import threading
import time

from libs.Prepare.RateLimiter import ProviderLimiter, call_with_backoff, is_retryable_result


def test_max_concurrent():
    limiter = ProviderLimiter(2, None)
    lock, current, peak = threading.Lock(), [0], [0]

    def task():
        with limiter:
            with lock:
                current[0] += 1
                peak[0] = max(peak[0], current[0])
            time.sleep(0.02)
            with lock:
                current[0] -= 1

    threads = [threading.Thread(target=task) for _ in range(10)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert peak[0] == 2


def test_rpm_quarta_chamada_espera():
    now = [0.0]
    sleeps = []

    def sleep(s):
        sleeps.append(s)
        now[0] += s

    limiter = ProviderLimiter(5, 3, clock=lambda: now[0], sleep=sleep)
    for _ in range(3):
        with limiter:
            pass
    assert sleeps == []
    with limiter:
        pass
    assert sleeps == [60.0]


def test_backoff_2_4_8_e_desiste():
    sleeps, calls = [], []

    def fn():
        calls.append(1)
        return {"success": False, "status_code": 429}

    result = call_with_backoff(fn, sleep=sleeps.append, jitter=lambda: 0)
    assert sleeps == [2, 4, 8]
    assert len(calls) == 4 and result["success"] is False


def test_retry_after_respeitado():
    sleeps = []
    results = iter([{"success": False, "status_code": 429, "retry_after": 7}, {"success": True}])
    assert call_with_backoff(lambda: next(results), sleep=sleeps.append, jitter=lambda: 0)["success"]
    assert sleeps == [7.0]


def test_is_retryable():
    assert is_retryable_result({"success": False, "status_code": 503})
    assert not is_retryable_result({"success": False, "status_code": 400})
    assert is_retryable_result({"success": False, "error": "HTTP 429: Too Many Requests"})
    assert not is_retryable_result({"success": False, "error": "prompt inválido"})
    assert not is_retryable_result({"success": True})
