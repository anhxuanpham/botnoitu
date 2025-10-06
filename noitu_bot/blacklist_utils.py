# blacklist_utils.py
import os
from typing import List, Optional
from .redis_keys import K_BLACKLIST

_BLACKLIST_LOADED = False


def normalize_word(text: Optional[str]) -> str:
    return (text or "").strip().lower()


def read_blacklist_file(file_path: str = "words/blacklist.txt") -> List[str]:
    items: List[str] = []
    if not os.path.exists(file_path):
        return items
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            word = line.strip()
            if word and not word.startswith("#"):
                items.append(word.lower())
    return items


async def load_blacklist_to_redis(redis, file_path: str = "words/blacklist.txt") -> int:
    global _BLACKLIST_LOADED
    if _BLACKLIST_LOADED:
        return 0
    words = read_blacklist_file(file_path)
    if not words:
        _BLACKLIST_LOADED = True
        return 0
    added_count = 0
    try:
        if hasattr(redis, "pipeline"):
            pipe = redis.pipeline()
            for word in words:
                pipe.sadd(K_BLACKLIST(), word)
            results = pipe.execute()
            added_count = sum(1 for r in results if r == 1)
        else:
            for word in words:
                added_count += 1 if redis.sadd(K_BLACKLIST(), word) == 1 else 0
    finally:
        _BLACKLIST_LOADED = True
    return added_count


def is_in_blacklist(redis, word: str) -> bool:
    return bool(redis.sismember(K_BLACKLIST(), normalize_word(word)))


def append_word_to_file_if_missing(
    word: str, file_path: str = "words/blacklist.txt"
) -> bool:
    word_norm = normalize_word(word)
    exists = False
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().lower() == word_norm:
                    exists = True
                    break
    if not exists:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(word_norm + "\n")
        return True
    return False


def add_to_blacklist(redis, word: str, file_path: str = "words/blacklist.txt") -> dict:
    word_norm = normalize_word(word)
    redis_added = int(redis.sadd(K_BLACKLIST(), word_norm)) == 1
    file_added = append_word_to_file_if_missing(word_norm, file_path)
    return {"redis_added": redis_added, "file_added": file_added}


async def ensure_blacklist_loaded(
    redis, file_path: str = "words/blacklist.txt"
) -> None:
    if not _BLACKLIST_LOADED:
        await load_blacklist_to_redis(redis, file_path)
