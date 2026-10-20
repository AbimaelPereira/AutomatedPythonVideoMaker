"""Limite de concorrência + RPM por provider, e backoff para 429/5xx."""
import random
import re
import threading
import time
from collections import deque

# Defaults conservadores. Sobrescrever em global_settings.ai.rate_limits.<provider>.
DEFAULT_LIMITS = {
    "pollinations": {"max_concurrent": 2, "rpm": 20},  # API gratuita; 429 frequente acima disso
    "modelscope": {"max_concurrent": 1, "rpm": 10},    # cota por conta, fila assíncrona
    "download": {"max_concurrent": 8, "rpm": None},    # CDNs aguentam; limita só sockets
}
FALLBACK_LIMIT = {"max_concurrent": 2, "rpm": 20}
BACKOFF_DELAYS = (2, 4, 8, 16)


class ProviderLimiter:
    def __init__(self, max_concurrent: int, rpm: int | None, *,
                 clock=time.monotonic, sleep=time.sleep):
        self.max_concurrent = max(1, int(max_concurrent))
        self.rpm = int(rpm) if rpm else None
        self._sem = threading.BoundedSemaphore(self.max_concurrent)
        self._lock = threading.Lock()
        self._calls = deque()
        self._clock = clock
        self._sleep = sleep

    def _wait_rpm(self):
        if not self.rpm:
            return
        while True:
            with self._lock:
                now = self._clock()
                while self._calls and now - self._calls[0] >= 60:
                    self._calls.popleft()
                if len(self._calls) < self.rpm:
                    self._calls.append(now)
                    return
                wait = 60 - (now - self._calls[0])
            print(f"[Prepare] rate limit: aguardando {wait:.1f}s (rpm={self.rpm})")
            self._sleep(wait)

    def __enter__(self):
        self._sem.acquire()
        try:
            self._wait_rpm()
        except BaseException:
            self._sem.release()
            raise
        return self

    def __exit__(self, *exc):
        self._sem.release()
        return False


_limiters: dict = {}
_limiters_lock = threading.Lock()


def limiter_for(provider: str, gs: dict | None = None) -> ProviderLimiter:
    """Singleton por provider no processo; a 1ª config vista vale até o fim."""
    provider = provider or "pollinations"
    with _limiters_lock:
        if provider not in _limiters:
            cfg = dict(DEFAULT_LIMITS.get(provider, FALLBACK_LIMIT))
            override = (((gs or {}).get("ai") or {}).get("rate_limits") or {}).get(provider) or {}
            cfg.update({k: v for k, v in override.items() if k in ("max_concurrent", "rpm")})
            _limiters[provider] = ProviderLimiter(cfg["max_concurrent"], cfg.get("rpm"))
        return _limiters[provider]


def reset_limiters():
    with _limiters_lock:
        _limiters.clear()


_RETRYABLE_TEXT = re.compile(r"\b(429|5\d\d)\b|rate.?limit|too many requests", re.I)


def is_retryable_result(result) -> bool:
    """Falha de provider por 429 / rate limit / 5xx."""
    if not isinstance(result, dict) or result.get("success"):
        return False
    status = result.get("status_code")
    if status is not None:
        return status == 429 or 500 <= int(status) < 600
    return bool(_RETRYABLE_TEXT.search(str(result.get("error", ""))))


def call_with_backoff(fn, *, is_retryable=is_retryable_result, sleep=time.sleep,
                      delays=BACKOFF_DELAYS, max_attempts: int = 4,
                      jitter=lambda: random.uniform(0, 0.5)):
    """Chama `fn` até `max_attempts` vezes enquanto o resultado for retryable.

    Espera `retry_after` do resultado (se o provider expuser) ou o próximo
    `delays[i]` + jitter.
    """
    result = None
    for attempt in range(max_attempts):
        result = fn()
        if not is_retryable(result) or attempt == max_attempts - 1:
            return result
        retry_after = result.get("retry_after") if isinstance(result, dict) else None
        wait = float(retry_after) if retry_after else delays[min(attempt, len(delays) - 1)] + jitter()
        print(f"[Prepare] provider sobrecarregado; nova tentativa em {wait:.1f}s")
        sleep(wait)
    return result
