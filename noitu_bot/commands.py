import logging
import discord
import os, asyncio, tarfile, tempfile
from datetime import datetime
from pathlib import Path
from discord import app_commands
from .redis_keys import K_PAUSED, K_ENDED, K_LAST_USER
from .referee import WordChainRefereeByLastWordExact
from .leaderboard_json import (
    get_leaderboard_json,
    format_leaderboard_embed,
    record_win_json,
)
from .config import (
    ROLE_ID,
    DICT_PATH,
    BLACKLIST_PATH,
    LEADERBOARD_PATH,
)  # import role id


def build_leaderboard_embed(
    guild: discord.Guild | None,
    gid: str,
    top_n: int = 10,
    title: str = "🏆 Bảng xếp hạng Nối Từ",
    color: int = 0xFFD166,
) -> discord.Embed:
    rows = get_leaderboard_json(gid, top_n=top_n, base_dir="./data")
    if not rows:
        return discord.Embed(title=title, description="(chưa có ai thắng)", color=color)

    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, r in enumerate(rows, start=1):
        icon = medals[i - 1] if i <= len(medals) else f"{i}."
        name = r["name"]
        wins = r["wins"]
        lines.append(f"{icon} **{name}** — **{wins}** thắng")

    emb = discord.Embed(title=title, description="\n".join(lines), color=color)
    emb.set_footer(text="Cập nhật theo lần thắng đã lưu")
    return emb


