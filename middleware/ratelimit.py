import time
import threading
from dataclasses import dataclass
from collections import defaultdict


@dataclass
class _Bucket:
    tokens: float
    last: float
    capacity: float
    rate: float


class TokenBucketLimiter:
    def __init__(self, global_rate: float, global_burst: int, client_rate: float, client_burst: int):
        now = time.time()
        self._lock = threading.Lock()
        self._global = _Bucket(tokens=global_burst, last=now, capacity=float(global_burst), rate=float(global_rate))
        self._clients = defaultdict(lambda: _Bucket(tokens=client_burst, last=now, capacity=float(client_burst), rate=float(client_rate)))

    def _refill(self, b: _Bucket, now: float):
        elapsed = max(0.0, now - b.last)
        b.tokens = min(b.capacity, b.tokens + elapsed * b.rate)
        b.last = now

    def allow(self, client_key: str) -> tuple[bool, int, int, int]:
        now = time.time()
        with self._lock:
            gb = self._global
            cb = self._clients[client_key]
            self._refill(gb, now)
            self._refill(cb, now)

            if gb.tokens >= 1.0 and cb.tokens >= 1.0:
                gb.tokens -= 1.0
                cb.tokens -= 1.0
                remaining = int(cb.tokens)
                return True, int(cb.capacity), max(0, remaining), 0

            # compute retry-after (seconds until next token available for either bucket shortage)
            need_g = max(0.0, 1.0 - gb.tokens)
            need_c = max(0.0, 1.0 - cb.tokens)
            wait_g = need_g / gb.rate if gb.rate > 0 else float('inf')
            wait_c = need_c / cb.rate if cb.rate > 0 else float('inf')
            retry_after = int(max(0.0, round(max(wait_g, wait_c))))
            remaining = int(cb.tokens)
            return False, int(cb.capacity), max(0, remaining), retry_after
