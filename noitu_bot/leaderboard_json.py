from __future__ import annotations
import os, json, tempfile
from typing import Dict, List, Optional
import discord

# START FIX: IMPORTS VÀ FALLBACK CHO MONITORING METRICS
try:
    # Cần đảm bảo file monitoring_server.py đã được tạo
    from .monitoring_server import GAMES_COMPLETED_COUNTER
except ImportError:
    print("Warning: Could not import monitoring metrics. Running without Prometheus.")


    class DummyCounter:
        def inc(self):
            pass


    GAMES_COMPLETED_COUNTER = DummyCounter()


# END FIX


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


# Ghi log số lần đánh từ (hàm mới)
def record_word_attempt_json(user_id: str, is_correct: bool, base_dir: str = "./data"):
    path = lb_path(base_dir)
    data = _read_json(path)
    user_data = data.get(user_id, {"name": f"UID:{user_id}", "wins": 0, "correct_words": 0, "total_attempts": 0})

    user_data["total_attempts"] = user_data.get("total_attempts", 0) + 1
    if is_correct:
        user_data["correct_words"] = user_data.get("correct_words", 0) + 1

    # Đảm bảo name tồn tại khi chưa thắng
    if "name" not in user_data:
        user_data["name"] = f"UID:{user_id}"

    data[user_id] = user_data
    _atomic_write(path, data)


# Ghi nhận 1 lượt thắng (đã sửa để cập nhật cấu trúc data mới và tăng metric)
def record_win_json(user_id: str, display_name: Optional[str],
                    base_dir: str = "./data") -> int:
    path = lb_path(base_dir)
    data = _read_json(path)
    entry = data.get(user_id,
                     {"name": display_name or f"UID:{user_id}", "wins": 0, "correct_words": 0, "total_attempts": 0})

    if display_name and entry.get("name") != display_name:
        entry["name"] = display_name

    entry["wins"] = int(entry.get("wins", 0)) + 1

    # Đảm bảo các trường metrics tồn tại
    entry["correct_words"] = entry.get("correct_words", 0)
    entry["total_attempts"] = entry.get("total_attempts", 0)

    data[user_id] = entry
    _atomic_write(path, data)

    # Tăng metric GAMES_COMPLETED
    GAMES_COMPLETED_COUNTER.inc()

    return int(entry["wins"])


# Lấy BXH top N (Đã sửa để lấy metrics)
def get_leaderboard_json(top_n: int = 10, base_dir: str = "./data") -> List[Dict[str, object]]:
    path = lb_path(base_dir)
    data = _read_json(path)

    # Cập nhật và sắp xếp lại dữ liệu theo số lần thắng
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
            # Thêm các trường metrics mới
            "correct_words": int(info.get("correct_words", 0)),
            "total_attempts": int(info.get("total_attempts", 0)),
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

    ranks = []
    wins = []
    accuracy = []

    for i, data in enumerate(rows, start=1):

        total_attempts = data.get("total_attempts", 0)
        correct_words = data.get("correct_words", 0)
        user_wins = data.get("wins", 0)

        # Tính toán tỷ lệ
        if total_attempts > 0:
            rate = (correct_words / total_attempts) * 100
            acc_str = f"{correct_words}/{total_attempts} ({rate:.2f}%)"
        else:
            acc_str = "0/0 (0.00%)"

        # Điền vào các cột
        if i <= 3:
            rank_str = f"{data['name']}"
            ranks.append(f"{['🥇', '🥈', '🥉'][i - 1]} **{rank_str}**")
        else:
            ranks.append(f"#{i} {data['name']}")

        wins.append(str(user_wins))
        accuracy.append(acc_str)

    embed = discord.Embed(
        title="🏆 Bảng xếp hạng Nối Từ - Top 10 🏆",
        description="Ai là Chúa tể ngôn ngữ?",
        color=discord.Color.gold(),
    )

    embed.add_field(name="Hạng/Người chơi", value="\n".join(ranks), inline=True)
    embed.add_field(name="Thắng", value="\n".join(wins), inline=True)
    embed.add_field(name="Từ đúng", value="\n".join(accuracy), inline=True)

    embed.set_footer(text="Cố gắng giành nhiều chiến thắng hơn nhé!")
    return embed