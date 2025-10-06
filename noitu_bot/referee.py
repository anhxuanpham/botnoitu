from typing import Optional, Dict, Any
from redis import Redis
from .config import Fail_Limit
from .utils_vi import norm_phrase, first_token, last_token
from .redis_keys import (
    K_DICT,
    K_TOKEN_IDX,
    K_LAST_WORD,
    K_LAST_USER,
    K_USED,
    K_USED_TOKEN,
    K_REMAIN,
    K_WINNER,
    K_ENDED,
    K_PAUSED,
    K_FAILS,
)


class WordChainRefereeByLastWordExact:
    """Referee for Vietnamese word-chain (connect by LAST WORD, with diacritics)."""

    def __init__(self, r: Redis, game_id: str):
        self.r = r
        self.gid = game_id
        self.fail_limit = Fail_Limit

    def start_round_random(self) -> Optional[str]:
        """
        Mở ván mới với 1 từ random NHƯNG đảm bảo có nước đi tiếp theo:
        chọn 'opening' sao cho scard(dict:vi:tokenx:<last_token(opening)>) > 0.
        """
        # reset state cũ
        self.r.delete(
            K_LAST_WORD(self.gid),
            K_LAST_USER(self.gid),
            K_USED(self.gid),
            K_WINNER(self.gid),
            K_ENDED(self.gid),
        )
        self._wipe_prefix(f"wc:{self.gid}:remainx:*")
        self._wipe_prefix(f"wc:{self.gid}:used_tokenx:*")
        self._wipe_prefix(f"wc:{self.gid}:fails:*")
        # Thử ngẫu nhiên trước (nhanh)
        tried = set()
        for _ in range(256):  # thử tối đa 256 lần
            opening = self.r.srandmember(K_DICT())
            if not opening:
                break
            if opening in tried:
                continue
            tried.add(opening)

            next_tok = last_token(opening)  # CÓ DẤU
            if not next_tok:
                continue

            # Có ít nhất 1 ứng viên bắt đầu bằng next_tok?
            if self.r.scard(K_TOKEN_IDX(next_tok)) > 0:
                # Chọn được opening hợp lệ
                ft = first_token(opening)
                pipe = self.r.pipeline()
                pipe.set(K_LAST_WORD(self.gid), opening)
                pipe.set(K_LAST_USER(self.gid), "BOT")
                pipe.sadd(K_USED(self.gid), opening)
                if ft:
                    pipe.sadd(K_USED_TOKEN(self.gid, ft), opening)
                    pipe.srem(K_REMAIN(self.gid, ft), opening)
                pipe.delete(K_WINNER(self.gid), K_ENDED(self.gid))
                # Pre-warm remain cho next_tok để lượt sau check nhanh
                pipe.sunionstore(K_REMAIN(self.gid, next_tok), K_TOKEN_IDX(next_tok))
                pipe.sdiffstore(
                    K_REMAIN(self.gid, next_tok),
                    K_REMAIN(self.gid, next_tok),
                    K_USED_TOKEN(self.gid, next_tok),
                )
                pipe.execute()
                return opening

        # Fallback: SCAN dict để kiếm 1 opening hợp lệ (chắc chắn có nước)
        cursor = 0
        while True:
            cursor, chunk = self.r.sscan(K_DICT(), cursor=cursor, count=2000)
            for opening in chunk:
                if opening in tried:
                    continue
                next_tok = last_token(opening)
                if next_tok and self.r.scard(K_TOKEN_IDX(next_tok)) > 0:
                    ft = first_token(opening)
                    pipe = self.r.pipeline()
                    pipe.set(K_LAST_WORD(self.gid), opening)
                    pipe.set(K_LAST_USER(self.gid), "BOT")
                    pipe.sadd(K_USED(self.gid), opening)
                    if ft:
                        pipe.sadd(K_USED_TOKEN(self.gid, ft), opening)
                        pipe.srem(K_REMAIN(self.gid, ft), opening)
                    pipe.delete(K_WINNER(self.gid), K_ENDED(self.gid))
                    pipe.sunionstore(
                        K_REMAIN(self.gid, next_tok), K_TOKEN_IDX(next_tok)
                    )
                    pipe.sdiffstore(
                        K_REMAIN(self.gid, next_tok),
                        K_REMAIN(self.gid, next_tok),
                        K_USED_TOKEN(self.gid, next_tok),
                    )
                    pipe.execute()
                    return opening
            if cursor == 0:
                break

        # Không tìm được gì
        return None

    def submit(self, user_id: str, raw_phrase: str) -> Dict[str, Any]:
        if self.r.get(K_ENDED(self.gid)) == "1":
            return {
                "ok": False,
                "ended": True,
                "winner": self.r.get(K_WINNER(self.gid)),
                "msg": "ENDED",
            }
        if self.r.get(K_PAUSED(self.gid)) == "1":
            return {"ok": False, "ended": False, "winner": None, "msg": "PAUSED"}

        last = self.r.get(K_LAST_WORD(self.gid))
        phrase = norm_phrase(raw_phrase)
        cooldown_key = f"COOLDOWN:{self.gid}"

        if not self.r.sismember(K_DICT(), phrase):
            if last:
                new_count = self.r.incr(K_FAILS(self.gid, last))
                if new_count >= self.fail_limit:
                    last_successful_user = self.r.get(K_LAST_USER(self.gid))
                    if last_successful_user and last_successful_user != "BOT":
                        self._win(last_successful_user)
                        if last:
                            cooldown_items = self.r.hgetall(cooldown_key)
                            for k, v in cooldown_items.items():
                                if k != last:
                                    remaining_wins = int(v) - 1
                                    if remaining_wins <= 0:
                                        self.r.hdel(cooldown_key, k)
                                    else:
                                        self.r.hset(cooldown_key, k, remaining_wins)
                            self.r.hset(cooldown_key, last, 5)
                        return {
                            "ok": False,
                            "ended": True,
                            "winner": last_successful_user,
                            "msg": "FAIL_LIMIT_REACHED",
                        }
            return {"ok": False, "ended": False, "winner": None, "msg": "NOT_IN_DICT"}
        if self.r.sismember(K_USED(self.gid), phrase):
            return {"ok": False, "ended": False, "winner": None, "msg": "USED"}

        if self.r.hexists(cooldown_key, phrase):
            left = int(self.r.hget(cooldown_key, phrase))
            return {
                "ok": False,
                "ended": False,
                "winner": None,
                "msg": "COOLDOWN",
                "cooldown_left": left,
            }

        if last:
            need_tok = last_token(last)
            got_tok = first_token(phrase)
            if not need_tok or not got_tok or need_tok != got_tok:
                self.r.incr(K_FAILS(self.gid, last))
                return {
                    "ok": False,
                    "ended": False,
                    "winner": None,
                    "msg": "RULE_MISMATCH",
                }

        ft = first_token(phrase)
        pipe = self.r.pipeline()
        pipe.set(K_LAST_WORD(self.gid), phrase)
        pipe.set(K_LAST_USER(self.gid), user_id)
        pipe.sadd(K_USED(self.gid), phrase)
        if ft:
            pipe.sadd(K_USED_TOKEN(self.gid, ft), phrase)
            pipe.srem(K_REMAIN(self.gid, ft), phrase)
        pipe.execute()
        if last:
            self.r.delete(K_FAILS(self.gid, last))
        next_need_tok = last_token(phrase)
        if not next_need_tok:
            self._win(user_id)
            cooldown_items = self.r.hgetall(cooldown_key)
            for k, v in cooldown_items.items():
                if k != phrase:
                    remaining_wins = int(v) - 1
                    if remaining_wins <= 0:
                        self.r.hdel(cooldown_key, k)
                    else:
                        self.r.hset(cooldown_key, k, remaining_wins)
            self.r.hset(cooldown_key, phrase, 3)
            return {"ok": True, "ended": True, "winner": user_id, "msg": "WIN"}

        self._ensure_remain(next_need_tok)
        if self.r.scard(K_REMAIN(self.gid, next_need_tok)) == 0:
            self._win(user_id)
            cooldown_items = self.r.hgetall(cooldown_key)
            for k, v in cooldown_items.items():
                if k != phrase:
                    remaining_wins = int(v) - 1
                    if remaining_wins <= 0:
                        self.r.hdel(cooldown_key, k)
                    else:
                        self.r.hset(cooldown_key, k, remaining_wins)
            self.r.hset(cooldown_key, phrase, 3)
            return {"ok": True, "ended": True, "winner": user_id, "msg": "WIN"}

        return {"ok": True, "ended": False, "winner": None, "msg": "OK"}

    def get_hint(self) -> Optional[str]:
        if self.r.get(K_ENDED(self.gid)) == "1":
            return None
        last = self.r.get(K_LAST_WORD(self.gid))
        if not last:
            return self.r.srandmember(K_DICT())
        need_tok = last_token(last)
        if not need_tok:
            return None
        rkey = K_REMAIN(self.gid, need_tok)
        if not self.r.exists(rkey):
            pipe = self.r.pipeline()
            pipe.sunionstore(rkey, K_TOKEN_IDX(need_tok))
            pipe.sdiffstore(rkey, rkey, K_USED_TOKEN(self.gid, need_tok))
            pipe.execute()
        return self.r.srandmember(rkey)

    def _ensure_remain(self, tok: str):
        rkey = K_REMAIN(self.gid, tok)
        if self.r.exists(rkey):
            return
        pipe = self.r.pipeline()
        pipe.sunionstore(rkey, K_TOKEN_IDX(tok))
        pipe.sdiffstore(rkey, rkey, K_USED_TOKEN(self.gid, tok))
        pipe.execute()

    def _win(self, user_id: str):
        self.r.set(K_WINNER(self.gid), user_id)
        self.r.set(K_ENDED(self.gid), "1")

    def _wipe_prefix(self, pattern: str):
        cursor = 0
        while True:
            cursor, keys = self.r.scan(cursor=cursor, match=pattern, count=500)
            if keys:
                self.r.delete(*keys)
            if cursor == 0:
                break
