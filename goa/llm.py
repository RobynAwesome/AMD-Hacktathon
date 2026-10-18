"""Provider-agnostic model calls. Each step (brief, vision, explain, enquiry, ideas) can use any provider.

Routing, from env vars (or .env):
  GOA_PROVIDER              default provider for every step (default: token_factory)
  GOA_PROVIDER_<STEP>       provider for one step, e.g. GOA_PROVIDER_IDEAS=anthropic
  GOA_MODEL_<STEP>          model for one step
  Token Factory key: TOKEN_FACTORY_API_KEY (or RADEON_API_KEY), base URL defaults to the shared endpoint.
  GOA_MODE                  dev (default) warns when a prize-locked step is routed away from its
                            provider; submission refuses to run
Providers and prize locks live in goa/providers.json.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from goa import usage

CONFIG = json.loads((Path(__file__).parent / "providers.json").read_text())
CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "llm"
# Output caps per step, so no call can run away with the shared quota. Gemma does not think by default.
MAX_TOKENS = {"brief": 1200, "explain": 600, "enquiry": 400, "ideas": 400, "vision": 300}
PROVIDERS = CONFIG["providers"]
STEPS = CONFIG["steps"]
LOCKS = CONFIG["prize_locks"]


class LLMConfigError(RuntimeError):
    pass


class LLMUnavailable(RuntimeError):
    """The usage guard or cache-only mode stopped a live call. Callers fall back to cache or templates."""


@dataclass
class Image:
    data: bytes
    mime: str = "image/jpeg"


@dataclass
class Route:
    step: str
    provider: str
    kind: str
    model: str
    base_url: str
    key: str
    locked_to: str | None = None


@dataclass
class LLMReply:
    text: str
    latency_ms: int
    model: str
    base_url: str
    step: str = ""
    provider: str = ""
    cached: bool = False


def _env(name: str) -> str:
    return os.environ.get(name, "") if name else ""


def mode() -> str:
    return os.environ.get("GOA_MODE", "dev")


def route(step: str) -> Route:
    if step not in STEPS:
        raise ValueError(f"unknown step {step}")
    name = _env(f"GOA_PROVIDER_{step.upper()}") or _env("GOA_PROVIDER") or "token_factory"
    if name not in PROVIDERS:
        raise LLMConfigError(f"unknown provider {name} for step {step}")
    p = PROVIDERS[name]
    model = _env(f"GOA_MODEL_{step.upper()}") or _env(p.get("model_env", "")) or p["model"]
    base_url = (_env(p.get("base_url_env", "")) or p.get("base_url", "")).rstrip("/")
    lock = LOCKS.get(step, {}).get("provider")
    key = _env(p.get("key_env", "")) or _env(p.get("key_env_alias", ""))
    return Route(step, name, p["kind"], model, base_url, key, lock)


def lock_problems() -> list[str]:
    out = []
    for step in STEPS:
        r = route(step)
        if r.locked_to and r.provider != r.locked_to:
            out.append(f"{step} is routed to {r.provider}, but {LOCKS[step]['why']} needs {r.locked_to}")
    return out


def check_submission() -> None:
    problems = lock_problems()
    if problems and mode() == "submission":
        raise LLMConfigError("Submission mode: " + "; ".join(problems))
    for p in problems:
        print(f"warning: {p}", file=sys.stderr)


def _require(r: Route) -> None:
    if r.kind == "openai_compat" and not r.base_url:
        raise LLMConfigError(f"Set the base URL for provider {r.provider} (step {r.step}).")
    if PROVIDERS[r.provider].get("key_env") and not r.key:
        raise LLMConfigError(
            f"Set {PROVIDERS[r.provider]['key_env']} for provider {r.provider} (step {r.step}), "
            "in .env or the environment."
        )
    if mode() == "submission" and r.locked_to and r.provider != r.locked_to:
        raise LLMConfigError(f"Submission mode: step {r.step} must use {r.locked_to} ({LOCKS[r.step]['why']}).")


def _post_with_backoff(url: str, body: dict, headers: dict, timeout: float, tries: int = 4):
    """Retry only 429 (shared team key: 30 RPM, 8 concurrent) and 502/503, honouring Retry-After."""
    for attempt in range(tries):
        resp = httpx.post(url, json=body, headers=headers, timeout=timeout)
        if resp.status_code not in (429, 502, 503) or attempt == tries - 1:
            return resp
        wait = float(resp.headers.get("retry-after", 0) or 0) or (2 ** attempt + random.random())
        time.sleep(min(wait, 60))
    return resp


def _openai_compat(r: Route, messages: list[dict], json_mode: bool, images: list[Image],
                   timeout: float) -> tuple[str, int | None, int | None]:
    msgs = [dict(m) for m in messages]
    if images:
        last = msgs[-1]
        parts = [{"type": "text", "text": last["content"]}] if isinstance(last["content"], str) else list(last["content"])
        for img in images:
            b64 = base64.b64encode(img.data).decode()
            parts.append({"type": "image_url", "image_url": {"url": f"data:{img.mime};base64,{b64}"}})
        last["content"] = parts
    body = {"model": r.model, "messages": msgs, "temperature": 0, "max_tokens": MAX_TOKENS.get(r.step, 600)}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {r.key}"} if r.key else {}
    resp = _post_with_backoff(f"{r.base_url}/chat/completions", body, headers, timeout)
    if resp.status_code == 400 and json_mode:
        # Some endpoints reject response_format; the prompt still asks for JSON.
        body.pop("response_format")
        resp = _post_with_backoff(f"{r.base_url}/chat/completions", body, headers, timeout)
    usage.USAGE.update_from_headers(getattr(resp, "headers", {}) or {})
    resp.raise_for_status()
    data = resp.json()
    u = data.get("usage") or {}
    return data["choices"][0]["message"]["content"] or "", u.get("prompt_tokens"), u.get("completion_tokens")


def _anthropic_request(r: Route, messages: list[dict], images: list[Image]) -> dict:
    """Map chat messages to a Claude Messages API request (system prompt goes in its own field)."""
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    msgs = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
    if images:
        last = msgs[-1]
        blocks = [{"type": "text", "text": last["content"]}] if isinstance(last["content"], str) else list(last["content"])
        for img in images:
            blocks.insert(0, {"type": "image", "source": {"type": "base64", "media_type": img.mime,
                                                          "data": base64.standard_b64encode(img.data).decode()}})
        last["content"] = blocks
    req = {"model": r.model, "max_tokens": 16000, "messages": msgs, "output_config": {"effort": "low"}}
    if system:
        req["system"] = system
    return req


def _anthropic(r: Route, messages: list[dict], json_mode: bool, images: list[Image], timeout: float,
               client=None) -> tuple[str, int | None, int | None]:
    try:
        import anthropic
    except ImportError as e:
        raise LLMConfigError("pip install anthropic to use the anthropic provider") from e
    client = client or anthropic.Anthropic(api_key=r.key or None, timeout=timeout)
    req = _anthropic_request(r, messages, images)
    # Server-side fallback: if the model declines, the API reruns the request on a fallback model.
    resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], extra_body={"fallbacks": "default"}, **req)
    if resp.stop_reason == "refusal":
        raise RuntimeError("the model declined this request")
    u = getattr(resp, "usage", None)
    text = "".join(b.text for b in resp.content if b.type == "text")
    return text, getattr(u, "input_tokens", None), getattr(u, "output_tokens", None)


def _parses(text: str) -> bool:
    start, end = text.find("{"), text.rfind("}")
    try:
        json.loads(text[start:end + 1])
        return True
    except ValueError:
        return False


def _cache_key(r: Route, messages: list[dict], json_mode: bool, images: list[Image]) -> str:
    h = hashlib.sha256()
    h.update(json.dumps([r.step, r.provider, r.model, json_mode, messages], sort_keys=True).encode())
    for img in images:
        h.update(hashlib.sha256(img.data).digest())
    return h.hexdigest()[:24]


def chat(step: str, messages: list[dict], json_mode: bool = True, images: list[Image] | None = None,
         timeout: float = 90.0, use_cache: bool = True) -> LLMReply:
    """One model call, through the cache, the usage guard and the rate limiter, in that order."""
    r = route(step)
    images = images or []
    path = CACHE_DIR / f"{_cache_key(r, messages, json_mode, images)}.json"
    if use_cache and path.exists():
        hit = json.loads(path.read_text())
        usage.log_call(step, r.provider, r.model, cached=True)
        return LLMReply(text=hit["text"], latency_ms=0, model=r.model, base_url=r.base_url or r.provider,
                        step=step, provider=r.provider, cached=True)
    ok, why = usage.allowed(step)
    if not ok:
        raise LLMUnavailable(why)
    _require(r)
    usage.LIMITER.acquire()
    start = time.perf_counter()
    try:
        if r.kind == "anthropic":
            text, t_in, t_out = _anthropic(r, messages, json_mode, images, timeout)
        else:
            text, t_in, t_out = _openai_compat(r, messages, json_mode, images, timeout)
    except Exception as e:
        usage.log_call(step, r.provider, r.model, cached=False, error=type(e).__name__)
        raise
    finally:
        usage.LIMITER.release()
    latency_ms = int((time.perf_counter() - start) * 1000)
    usage.log_call(step, r.provider, r.model, cached=False, latency_ms=latency_ms, tokens_in=t_in, tokens_out=t_out)
    if use_cache and text.strip() and (not json_mode or _parses(text)):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"text": text, "step": step, "model": r.model, "ts": int(time.time())}))
    return LLMReply(text=text, latency_ms=latency_ms, model=r.model, base_url=r.base_url or r.provider,
                    step=step, provider=r.provider)


def refresh_usage() -> dict | None:
    """GET /v1/usage on Token Factory. Returns the raw body, or None if no key or it fails."""
    r = route("brief")
    if r.provider != "token_factory" or not r.key:
        return None
    try:
        resp = httpx.get(f"{r.base_url}/usage", params={"include_recent": "true"},
                         headers={"Authorization": f"Bearer {r.key}"}, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None
    usage.USAGE.update_from_usage(data)
    return data


def list_models(provider: str | None = None) -> list[str]:
    name = provider or route("brief").provider
    p = PROVIDERS[name]
    key = _env(p.get("key_env", ""))
    if p["kind"] == "anthropic":
        import anthropic

        return [m.id for m in anthropic.Anthropic(api_key=key or None).models.list()]
    base_url = (_env(p.get("base_url_env", "")) or p.get("base_url", "")).rstrip("/")
    if not base_url:
        raise LLMConfigError(f"Set the base URL for provider {name}.")
    resp = httpx.get(f"{base_url}/models", headers={"Authorization": f"Bearer {key}"} if key else {}, timeout=30)
    resp.raise_for_status()
    return [m["id"] for m in resp.json().get("data", [])]
