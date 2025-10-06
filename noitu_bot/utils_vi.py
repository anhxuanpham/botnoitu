import re

_PUNCT = ".,;:!?\"'()[]{}…–—-/"


def norm_phrase(s: str) -> str:
    # lowercase + collapse whitespace, KEEP Vietnamese diacritics
    return re.sub(r"\s+", " ", s.strip().lower())


def _clean_token(tok: str) -> str:
    return tok.strip(_PUNCT).strip()


def first_token(s: str) -> str | None:
    s = norm_phrase(s)
    if not s:
        return None
    parts = [t for t in s.split(" ") if _clean_token(t)]
    return _clean_token(parts[0]) if parts else None  # WITH DIACRITICS


def last_token(s: str) -> str | None:
    s = norm_phrase(s)
    if not s:
        return None
    parts = [t for t in s.split(" ") if _clean_token(t)]
    return _clean_token(parts[-1]) if parts else None  # WITH DIACRITICS
