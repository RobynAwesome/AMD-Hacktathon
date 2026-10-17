"""Client for any OpenAI-compatible chat endpoint. AMD Token Factory in the demo.

Config comes from env vars (or .env):
  TOKEN_FACTORY_BASE_URL, TOKEN_FACTORY_API_KEY, GEMMA_MODEL
A stand-in such as Google AI Studio works by changing these values only.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


class LLMConfigError(RuntimeError):
    pass


@dataclass
class LLMReply:
    text: str
    latency_ms: int
    model: str
    base_url: str


def config() -> tuple[str, str, str]:
    base_url = os.environ.get("TOKEN_FACTORY_BASE_URL", "").rstrip("/")
    key = os.environ.get("TOKEN_FACTORY_API_KEY", "")
    model = os.environ.get("GEMMA_MODEL", "gemma-4-31b-it")
    if not base_url or not key:
        raise LLMConfigError(
            "Set TOKEN_FACTORY_BASE_URL and TOKEN_FACTORY_API_KEY in .env or the environment."
        )
    return base_url, key, model


def is_token_factory(base_url: str) -> bool:
    return "googleapis.com" not in base_url and "openrouter.ai" not in base_url and "localhost" not in base_url


def chat(messages: list[dict], json_mode: bool = True, timeout: float = 60.0) -> LLMReply:
    base_url, key, model = config()
    body = {"model": model, "messages": messages, "temperature": 0}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {key}"}
    start = time.perf_counter()
    r = httpx.post(f"{base_url}/chat/completions", json=body, headers=headers, timeout=timeout)
    if r.status_code == 400 and json_mode:
        # Some endpoints reject response_format; the prompt still asks for JSON.
        body.pop("response_format")
        r = httpx.post(f"{base_url}/chat/completions", json=body, headers=headers, timeout=timeout)
    r.raise_for_status()
    latency_ms = int((time.perf_counter() - start) * 1000)
    text = r.json()["choices"][0]["message"]["content"] or ""
    return LLMReply(text=text, latency_ms=latency_ms, model=model, base_url=base_url)


def list_models() -> list[str]:
    base_url, key, _ = config()
    r = httpx.get(f"{base_url}/models", headers={"Authorization": f"Bearer {key}"}, timeout=30)
    r.raise_for_status()
    return [m["id"] for m in r.json().get("data", [])]
