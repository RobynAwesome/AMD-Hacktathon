"""One monotonic budget shared by all model steps in an HTTP request."""

from contextlib import contextmanager
from contextvars import ContextVar
import math
import os
import time


class BudgetExceeded(RuntimeError):
    pass


END: ContextVar[float | None] = ContextVar("goa_request_deadline", default=None)


def web_seconds() -> float:
    # Vercel's function is configured for 60s; leave time for fallback and response.
    try:
        value = float(os.environ.get("GOA_WEB_BUDGET", "40"))
        return min(40.0, max(0.01, value)) if math.isfinite(value) else 40.0
    except ValueError:
        return 40.0


@contextmanager
def budget(seconds: float):
    token = END.set(time.monotonic() + seconds)
    try:
        yield
    finally:
        END.reset(token)


def remaining(cap: float | None = None) -> float | None:
    end = END.get()
    if end is None:
        return cap
    left = end - time.monotonic()
    if left <= 0:
        raise BudgetExceeded("The request's model budget expired.")
    return min(left, cap) if cap is not None else left


def pause(seconds: float) -> None:
    left = remaining()
    if left is not None and seconds >= left:
        raise BudgetExceeded("Retry wait exceeds the remaining request budget.")
    time.sleep(seconds)
