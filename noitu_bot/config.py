import os, platform
from pathlib import Path

if platform.system().lower().startswith("win"):
    try:
        print("windows")
        from dotenv import load_dotenv, find_dotenv

        p = find_dotenv(filename=".env", usecwd=True) or str(
            Path(__file__).resolve().parent / ".env"
        )
        if p:
            load_dotenv(p, override=False)
    except Exception:
        pass
Fail_Limit = 20
GOOGLE_BASE64: str = os.getenv("GOOGLE_CREDENTIALS_BASE64")
DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
OPEN_AI: str = os.getenv("OPEN_AI", "")
OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "")

# FIX: ID's must be converted to int. Using '0' as safe default to prevent NoneType crash.
CHANNEL_ID: int = int(os.getenv('CHANNEL_ID', '0'))
CHAT_ROLE_ID: int = int(os.getenv('CHAT_ROLE_ID', '0'))
ROLE_ID: int = int(os.getenv("ROLE_ID", '0'))
ADMIN_USER_ID: int = int(os.getenv("ADMIN_USER_ID", '0'))

# FIX: Đảm bảo CHAT_CHANNEL_IDS là một LIST of INTs bằng cách đọc từ env và tách bằng dấu phẩy (nếu có).
chat_channels_raw = os.getenv('CHAT_CHANNEL_IDS', str(CHANNEL_ID))
CHAT_CHANNEL_IDS: list[int] = [int(i.strip()) for i in chat_channels_raw.split(',') if i.strip().isdigit()]

DICT_PATH = Path("words/words.txt")
LEADERBOARD_PATH = Path("data/leaderboard.json")
BLACKLIST_PATH = Path("words/blacklist.txt")

GUILD_ID: int | None = int(os.getenv("GUILD_ID")) if os.getenv("GUILD_ID") else None

REDIS_HOST: str = os.getenv("REDIS_HOST", "redis")
REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
REDIS_DECODE: bool = True  # keep UTF-8 Vietnamese text readable


# Minimal permissions for invite (View, Send, Add Reactions, Read History)
MIN_PERMS = 68672
ADMIN_PERMS = 8