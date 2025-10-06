def K_DICT() -> str:
    return "dict:vi"


def K_TOKEN_IDX(tok: str) -> str:
    return f"dict:vi:tokenx:{tok}"  # index by FIRST token (with diacritics)


def K_LAST_WORD(gid: str) -> str:
    return f"wc:{gid}:last_word"


def K_LAST_USER(gid: str) -> str:
    return f"wc:{gid}:last_user"


def K_USED(gid: str) -> str:
    return f"wc:{gid}:used"


def K_USED_TOKEN(gid: str, tok: str) -> str:
    return f"wc:{gid}:used_tokenx:{tok}"


def K_REMAIN(gid: str, tok: str) -> str:
    return f"wc:{gid}:remainx:{tok}"


def K_WINNER(gid: str) -> str:
    return f"wc:{gid}:winner"


def K_ENDED(gid: str) -> str:
    return f"wc:{gid}:ended"


def K_PAUSED(gid: str) -> str:
    return f"wc:{gid}:paused"


def K_FAILS(gid: str, word: str) -> str:
    return f"wc:{gid}:fails:{word}"


def K_BLACKLIST() -> str:
    return f"dict:blacklist"
