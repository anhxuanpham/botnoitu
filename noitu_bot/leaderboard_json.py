from __future__ import annotations
import os, json, tempfile
from typing import Dict, List, Optional
import discord  # cần discord.py

# Đường dẫn file BXH
def lb_path(base_dir: str = "./data") -> str:
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, "leaderboard.json")

# Đọc JSON
def _read_json(path: str) -> Dict[str, Dict[str, object]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return {}
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}

# Ghi JSON an toàn
def _atomic_write(path: str, data: Dict[str, Dict[str, object]]) -> None:
    dir_ = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(prefix=".lb_", suffix=".json", dir=dir_, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass

# Ghi nhận 1 lượt thắng
def record_win_json(user_id: str, display_name: Optional[str],
                    base_dir: str = "./data") -> int:
    path = lb_path(base_dir)
    data = _read_json(path)
    entry = data.get(user_id, {"name": display_name or f"UID:{user_id}", "wins": 0})
    if display_name:
        entry["name"] = display_name
    entry["wins"] = int(entry.get("wins", 0)) + 1
    data[user_id] = entry
    _atomic_write(path, data)
    return int(entry["wins"])

# Lấy BXH top N
def get_leaderboard_json(top_n: int = 10, base_dir: str = "./data") -> List[Dict[str, object]]:
    data = _read_json(lb_path(base_dir))
    items = sorted(
        data.items(),
        key=lambda kv: (-int(kv[1].get("wins", 0)), str(kv[1].get("name", "")))
    )
    rows: List[Dict[str, object]] = []
    for user_id, info in items[:max(0, top_n)]:
        rows.append({
            "user_id": user_id,
            "name": info.get("name", f"UID:{user_id}"),
            "wins": int(info.get("wins", 0)),
        })
    return rows

# Reset BXH
def reset_leaderboard_json(base_dir: str = "./data") -> None:
    path = lb_path(base_dir)
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def format_leaderboard_embed(rows: List[Dict[str, object]]) -> discord.Embed:
    if not rows:
        return discord.Embed(
            title="🏆 Bảng xếp hạng",
            description="Chưa có ai thắng!",
            color=discord.Color.dark_grey()
        )

    medals = ["🥇", "🥈", "🥉"]

    embed = discord.Embed(
        title="🏆 Bảng xếp hạng",
        color=0xFFD166
    )

    lines = []
    for i, r in enumerate(rows, start=1):
        icon = medals[i-1] if i <= len(medals) else f"#{i}"
        wins = r["wins"]
        name = r["name"]
        lines.append(f"{icon} **{name}** — 🏆 {wins} lần thắng")

    separator = "\n┄┄┄┄┄┄┄┄┄┄┄┄\n"
    embed.description = separator.join(lines)
    embed.set_footer(text="Cố gắng giành nhiều chiến thắng hơn nhé!")
    return embed



