# word_react.py
import os
import asyncio
import logging
from pathlib import Path
import discord
from .config import (
    DISCORD_TOKEN,
    CHANNEL_ID,
    DICT_PATH,
    GUILD_ID,
    REDIS_HOST,
    REDIS_PORT,
    REDIS_DB,
    REDIS_DECODE,
    ROLE_ID,
    Fail_Limit,
)
from .redis_keys import (
    K_PAUSED,
    K_LAST_USER,
    K_DICT,
    K_TOKEN_IDX,
    K_REMAIN,
    K_USED_TOKEN,
    K_LAST_WORD,
)

from .utils_vi import norm_phrase, first_token, last_token
from .blacklist_utils import add_to_blacklist

EMOJI_ADD = "❤️"
EMOJI_DEL = "❌"


def add_word_to_dictionary(r, phrase: str, ref) -> bool:
    phrase = phrase.lower()
    print("vào thêm từ")
    if r.sismember(K_DICT(), phrase):
        return False
    try:
        with open(DICT_PATH, "a+", encoding="utf-8") as f:
            f.seek(0, os.SEEK_END)
            if f.tell() > 0:
                f.seek(f.tell() - 1)
                if f.read(1) != "\n":
                    f.write("\n")
            f.write(phrase + "\n")
    except Exception as e:
        logging.error(f"Failed to write word '{phrase}' to dictionary file: {e}")
        return False
    ft = first_token(phrase)
    pipe = r.pipeline()
    pipe.sadd(K_DICT(), phrase)
    pipe.sadd(K_TOKEN_IDX(ft), phrase)

    last = r.get(K_LAST_WORD(ref.gid))
    need_tok = last_token(last) if last else None
    if need_tok == ft:
        used_key = K_USED_TOKEN(ref.gid, ft)
        rem_key = K_REMAIN(ref.gid, ft)
        if r.exists(rem_key) and not r.sismember(used_key, phrase):
            pipe.sadd(rem_key, phrase)

    try:
        pipe.execute()
        return True
    except Exception as e:
        logging.error(f"Failed to add word '{phrase}' to Redis: {e}")
        return False


