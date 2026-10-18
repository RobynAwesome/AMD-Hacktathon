"""Merchant gap view: what people asked for that nobody in reach could supply."""

from __future__ import annotations

import json
from collections import Counter, defaultdict

from goa.catalogue import Catalogue
from goa.compose import GAPS_LOG

REASONS = {
    "no_match": "nobody stocks it",
    "out_of_stock_in_size": "out of stock in the sizes asked for",
    "too_slow": "does not arrive before the event",
}


def _key(e: dict) -> str:
    colour = (e["colour_families"] or [""])[0]
    material = (e["materials"] or [""])[0]
    return " ".join(x for x in [colour, material, e["slot"].replace("_", " ")] if x)


def load_entries() -> list[dict]:
    if not GAPS_LOG.exists():
        return []
    return [json.loads(line) for line in GAPS_LOG.read_text().splitlines() if line.strip()]


def ranked(cat: Catalogue, market: str | None = None, looks_total: int | None = None) -> list[dict]:
    entries = [e for e in load_entries() if market in (None, e["market"])]
    groups: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        groups[_key(e)].append(e)
    rows = []
    for key, es in groups.items():
        reasons = Counter(e["reason"] for e in es)
        markets = Counter(e["market"] for e in es)
        top_reason = reasons.most_common(1)[0][0]
        rows.append({
            "want": key, "count": len(es), "markets": dict(markets), "reason": top_reason,
            "reason_text": REASONS.get(top_reason, top_reason),
            "examples": list(dict.fromkeys(e["description"] for e in es))[:3],
            "headline": (f"{len(es)}{' of ' + str(looks_total) if looks_total else ''} looks wanted a {key}; "
                         f"{REASONS.get(top_reason, top_reason)}."),
        })
    rows.sort(key=lambda r: r["count"], reverse=True)
    return rows
