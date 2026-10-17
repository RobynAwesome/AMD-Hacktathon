"""Configuration boundary for GOA Creative Commerce (Correction D).

Resolves one primary configuration contract (`GOA_LLM_*`) with documented aliases
from Busi's architecture (`TOKEN_FACTORY_*`, `GEMMA_MODEL`, `RADEON_API_KEY`).
Never invents endpoints, model identifiers or credentials: unset values remain None
and are reported as UNKNOWN / unconfigured.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
EVIDENCE_DIR = ROOT_DIR / "evidence"

BASE_URL_ENV_ORDER: tuple[str, ...] = ("GOA_LLM_BASE_URL", "TOKEN_FACTORY_BASE_URL")
API_KEY_ENV_ORDER: tuple[str, ...] = ("GOA_LLM_API_KEY", "TOKEN_FACTORY_API_KEY", "RADEON_API_KEY")
MODEL_ENV_ORDER: tuple[str, ...] = ("GOA_LLM_MODEL", "GEMMA_MODEL")


def _first_present(env: Mapping[str, str], names: tuple[str, ...]) -> tuple[str | None, str | None]:
    for name in names:
        val = env.get(name, "").strip()
        if val:
            return val, name
    return None, None


@dataclass(frozen=True)
class LLMProviderConfig:
    """Resolved LLM provider configuration with provenance and no secret exposure."""

    base_url: str | None
    base_url_source_env: str | None
    api_key: str | None
    api_key_source_env: str | None
    model: str | None
    model_source_env: str | None
    timeout_seconds: float = 20.0

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def public_summary(self) -> dict[str, object]:
        """Safe, redactable summary suitable for logs, API responses and receipts."""
        return {
            "is_configured": self.is_configured,
            "base_url": self.base_url,
            "base_url_source_env": self.base_url_source_env,
            "model": self.model,
            "model_source_env": self.model_source_env,
            "api_key_present": bool(self.api_key),
            "api_key_source_env": self.api_key_source_env,
            "primary_contract": {
                "base_url": "GOA_LLM_BASE_URL",
                "api_key": "GOA_LLM_API_KEY",
                "model": "GOA_LLM_MODEL",
            },
            "accepted_aliases": {
                "base_url": list(BASE_URL_ENV_ORDER[1:]),
                "api_key": list(API_KEY_ENV_ORDER[1:]),
                "model": list(MODEL_ENV_ORDER[1:]),
            },
        }


def load_llm_config(env: Mapping[str, str] | None = None) -> LLMProviderConfig:
    source = os.environ if env is None else env
    base_url, base_src = _first_present(source, BASE_URL_ENV_ORDER)
    api_key, key_src = _first_present(source, API_KEY_ENV_ORDER)
    model, model_src = _first_present(source, MODEL_ENV_ORDER)
    timeout_raw = source.get("GOA_LLM_TIMEOUT_SECONDS", "").strip()
    timeout = float(timeout_raw) if timeout_raw else 20.0
    return LLMProviderConfig(
        base_url=base_url,
        base_url_source_env=base_src,
        api_key=api_key,
        api_key_source_env=key_src,
        model=model,
        model_source_env=model_src,
        timeout_seconds=timeout,
    )