async def handle_word_react(
    bot,
    r,
    ref,
    channel_id,
    role_id,
    dict_path,
    norm_phrase,
    first_token,
    last_token,
    K_DICT,
    K_TOKEN_IDX,
    K_LAST_WORD,
    K_USED_TOKEN,
    K_REMAIN,
    payload: discord.RawReactionActionEvent,
):
    if not bot.user or payload.user_id == bot.user.id:
        return
    if payload.channel_id != channel_id:
        return
    emoji = str(payload.emoji)
    if emoji not in {EMOJI_ADD, EMOJI_DEL}:
        return

    guild = bot.get_guild(payload.guild_id)
    member = payload.member
    if member is None and guild is not None:
        try:
            member = await guild.fetch_member(payload.user_id)
        except discord.NotFound:
            member = None
    if not member:
        return
    if not any(role.id == role_id for role in member.roles):
        return

    channel = bot.get_channel(payload.channel_id)
    if not channel:
        return
    try:
        msg = await channel.fetch_message(payload.message_id)
    except discord.NotFound:
        return

    content = (msg.content or "").strip()
    if len(content.split()) != 2:
        return

    phrase = norm_phrase(content)
    ft = first_token(phrase)
    if not ft:
        return

    dict_path = Path(dict_path)

    if emoji == EMOJI_ADD:
        print("vào thêm từ")
        if r.sismember(K_DICT(), phrase):
            try:
                await channel.send(f"⚠️ Từ **{content}** đã tồn tại trong từ điển.")
            except discord.HTTPException as e:
                logging.error(f"Failed to send duplicate word message: {e}")
            return

        def write_word_to_file():
            with open(dict_path, "a+", encoding="utf-8") as f:
                f.seek(0, os.SEEK_END)
                if f.tell() > 0:
                    f.seek(f.tell() - 1)
                    if f.read(1) != "\n":
                        f.write("\n")
                f.write(phrase + "\n")

        try:
            await asyncio.to_thread(write_word_to_file)
        except Exception as e:
            logging.error(f"Failed to write word '{phrase}' to file: {e}")
            return

        pipe = r.pipeline()
        pipe.sadd(K_DICT(), phrase)
        pipe.sadd(K_TOKEN_IDX(ft), phrase)

        last = r.get(K_LAST_WORD(ref.gid))
        need_tok = last_token(last) if last else None
        if need_tok == ft:
            used_key = K_USED_TOKEN(ref.gid, ft)
            rem_key = K_REMAIN(ref.gid, ft)
            if r.exists(rem_key) and not r.sismember(used_key, phrase):
                pipe.sadd(rem_key, phrase)

        try:
            pipe.execute()
            await channel.send(
                f"✅ Đã thêm **{content}** vào từ điển (dùng được ngay)!"
            )
        except discord.HTTPException as e:
            logging.error(f"Failed to send success message or execute Redis pipeline: {e}")
        except Exception as e:
            logging.error(f"Unexpected error adding word to Redis: {e}")

    elif emoji == EMOJI_DEL:
        if not r.sismember(K_DICT(), phrase):
            try:
                await channel.send(f"⚠️ Từ **{content}** không có trong từ điển.")
            except discord.HTTPException as e:
                logging.error(f"Failed to send word not found message: {e}")
            return

        def remove_word_from_file():
            src = Path(dict_path)
            tmp = src.with_suffix(src.suffix + ".tmp")
            removed = False
            with open(src, "r", encoding="utf-8") as fin, open(
                tmp, "w", encoding="utf-8"
            ) as fout:
                for line in fin:
                    if norm_phrase(line.strip()) == phrase:
                        removed = True
                        continue
                    fout.write(line)
            if removed:
                os.replace(tmp, src)
                return True
            else:
                try:
                    tmp.unlink(missing_ok=True)
                except Exception as e:
                    logging.warning(f"Failed to delete temp file: {e}")
                return False

        try:
            removed = await asyncio.to_thread(remove_word_from_file)
            if not removed:
                await channel.send("⚠️ Không thấy dòng cần xoá trong file.")
                return
        except Exception as e:
            logging.error(f"Failed to remove word '{phrase}' from file: {e}")
            try:
                await channel.send(f"❌ Lỗi khi xoá file: {e}")
            except discord.HTTPException as http_err:
                logging.error(f"Failed to send error message: {http_err}")
            return

        try:
            pipe = r.pipeline()
            pipe.srem(K_DICT(), phrase)
            pipe.srem(K_TOKEN_IDX(ft), phrase)
            used_key = K_USED_TOKEN(ref.gid, ft)
            rem_key = K_REMAIN(ref.gid, ft)
            pipe.srem(rem_key, phrase)
            pipe.srem(used_key, phrase)
            pipe.execute()
            await channel.send(f"❌ Đã xoá **{content}** khỏi từ điển.")
            added = add_to_blacklist(r, phrase, "words/blacklist.txt")
            if added.get("redis_added") or added.get("file_added"):
                print(f"[BLACKLIST] Đã thêm '{phrase}' vào blacklist")
            else:
                print(f"[BLACKLIST] '{phrase}' đã tồn tại trong blacklist")
        except discord.HTTPException as e:
            logging.error(f"Failed to send delete confirmation message: {e}")
        except Exception as e:
            logging.error(f"Unexpected error removing word from Redis: {e}")


async def _runner(*args, **kwargs):
    try:
        await handle_word_react(*args, **kwargs)
    except Exception as e:
        logging.exception("word_react task error: %s", e)


def spawn_word_react_task(*args, **kwargs):
    asyncio.create_task(_runner(*args, **kwargs))
