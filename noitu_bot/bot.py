import platform
from datetime import datetime, time
import logging
import random
import discord
import re
import os
import asyncio
from discord.utils import get
from discord.ext import tasks
from discord import app_commands
from redis import Redis
from .config import (
    DISCORD_TOKEN,
    CHANNEL_ID,
    DICT_PATH,
    GUILD_ID,
    REDIS_HOST,
    REDIS_PORT,
    REDIS_DB,
    REDIS_DECODE,
    CHAT_CHANNEL_IDS,
    CHAT_ROLE_ID,
    ROLE_ID,
    Fail_Limit,
)
from ai_gemini.gpt_mini_bot import check_vietnamese_word, gpt_generate_bot_reply

from .dict_bootstrap import bootstrap_dictionary_by_token_exact, read_words_from_file
from .referee import WordChainRefereeByLastWordExact
from .redis_keys import (
    K_PAUSED,
    K_LAST_USER,
    K_DICT,
    K_TOKEN_IDX,
    K_REMAIN,
    K_USED_TOKEN,
    K_LAST_WORD,
    K_BLACKLIST,
)
from .commands import NoituSlash
from .leaderboard_json import (
    record_win_json,
    get_leaderboard_json,
    format_leaderboard_embed,
)
from .utils_vi import norm_phrase, first_token, last_token
from .word_react import spawn_word_react_task, add_word_to_dictionary
from .ratelimit import RateLimiter
from typing import Optional
from .blacklist_utils import (
    ensure_blacklist_loaded,
    normalize_word,
    is_in_blacklist,
    add_to_blacklist,
)

is_checkspell = os.getenv("IS_CHECKSPELL", True)
ai_rate_limiter = RateLimiter(max_calls=50, period_seconds=60)

user_cooldowns = {}
COOLDOWN_SECONDS = 30

EMOJI_PATTERN = re.compile(r"^(\s*(<a?:\w+:\d+>|[\U0001F000-\U0001FAFF]))+\s*$")


async def handle_invalid_word(redis_client, input_word: str, ref, chanel):
    if await ai_rate_limiter.is_limited():
        print(f"Rate limit đã đạt, bỏ qua kiểm tra từ: '{input_word}'")
        return

    await ensure_blacklist_loaded(redis_client, "words/blacklist.txt")

    normalized_word = normalize_word(input_word)
    if not normalized_word:
        return

    try:
        if is_in_blacklist(redis_client, normalized_word):
            print(f"[BLACKLIST] Bỏ qua '{normalized_word}' (đã trong blacklist).")
            return
    except Exception as ex:
        print(f"[BLACKLIST] Lỗi khi kiểm tra: {ex}")
        return

    try:
        verdict = await check_vietnamese_word(normalized_word)
    except Exception as ex:
        print(f"[CHECK WORD] Lỗi gọi AI: {ex}")
        return

    if verdict == "có":
        try:
            is_added = add_word_to_dictionary(
                r=redis_client, phrase=input_word, ref=ref
            )
            if is_added:
                await chanel.send(
                    f"✅ Đã thêm **{input_word}** vào từ điển (dùng được ngay) - BY CHATGPT!"
                )
        except Exception as ex:
            print(f"[DICT] Lỗi khi thêm '{normalized_word}' vào {K_DICT()}: {ex}")
    else:
        try:
            added = add_to_blacklist(
                redis_client, normalized_word, "words/blacklist.txt"
            )
            if added.get("redis_added") or added.get("file_added"):
                print(f"[BLACKLIST] Đã thêm '{normalized_word}' vào blacklist")
            else:
                print(f"[BLACKLIST] '{normalized_word}' đã tồn tại trong blacklist")
        except Exception as ex:
            print(f"[BLACKLIST] Lỗi khi thêm '{normalized_word}': {ex}")


def game_id_for_channel(channel_id: int) -> str:
    return f"channel:{channel_id}"


