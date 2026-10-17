"""Free text to a structured Brief, using Gemma. Schema check plus one retry."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

from pydantic import ValidationError

from goa import llm
from goa.schemas import Brief

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache" / "briefs"
MARKETS = {m["code"]: m for m in json.loads((Path(__file__).parent / "markets.json").read_text())["markets"]}

THANDI = (
    "Graduation in Cape Town on 12 December, outdoor, warm. Green, elegant but not formal, "
    "something I can wear again. Budget R2,500."
)

SYSTEM = """You turn a person's description of an outfit they want into a JSON brief.
Return one JSON object only, no prose, with these keys:
  occasion (string), event_date (YYYY-MM-DD or null), location (string or null),
  market (string, use the given market code), setting (indoor/outdoor or null),
  weather (string or null),
  budget ({"amount": number, "currency": "ZAR"|"USD"|"GBP", "soft": bool} or null),
  size (string or null), shoe_size (string or null),
  colours (list), formality (casual|smart_casual|cocktail|formal|black_tie or null),
  style_notes (list), constraints (list),
  parts (list of 1 to 6 objects: {"slot": "garment"|"shoes"|"outer_layer"|"accessory",
         "description": string, "colours": list, "materials": list}).
Rules:
- Never invent a size, shoe size or budget. If the person did not say it, use null.
- budget is the total for the whole look. soft is true for words like "around" or "about".
- At most one part has slot "garment" (a dress, suit, jumpsuit or set). Zero is fine if they
  already have one.
- A date with no year means the next time that date comes after today. Never a past date.
- If the weather is not stated, infer it from the location, date and hemisphere, and say so
  in weather (for example "likely warm, summer in Cape Town").
- Suggest the parts a complete look needs for the occasion and weather, even if the person
  did not list them all.
"""


class BriefError(RuntimeError):
    pass


@dataclass
class BriefResult:
    brief: Brief
    attempts: int
    latency_ms: int
    model: str
    base_url: str
    cached: bool = False


ChatFn = Callable[[list[dict]], llm.LLMReply]


def _extract_json(text: str) -> dict:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            text = text[start : end + 1]
    return json.loads(text)


def _validate(text: str, today: date) -> Brief:
    brief = Brief.model_validate(_extract_json(text))
    brief.check_date(today)
    return brief


def _cache_path(text: str, market: str) -> Path:
    h = hashlib.sha256(f"{market}\n{text.strip()}".encode()).hexdigest()[:16]
    return CACHE_DIR / f"{h}.json"


def parse_brief(
    text: str,
    market: str = "ZA",
    today: date | None = None,
    chat_fn: ChatFn | None = None,
    use_cache: bool = True,
) -> BriefResult:
    if market not in MARKETS:
        raise ValueError(f"unknown market {market}")
    today = today or date.today()
    chat_fn = chat_fn or llm.chat
    path = _cache_path(text, market)
    if use_cache and path.exists():
        data = json.loads(path.read_text())
        return BriefResult(Brief.model_validate(data["brief"]), 0, 0, data["model"], data["base_url"], cached=True)

    m = MARKETS[market]
    user = (
        f"Today is {today.isoformat()}. Market: {market} ({m['name']}, currency {m['currency']}, "
        f"{m['hemisphere']}ern hemisphere, default city {m['default_city']}).\n\nDescription:\n{text}"
    )
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]

    total_ms = 0
    last_error = ""
    for attempt in (1, 2):
        reply = chat_fn(messages)
        total_ms += reply.latency_ms
        try:
            brief = _validate(reply.text, today)
        except (ValueError, ValidationError) as e:  # JSONDecodeError is a ValueError
            last_error = str(e)
            messages += [
                {"role": "assistant", "content": reply.text},
                {"role": "user", "content": f"That JSON failed validation:\n{last_error}\nReturn the corrected JSON object only."},
            ]
            continue
        if use_cache:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"brief": brief.model_dump(mode="json"), "model": reply.model, "base_url": reply.base_url}, indent=2))
        return BriefResult(brief, attempt, total_ms, reply.model, reply.base_url)

    raise BriefError(f"brief failed validation twice: {last_error}")
