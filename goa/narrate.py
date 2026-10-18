"""Model-written words around verified facts: why each item fits, the enquiry text, ideas, mood photo notes.

The model writes prose only. Prices, dates, sizes and stock are inserted by code. When the model
call fails, a plain template is used and marked as such, so nothing pretends to be model output.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass

from goa import llm
from goa.brief import _extract_json
from goa.catalogue import ROOT, Catalogue
from goa.compose import Look
from goa.schemas import Brief

ENQUIRIES_LOG = ROOT / "cache" / "enquiries.jsonl"


@dataclass
class Narration:
    text: dict | str | list
    source: str  # provider name, or "template"
    latency_ms: int = 0
    model: str = ""


def _call(step: str, system: str, user: str, json_mode: bool = True, images=None) -> llm.LLMReply:
    return llm.chat(step, [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    json_mode=json_mode, images=images)


def explain(cat: Catalogue, look: Look, brief: Brief) -> Narration:
    """One short line per chosen item on why it fits the brief."""
    chosen = [p.options[i] for p, i in zip(look.parts, look.chosen) if i is not None]
    facts = [{"id": o.item_id, "name": o.name, "merchant": o.merchant, "city": o.city,
              "colours": cat.by_id[o.item_id].colours, "materials": cat.by_id[o.item_id].materials,
              "formality": cat.by_id[o.item_id].formality.value, "part": o.slot} for o in chosen]
    system = ("You are a stylist. For each item, write one short sentence on why it suits the person's brief. "
              "Never mention prices, dates, delivery or stock. Return JSON: {\"<id>\": \"sentence\", ...}")
    user = f"Brief: {brief.model_dump_json()}\nItems: {json.dumps(facts)}"
    try:
        reply = _call("explain", system, user)
        lines = _extract_json(reply.text)
        lines = {k: str(v) for k, v in lines.items() if k in {f['id'] for f in facts}}
        return Narration(lines, reply.provider, reply.latency_ms, reply.model)
    except Exception:
        lines = {f["id"]: f"{', '.join(f['colours']).capitalize()} {', '.join(f['materials'])}, "
                          f"{f['formality'].replace('_', ' ')}." for f in facts}
        return Narration(lines, "template")


def enquiry(cat: Catalogue, look: Look, brief: Brief, contact_name: str = "", note: str = "") -> list[dict]:
    """One quote request per merchant in the look. Facts come from the verified look; the model writes the message."""
    chosen = [p.options[i] for p, i in zip(look.parts, look.chosen) if i is not None]
    by_merchant: dict[str, list] = {}
    for o in chosen:
        by_merchant.setdefault(o.merchant_id, []).append(o)
    out = []
    for mid, offers in by_merchant.items():
        m = cat.merchants[mid]
        lines = [{"item_id": o.item_id, "name": o.name, "size": o.size or "to confirm",
                  "price": o.price_original, "currency": o.currency_original} for o in offers]
        ship = m.ships_to[look.market]
        facts = {"merchant": m.name, "items": [x["name"] for x in lines], "occasion": brief.occasion,
                 "event_date": str(brief.event_date) if brief.event_date else None, "ship_to": look.market,
                 "note": note}
        system = ("Write a short, warm, professional quote request from a shopper to a fashion merchant. "
                  "Ask them to confirm availability, sizes and a final quote including delivery. "
                  "Do not state any prices or delivery times yourself. Plain text, under 120 words.")
        try:
            reply = _call("enquiry", system, json.dumps(facts), json_mode=False)
            body, source, ms = reply.text.strip(), reply.provider, reply.latency_ms
        except Exception:
            body = (f"Hello {m.name}, I would like a quote for the items below for a {brief.occasion}"
                    + (f" on {brief.event_date}" if brief.event_date else "")
                    + ". Please confirm availability in my sizes and a final price including delivery. Thank you.")
            source, ms = "template", 0
        record = {
            "ts": int(time.time()), "merchant_id": mid, "merchant": m.name, "to": m.email,
            "from": contact_name or "GOA shopper", "market": look.market, "event_date": facts["event_date"],
            "items": lines, "subtotal": round(sum(x["price"] for x in lines), 2), "currency": m.currency,
            "shipping": ship.cost, "delivery_days": ship.days, "message": body, "message_source": source,
            "latency_ms": ms, "status": "sent to merchant inbox (demo, not emailed)",
        }
        out.append(record)
    ENQUIRIES_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ENQUIRIES_LOG.open("a") as f:
        for r in out:
            f.write(json.dumps(r) + "\n")
    return out


def ideas(occasion: str, market: str, notes: str = "") -> Narration:
    system = ("Suggest 3 distinct outfit directions for the occasion. Return JSON: "
              "{\"ideas\": [{\"title\": \"2 to 4 words\", \"brief\": \"one sentence the person could send as their brief\"}]}")
    try:
        reply = _call("ideas", system, f"Occasion: {occasion}. Market: {market}. Notes: {notes}")
        data = _extract_json(reply.text)["ideas"][:3]
        return Narration(data, reply.provider, reply.latency_ms, reply.model)
    except Exception:
        return Narration([
            {"title": "Rewearable colour", "brief": f"A {occasion} look in one strong colour I can wear again, comfortable all day."},
            {"title": "Local designer", "brief": f"A {occasion} outfit from an African designer, modern tailoring, statement accessory."},
            {"title": "Quiet classic", "brief": f"A neutral, classic {occasion} outfit with good shoes and a light layer."},
        ], "template")


def mood_notes(images: list[llm.Image]) -> Narration:
    """Describe up to 3 mood photos as style notes that get added to the brief text."""
    system = ("Describe the outfit style in these mood photos for a shopping brief: colours, fabrics, silhouettes, "
              "formality. Return JSON: {\"notes\": \"one or two sentences\"}")
    reply = _call("vision", system, "Mood photos attached.", images=images[:3])
    return Narration(_extract_json(reply.text).get("notes", ""), reply.provider, reply.latency_ms, reply.model)


def as_dict(n: Narration) -> dict:
    return asdict(n)
