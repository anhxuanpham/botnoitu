from typing import Iterable
from redis import Redis
from .utils_vi import norm_phrase, first_token
from .redis_keys import K_DICT, K_TOKEN_IDX

def read_words_from_file(path: str) -> Iterable[str]:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            yield line

def bootstrap_dictionary_by_token_exact(
    r: Redis,
    words: Iterable[str],
    batch: int = 5000,
    *,
    purge_before_load: bool = True,
) -> None:
    """
    Load dictionary into Redis (with diacritics), after PURGING old keys:
      - dict:vi : all phrases (lowercase, keep accents)
      - dict:vi:tokenx:<first_token> : phrases whose FIRST token equals <first_token> (with accents)
    """
    # 1) Purge old dictionary/index keys (optional but default True)
    if purge_before_load:
        # xóa tập chính
        r.delete(K_DICT())
        # xóa toàn bộ index theo token đầu (có dấu)
        cursor = 0
        pattern = "dict:vi:tokenx:*"   # vì K_TOKEN_IDX(tok) = f"dict:vi:tokenx:{tok}"
        while True:
            cursor, keys = r.scan(cursor=cursor, match=pattern, count=1000)
            if keys:
                # xóa theo batch để tránh 1 lệnh DEL quá dài
                pipe = r.pipeline()
                for k in keys:
                    pipe.delete(k)
                pipe.execute()
            if cursor == 0:
                break

    # 2) Nạp lại từ điển + index
    pipe = r.pipeline()
    n = 0
    for raw in words:
        phrase = norm_phrase(raw)   # lowercase + gọn khoảng trắng, GIỮ DẤU
        if not phrase:
            continue
        ft = first_token(phrase)    # token đầu CÓ DẤU
        if not ft:
            continue

        pipe.sadd(K_DICT(), phrase)
        pipe.sadd(K_TOKEN_IDX(ft), phrase)

        n += 1
        if n % batch == 0:
            pipe.execute()

    if n % batch != 0:
        pipe.execute()