def run():
    if not DISCORD_TOKEN or DISCORD_TOKEN == "YOUR_BOT_TOKEN":
        raise RuntimeError("Please set DISCORD_TOKEN environment variable.")
    if not CHANNEL_ID:
        raise RuntimeError("Please set CHANNEL_ID environment variable.")

    r = Redis(
        host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=REDIS_DECODE
    )
    gid = game_id_for_channel(CHANNEL_ID)
    ref = WordChainRefereeByLastWordExact(r, gid)

    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True  # QUAN TRỌNG: để lấy member/roles
    intents.guilds = True
    intents.reactions = True
    intents.message_content = True
    bot = discord.Client(intents=intents)
    tree = app_commands.CommandTree(bot)

    # register slash group
    noitu = NoituSlash(
        name="noitu",
        description="Quản lý trò nối từ",
        ref=ref,
        channel_id=CHANNEL_ID,
        r=r,
    )
    tree.add_command(noitu)

    @tasks.loop(seconds=60)
    async def send_last_word_reminder():
        await bot.wait_until_ready()
        if r.get(K_PAUSED(gid)) == "1":
            return
        last_word = r.get(K_LAST_WORD(gid))
        channel = bot.get_channel(CHANNEL_ID)

        if channel and last_word:
            try:
                # Lấy message cuối cùng của channel
                last_msgs = [msg async for msg in channel.history(limit=1)]
                if last_msgs:
                    last_msg = last_msgs[0]
                    if "💡 Từ hiện tại là:" in last_msg.content:
                        return  # Đã có nhắc rồi, skip
                await channel.send(f"💡 Từ hiện tại là: **{last_word}**")
            except Exception as e:
                logging.error(f"Không t$hể gửi tin nhắn nhắc nhở: {e}")

    @bot.event
    async def on_ready():
        logging.info("Bot ready as %s", bot.user)
        try:
            if GUILD_ID:
                await tree.sync(guild=discord.Object(id=GUILD_ID))
                logging.info("Slash commands synced to guild %s.", GUILD_ID)
            else:
                await tree.sync()
                logging.info("Slash commands synced globally.")
        except Exception as e:
            logging.exception("Slash sync failed: %s", e)

        # Bootstrap dictionary (idempotent)
        try:
            bootstrap_dictionary_by_token_exact(r, read_words_from_file(DICT_PATH))
            logging.info("Dictionary bootstrapped from %s", DICT_PATH)
        except FileNotFoundError:
            logging.warning("Dictionary file not found: %s", DICT_PATH)

        # Start first round
        ch = bot.get_channel(CHANNEL_ID)
        if ch:
            opening = ref.start_round_random()

            if opening:
                await ch.send(f"🎮 **Ván mới!** Từ mở màn: **{opening}**")
            else:
                await ch.send("⚠️ Từ điển rỗng hoặc chưa nạp từ điển.")
        logging.info("Joined channel %s", CHANNEL_ID)
        send_last_word_reminder.start()

    @bot.event
    async def on_message(message: discord.Message):
        if message.author.bot or message.channel.id != CHANNEL_ID:
            return

        content = message.content.strip()
        if not content:
            return

        if message.stickers:
            return

        if EMOJI_PATTERN.match(content):
            return

        if message.reference:
            try:
                replied_to = await message.channel.fetch_message(
                    message.reference.message_id
                )
                # Nếu tin nhắn được reply là của bot
                if replied_to.author == bot.user:
                    # Tạo một task chạy nền để bot "tư duy" và trả lời
                    async def thinking_and_replying():
                        async with message.channel.typing():
                            reply_content = await gpt_generate_bot_reply(message)
                            await message.reply(reply_content, mention_author=False)

                    bot.loop.create_task(thinking_and_replying())
                    return
            except discord.NotFound:
                # Người dùng reply một tin nhắn đã bị xóa, bỏ qua
                pass
            except Exception as e:
                print(f"Lỗi khi xử lý tin nhắn reply: {e}")

        if len(content.split()) != 2:
            return

        if r.get(K_PAUSED(ref.gid)) == "1":
            try:
                await message.add_reaction("⛔")
            except Exception:
                pass
            return
        # NEW: chặn lặp user liên tiếp (trừ khi last là BOT)
        last_user = r.get(K_LAST_USER(ref.gid))
        if last_user and last_user != "BOT" and last_user == str(message.author.id):
            try:
                await message.add_reaction("⏳")
            except Exception:
                pass
            return
        res = ref.submit(user_id=str(message.author.id), raw_phrase=content)
        try:
            if res["ok"]:
                emoji = "✅"
            elif res["msg"] == "USED":
                emoji = "🔁"
            elif res["msg"] == "FAIL_LIMIT_REACHED":
                emoji = "🔒"
            elif res["msg"] == "COOLDOWN":
                remaining = res.get("cooldown_left", "?")
                number_emojis = {
                    1: "1️⃣",
                    2: "2️⃣",
                    3: "3️⃣",
                    4: "4️⃣",
                    5: "5️⃣",
                }
                print(f"{number_emojis.get(remaining, '❓')}")
                emoji = f"{number_emojis.get(remaining, '❓')}"
            else:
                emoji = "⛔"
                print(res["msg"])
                if res["msg"] == "NOT_IN_DICT":
                    if is_checkspell:
                        asyncio.create_task(
                            handle_invalid_word(r, content, ref, message.channel)
                        )
            await message.add_reaction(emoji)
        except Exception:
            pass

        if res["ended"] and res["msg"] != "ENDED":
            winner_id = res.get("winner")

            if winner_id and winner_id != "BOT":
                try:
                    winner_member = message.guild.get_member(int(winner_id))
                    display_name = (
                        winner_member.display_name
                        if winner_member
                        else f"User {winner_id}"
                    )
                except (ValueError, AttributeError):
                    display_name = f"User {winner_id}"

                total_wins = record_win_json(
                    user_id=str(winner_id),
                    display_name=display_name,
                    base_dir="./data",
                )
                top5 = get_leaderboard_json(top_n=5, base_dir="./data")
                lb_embed = format_leaderboard_embed(top5)

                hint = ref.get_hint()
                if res["msg"] == "FAIL_LIMIT_REACHED":
                    win_announcement = (
                        f"💡 **Gợi ý:** `{hint}`"
                        f"🔒 **Sai từ vượt quá {Fail_Limit} lần, kết thúc ván!**\n"
                        f"🏁 Người chiến thắng là **<@{winner_id}>**! (tổng: {total_wins})"
                    )
                else:
                    win_announcement = (
                        f"🏁 **<@{winner_id}> thắng!** (tổng: {total_wins})"
                    )

                opening = ref.start_round_random()
                if opening:
                    await message.channel.send(
                        f"{win_announcement}\n"
                        f"🔄 **Ván mới!** Từ mở màn: **{opening}**",
                        embed=lb_embed,
                    )
                else:
                    await message.channel.send(
                        f"{win_announcement}\n"
                        f"⚠️ Không thể mở ván mới (từ điển rỗng).",
                        embed=lb_embed,
                    )
            else:
                opening = ref.start_round_random()
                if opening:
                    await message.channel.send(
                        f"🔒 Ván chơi kết thúc do có quá nhiều lượt sai.\n"
                        f"🔄 **Ván mới!** Từ mở màn: **{opening}**"
                    )
                else:
                    await message.channel.send("⚠️ Không thể mở ván mới (từ điển rỗng).")

    @bot.event
    async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
        spawn_word_react_task(
            bot,
            r,
            ref,
            CHANNEL_ID,
            ROLE_ID,
            DICT_PATH,
            norm_phrase,
            first_token,
            last_token,
            K_DICT,
            K_TOKEN_IDX,
            K_LAST_WORD,
            K_USED_TOKEN,
            K_REMAIN,
            payload,
        )

    bot.run(DISCORD_TOKEN)
