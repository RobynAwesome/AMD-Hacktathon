"""Token Factory usage: rate limiting, spend guard and a call log, with per-process limits, not a global shared-key guarantee.

Guard levels (from the spend remaining on the key, read from X-RateLimit-* headers and GET /v1/usage):
  normal       all steps call the model
  essential    under GOA_GUARD_ESSENTIAL (default 25%) remaining: only brief and enquiry call the model;
               other steps use their labelled templates
  cache_only   under GOA_GUARD_CACHE_ONLY (default 10%) remaining, or GOA_CACHE_ONLY=1: nothing calls
               the model; answers come from the cache or templates
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from pathlib import Path

from goa.catalogue import CACHE_ROOT, ROOT

CALLS_LOG = CACHE_ROOT / "calls.jsonl"
ESSENTIAL_STEPS = {"brief", "enquiry"}


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


class RateLimiter:
    """At most `per_minute` starts in any 60 s window and `concurrent` calls in flight. Callers wait, never fail."""

    def __init__(self, per_minute: int, concurrent: int, clock=time.monotonic, sleep=time.sleep):
        self.per_minute = per_minute
        self.slots = threading.BoundedSemaphore(concurrent)
        self.starts: deque[float] = deque()
        self.lock = threading.Lock()
        self.clock, self.sleep = clock, sleep

    def acquire(self, timeout: float | None = None) -> None:
        started = self.clock()
        if not self.slots.acquire(timeout=timeout):
            raise TimeoutError("No model slot within the request budget")
        try:
            while True:
                with self.lock:
                    now = self.clock()
                    while self.starts and now - self.starts[0] >= 60:
                        self.starts.popleft()
                    if len(self.starts) < self.per_minute:
                        self.starts.append(now)
                        return
                    wait = 60 - (now - self.starts[0]) + 0.05
                if timeout is not None and wait >= timeout - (self.clock() - started):
                    raise TimeoutError("Rate limit wait exceeds the request budget")
                self.sleep(wait)
        except BaseException:
            self.slots.release()
            raise

    def release(self) -> None:
        self.slots.release()


LIMITER = RateLimiter(int(_float_env("GOA_RPM", 15)), int(_float_env("GOA_CONCURRENCY", 4)))


class Usage:
    """What we know about the key's remaining spend. Updated from response headers and /v1/usage."""

    def __init__(self):
        self.limit: float | None = None
        self.remaining: float | None = None
        self.reset: str | None = None
        self.rpm: str | None = None
        self.checked_at: float = 0.0
        self.raw: dict = {}

    def fraction_remaining(self) -> float | None:
        if self.limit and self.remaining is not None and self.limit > 0:
            return max(0.0, min(1.0, self.remaining / self.limit))
        return None

    def update_from_headers(self, headers) -> None:
        """Read X-RateLimit-* headers. Spend headers are preferred; names vary, so match loosely."""
        h = {k.lower(): v for k, v in dict(headers).items() if k.lower().startswith("x-ratelimit")}
        if not h:
            return
        self.raw.update(h)

        def pick(*words):
            for k, v in h.items():
                if all(w in k for w in words):
                    try:
                        return float(v)
                    except ValueError:
                        continue
            return None

        limit = pick("limit", "spend") or pick("limit", "budget") or pick("limit", "quota")
        remaining = pick("remaining", "spend") or pick("remaining", "budget") or pick("remaining", "quota")
        if limit is not None and remaining is not None:
            self.limit, self.remaining = limit, remaining
        rpm = h.get("x-ratelimit-remaining-requests") or h.get("x-ratelimit-remaining")
        if rpm:
            self.rpm = rpm
        self.checked_at = time.time()

    def update_from_usage(self, data: dict) -> None:
        """GET /v1/usage. Field names are matched loosely: total/quota/limit, used, remaining, reset."""
        flat = dict(data)
        for v in data.values():
            if isinstance(v, dict):
                flat.update(v)
        num = lambda *keys: next((float(flat[k]) for k in keys if isinstance(flat.get(k), (int, float))), None)  # noqa: E731
        total = num("daily_cost_limit_usd", "total_quota", "quota", "total", "limit", "daily_limit")
        used = num("daily_cost_used_usd", "used", "used_amount", "spent")
        remaining = num("daily_cost_remaining_usd", "remaining", "remaining_amount", "balance")
        if remaining is None and total is not None and used is not None:
            remaining = total - used
        if total is not None and remaining is not None:
            self.limit, self.remaining = total, remaining
        reset = flat.get("daily_reset_at") or flat.get("reset_at") or flat.get("reset_time") or flat.get("reset")
        tz = flat.get("daily_reset_timezone")
        self.reset = f"{reset} {tz}".strip() if reset and tz else str(reset or self.reset or "")
        rpm = flat.get("rpm_limit") or flat.get("rpm")
        if rpm:
            self.rpm = str(rpm)
            # Stay at least 5 requests a minute under the key's real limit, and never above our default.
            LIMITER.per_minute = max(1, min(LIMITER.per_minute, int(float(rpm)) - 5))
        self.raw = {k: v for k, v in flat.items() if not isinstance(v, (list, dict))}
        self.checked_at = time.time()


USAGE = Usage()


def guard_level() -> str:
    if os.environ.get("GOA_CACHE_ONLY") == "1":
        return "cache_only"
    frac = USAGE.fraction_remaining()
    if frac is None:
        return "normal"
    if frac < _float_env("GOA_GUARD_CACHE_ONLY", 0.10):
        return "cache_only"
    if frac < _float_env("GOA_GUARD_ESSENTIAL", 0.25):
        return "essential"
    return "normal"


def allowed(step: str) -> tuple[bool, str]:
    level = guard_level()
    if level == "cache_only":
        return False, "cache only: usage guard or GOA_CACHE_ONLY"
    if level == "essential" and step not in ESSENTIAL_STEPS:
        return False, "usage guard: saving the remaining quota for brief and enquiry"
    return True, ""


def log_call(step: str, provider: str, model: str, cached: bool, latency_ms: int = 0,
             tokens_in: int | None = None, tokens_out: int | None = None, error: str | None = None) -> None:
    """One line per model call. Token counts only, never prompt or reply text."""
    try:
        CALLS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with CALLS_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": int(time.time()), "step": step, "provider": provider, "model": model,
                                "cached": cached, "latency_ms": latency_ms, "tokens_in": tokens_in,
                                "tokens_out": tokens_out, "error": error, "guard": guard_level()}) + "\n")
    except OSError:
        pass


def recent_calls(n: int = 20) -> list[dict]:
    if not CALLS_LOG.exists():
        return []
    lines = CALLS_LOG.read_text().splitlines()[-n:]
    return [json.loads(x) for x in lines if x.strip()]


def summary() -> dict:
    calls = recent_calls(10_000)
    live = [c for c in calls if not c["cached"] and not c.get("error")]
    return {
        "guard": guard_level(),
        "fraction_remaining": USAGE.fraction_remaining(),
        "limit": USAGE.limit, "remaining": USAGE.remaining, "reset": USAGE.reset, "rpm": USAGE.rpm,
        "checked_at": USAGE.checked_at,
        "calls_live": len(live), "calls_cached": sum(1 for c in calls if c["cached"]),
        "tokens_in": sum(c.get("tokens_in") or 0 for c in live),
        "tokens_out": sum(c.get("tokens_out") or 0 for c in live),
        "limiter": {"per_minute": LIMITER.per_minute, "scope": "process_only"},
        "persistence": "transient_instance",
        "quota_known": USAGE.fraction_remaining() is not None,
    }