class NoituSlash(app_commands.Group):
    def __init__(
        self,
        name: str,
        description: str,
        *,
        ref: WordChainRefereeByLastWordExact,
        channel_id: int,
        r,
    ):
        super().__init__(name=name, description=description)
        self.ref = ref
        self.channel_id = channel_id
        self.r = r

    # Hàm check quyền role
    def _has_permission(self, inter: discord.Interaction) -> bool:
        return any(role.id == ROLE_ID for role in inter.user.roles)

    @app_commands.command(
        name="batdau", description="Reset hoàn toàn ván và mở ván mới (random)."
    )
    async def batdau(self, inter: discord.Interaction):
        if not self._has_permission(inter):
            await inter.response.send_message(
                "❌ Bạn không có quyền dùng lệnh này.", ephemeral=True
            )
            return
        if inter.channel_id != self.channel_id:
            await inter.response.send_message("❌ Sai kênh.", ephemeral=True)
            return

        self.r.delete(K_PAUSED(self.ref.gid))
        opening = self.ref.start_round_random()
        logging.info("/noitu batdau by %s -> %s", inter.user.id, opening)
        if opening:
            await inter.response.send_message(
                f"🔄 **Reset ván!**\n🎮 **Ván mới!** Từ mở màn: **{opening}**"
            )
        else:
            await inter.response.send_message("⚠️ Không thể mở ván mới (từ điển rỗng).")

    @app_commands.command(
        name="ketthuc", description="Tạm ngưng bot; chỉ nhận lệnh quản trị."
    )
    async def ketthuc(self, inter: discord.Interaction):
        if not self._has_permission(inter):
            await inter.response.send_message(
                "❌ Bạn không có quyền dùng lệnh này.", ephemeral=True
            )
            return
        if inter.channel_id != self.channel_id:
            await inter.response.send_message("❌ Sai kênh.", ephemeral=True)
            return

        self.r.set(K_PAUSED(self.ref.gid), "1")
        logging.info("/noitu ketthuc by %s", inter.user.id)
        await inter.response.send_message(
            "⏸️ **Đã tạm ngưng trò nối từ.** Dùng `/noitu batdau` để chơi lại."
        )

    @app_commands.command(
        name="goiy", description="Gợi ý, cho người cuối thắng và mở ván mới."
    )
    async def goiy(self, inter: discord.Interaction):
        if not self._has_permission(inter):
            await inter.response.send_message(
                "❌ Bạn không có quyền dùng lệnh này.", ephemeral=True
            )
            return
        if inter.channel_id != self.channel_id:
            await inter.response.send_message("❌ Sai kênh.", ephemeral=True)
            return
        if self.r.get(K_PAUSED(self.ref.gid)) == "1":
            await inter.response.send_message(
                "⏸️ Đang tạm ngưng. Dùng `/noitu batdau` để tiếp tục."
            )
            return

        last_uid = self.r.get(K_LAST_USER(self.ref.gid))
        if not last_uid:
            await inter.response.send_message("⚠️ Chưa có người chơi trước đó.")
            return

        await inter.response.defer()

        hint = self.ref.get_hint()
        if hint:
            await inter.followup.send(f"💡 **Gợi ý:** `{hint}`")
        else:
            await inter.followup.send("🤔 Không có gợi ý khả dụng.")

        member = inter.guild.get_member(int(last_uid)) if inter.guild else None
        if not member and inter.guild:
            try:
                member = await inter.guild.fetch_member(int(last_uid))
            except Exception:
                member = None
        display_name = member.display_name if member else str(last_uid)

        total_wins = record_win_json(
            user_id=str(last_uid),
            display_name=display_name,
            base_dir="./data",
        )
        top5 = get_leaderboard_json(top_n=5, base_dir="./data")
        lb_embed = format_leaderboard_embed(top5)

        opening = self.ref.start_round_random()
        if opening:
            await inter.followup.send(
                f"🏁 **<@{last_uid}> thắng!** (tổng: {total_wins})\n"
                f"🔄 **Ván mới!** Từ mở màn: **{opening}**",
                embed=lb_embed,
            )
        else:
            await inter.followup.send(
                f"🏁 **<@{last_uid}> thắng!** (tổng: {total_wins})\n"
                f"⚠️ Không thể mở ván mới (từ điển rỗng).",
                embed=lb_embed,
            )

    @app_commands.command(name="bxh", description="Xem bảng xếp hạng (top 10).")
    @app_commands.describe(solan="Số người đứng đầu muốn xem (mặc định 10, tối đa 25)")
    async def bxh(self, inter: discord.Interaction, solan: int = 10):
        if not self._has_permission(inter):
            await inter.response.send_message(
                "❌ Bạn không có quyền dùng lệnh này.", ephemeral=True
            )
            return
        if inter.channel_id != self.channel_id:
            await inter.response.send_message("❌ Sai kênh.", ephemeral=True)
            return

        top_n = max(1, min(25, solan))
        rows = get_leaderboard_json(top_n=top_n)
        embed = format_leaderboard_embed(rows)
        await inter.response.send_message(embed=embed)

    @app_commands.command(
        name="backup", description="Đóng gói words + leaderboard và gửi DM."
    )
    async def backup(self, inter: discord.Interaction):
        if inter.user.id != 237506940391915522:
            await inter.response.send_message("❌ Không được phép.", ephemeral=True)
            return
        await inter.response.send_message(
            "⏳ Đang backup, sẽ gửi file qua DM khi xong.", ephemeral=True
        )
        asyncio.create_task(self._backup_dm_task(inter.user))

    async def _backup_dm_task(self, user: discord.User):
        files = [p for p in [DICT_PATH, LEADERBOARD_PATH, BLACKLIST_PATH] if p.exists()]
        if not files:
            try:
                await user.send("❌ Không tìm thấy files cần backup.")
            except:
                pass
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"backup_noitu_{ts}.tar.gz"

        try:
            with tempfile.TemporaryDirectory() as tmp:
                tarpath = Path(tmp) / fname
                with tarfile.open(tarpath, "w:gz") as tar:
                    for p in files:
                        tar.add(p, arcname=p.as_posix())
                try:
                    await user.send(
                        content=f"✅ {fname}",
                        file=discord.File(str(tarpath), filename=fname),
                    )
                except Exception as e:
                    try:
                        await user.send(f"❌ Lỗi: {e}")
                    except:
                        pass
        except Exception as e:
            try:
                await user.send(f"❌ Lỗi: {e}")
            except:
                pass
