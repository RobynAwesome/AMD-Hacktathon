"""Gemma / AMD Token Factory adapter with schema validation, one retry and honest fallback.

Invariants:
- Never invents endpoints, model IDs, API keys, successful calls or latency numbers.
- Checks `LLMProviderConfig.is_configured` before any network call.
- Validates LLM JSON against `CreativeBrief`; retries once on invalid JSON/schema error,
  then falls back to `parse_brief_rule_based` (`InterpretationSource.RULE_BASED_FALLBACK`).
- Never allows the model to invent prices, stock, delivery promises or unstated sizes.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from typing import Any

import httpx
from pydantic import ValidationError

from goa.brief import apply_customer_sizes, parse_brief_rule_based
from goa.config import LLMProviderConfig, load_llm_config
from goa.schemas import (
    Composition,
    CreativeBrief,
    InterpretationSource,
    PartType,
)


@dataclass
class LLMCallReceipt:
    operation: str
    timestamp: str
    provider_configured: bool
    base_url: str | None
    model: str | None
    attempted_live_call: bool
    attempts: int
    succeeded: bool
    fallback_used: bool
    interpretation_source: str
    latency_ms: float | None
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = [ln for ln in stripped.splitlines() if not ln.strip().startswith("```")]
        stripped = "\n".join(lines).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in model output")
    return json.loads(stripped[start : end + 1])


def interpret_brief(
    raw_prompt: str,
    *,
    brief_id: str = "brf_session",
    session_id: str = "ses_default",
    reference_date: date = date(2026, 10, 18),
    customer_sizes: dict[PartType, str] | None = None,
    config: LLMProviderConfig | None = None,
    http_client: httpx.Client | None = None,
    now: datetime | None = None,
) -> tuple[CreativeBrief, LLMCallReceipt]:
    """Interpret `raw_prompt` via AMD Token Factory Gemma if configured, else rule-based fallback.

    Schema-validates the model response against `CreativeBrief`, retries once on
    validation failure, and falls back deterministically if unconfigured or if both
    attempts fail.
    """
    ts = now or datetime.now(timezone.utc)
    cfg = config or load_llm_config()

    if not cfg.is_configured:
        brief = parse_brief_rule_based(
            raw_prompt,
            brief_id=brief_id,
            session_id=session_id,
            reference_date=reference_date,
            customer_sizes=customer_sizes,
            now=ts,
        )
        receipt = LLMCallReceipt(
            operation="interpret_brief",
            timestamp=ts.isoformat(),
            provider_configured=False,
            base_url=cfg.base_url,
            model=cfg.model,
            attempted_live_call=False,
            attempts=0,
            succeeded=False,
            fallback_used=True,
            interpretation_source=InterpretationSource.RULE_BASED_FALLBACK.value,
            latency_ms=None,
            error="LLM provider not configured (missing base_url, api_key or model env var).",
        )
        return brief, receipt

    assert cfg.base_url and cfg.api_key and cfg.model
    endpoint = f"{cfg.base_url.rstrip('/')}/chat/completions"
    system_prompt = (
        "You are the GOA Creative Commerce brief interpreter. Convert the user's graduation "
        "outfit description into a strict JSON object matching the GOA CreativeBrief v1.0.0 "
        "schema. Never invent garment or shoe sizes that the user did not state. All money "
        "is integer ZAR cents."
    )

    last_error: str | None = None
    attempts = 0
    t_start = time.perf_counter()
    close_client = http_client is None
    client = http_client or httpx.Client(timeout=cfg.timeout_seconds)

    try:
        for attempt in range(1, 3):  # initial attempt + at most 1 retry
            attempts = attempt
            user_msg = raw_prompt
            if last_error:
                user_msg = (
                    f"{raw_prompt}\n\nPrevious JSON failed schema validation: {last_error}. "
                    "Return only a valid CreativeBrief JSON object."
                )
            try:
                resp = client.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {cfg.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": cfg.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_msg},
                        ],
                        "temperature": 0.1,
                        "max_tokens": 1024,
                        "stream": False,
                    },
                )
                resp.raise_for_status()
                body = resp.json()
                content = body["choices"][0]["message"]["content"]
                parsed = _extract_json_object(content)
                parsed["brief_id"] = brief_id
                parsed["session_id"] = session_id
                parsed["raw_prompt"] = raw_prompt
                parsed["interpretation_source"] = InterpretationSource.GEMMA_AMD_TOKEN_FACTORY.value
                parsed.setdefault("created_at", ts.isoformat())
                for part in parsed.get("requested_parts", []):
                    part["brief_id"] = brief_id

                brief = CreativeBrief.model_validate(parsed)
                if customer_sizes:
                    brief = apply_customer_sizes(brief, customer_sizes)
                latency_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
                return brief, LLMCallReceipt(
                    operation="interpret_brief",
                    timestamp=ts.isoformat(),
                    provider_configured=True,
                    base_url=cfg.base_url,
                    model=cfg.model,
                    attempted_live_call=True,
                    attempts=attempts,
                    succeeded=True,
                    fallback_used=False,
                    interpretation_source=InterpretationSource.GEMMA_AMD_TOKEN_FACTORY.value,
                    latency_ms=latency_ms,
                    error=None,
                )
            except (httpx.HTTPError, KeyError, ValueError, ValidationError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
    finally:
        if close_client:
            client.close()

    latency_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
    fallback_brief = parse_brief_rule_based(
        raw_prompt,
        brief_id=brief_id,
        session_id=session_id,
        reference_date=reference_date,
        customer_sizes=customer_sizes,
        now=ts,
    )
    return fallback_brief, LLMCallReceipt(
        operation="interpret_brief",
        timestamp=ts.isoformat(),
        provider_configured=True,
        base_url=cfg.base_url,
        model=cfg.model,
        attempted_live_call=True,
        attempts=attempts,
        succeeded=False,
        fallback_used=True,
        interpretation_source=InterpretationSource.RULE_BASED_FALLBACK.value,
        latency_ms=latency_ms,
        error=last_error,
    )


def explain_verified_composition(
    brief: CreativeBrief,
    composition: Composition,
) -> dict[str, str]:
    """Generate grounded explanations for each selected part using only verified facts."""
    explanations: dict[str, str] = {}
    for sp in composition.selected_parts:
        attrs = ", ".join(a.split(":", 1)[-1] for a in sp.matched_attributes[:4])
        explanations[sp.part_id] = (
            f"Matches your {brief.occasion or 'event'} brief ({attrs}); "
            f"verified in size {sp.size} at R{sp.unit_price_cents / 100:.2f} from {sp.merchant_id}."
        )
    return explanations
