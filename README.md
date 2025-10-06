
# Nối Từ Bot (Vietnamese Word-Chain) — Exact Diacritics

- Game runs in **one fixed channel** (`CHANNEL_ID`).
- Word connection by **LAST WORD**, with **exact Vietnamese diacritics**.
- Reactions only ✅/⛔; announce winner and auto-start new round with random opening.
- Redis-powered dictionary/index with per-token remain cache.
- Slash commands:
  - `/noitu batdau` — reset & start new round
  - `/noitu ketthuc` — pause game
  - `/noitu goiy` — give one hint (without consuming it)

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DISCORD_TOKEN=your_token_here
export CHANNEL_ID=123456789012345678
export DICT_PATH=./words.txt
# Optional: sync slash instantly in a guild
# export GUILD_ID=987654321098765432
python main.py
```

Redis must be running locally (or set REDIS_HOST/PORT/DB in env). Use UTF-8 dictionary file (one phrase per line, lowercase, with diacritics).

## Invite URL
Minimal perms + slash:
`https://discord.com/oauth2/authorize?client_id=YOUR_CLIENT_ID&scope=bot%20applications.commands&permissions=68672`

Admin perms:
`https://discord.com/oauth2/authorize?client_id=YOUR_CLIENT_ID&scope=bot%20applications.commands&permissions=8`
