import time
import asyncio


class RateLimiter:
    """
    Một lớp đơn giản để giới hạn số lần gọi trong một khoảng thời gian.
    An toàn để sử dụng trong môi trường asyncio.
    """

    def __init__(self, max_calls: int, period_seconds: int):
        self.max_calls = max_calls
        self.period_seconds = period_seconds
        self._call_count = 0
        self._start_time = time.time()
        self._lock = asyncio.Lock()

    async def is_limited(self) -> bool:
        async with self._lock:
            current_time = time.time()

            # Nếu đã qua khoảng thời gian giới hạn, reset lại
            if current_time - self._start_time >= self.period_seconds:
                self._start_time = current_time
                self._call_count = 0

            # Kiểm tra số lần gọi
            if self._call_count >= self.max_calls:
                return True  # Đã vượt limit, cần skip

            # Nếu chưa vượt limit, tăng biến đếm và cho phép thực thi
            self._call_count += 1
            return False
