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
    """One quote request per merchant in the look, all written in a single model call.
    Facts come from the verified look; the model only writes the messages."""
    chosen = [p.options[i] for p, i in zip(look.parts, look.chosen) if i is not None]
    by_merchant: dict[str, list] = {}
    for o in chosen:
        by_merchant.setdefault(o.merchant_id, []).append(o)
    facts = {"occasion": brief.occasion, "event_date": str(brief.event_date) if brief.event_date else None,
             "ship_to": look.market, "note": note,
             "merchants": {mid: {"name": cat.merchants[mid].name, "items": [o.name for o in offers]}
                           for mid, offers in by_merchant.items()}}
    system = ("For each merchant, write a short, warm, professional quote request from a shopper. Ask them to "
              "confirm availability, sizes and a final quote including delivery. Do not state any prices or "
              "delivery times yourself. Under 100 words each. Return JSON: {\"<merchant id>\": \"message\", ...}")
    messages, source, ms = {}, "template", 0
    try:
        reply = _call("enquiry", system, json.dumps(facts))
        messages = {k: str(v).strip() for k, v in _extract_json(reply.text).items() if k in by_merchant}
        source, ms = reply.provider, reply.latency_ms
    except Exception:
        pass
    out = []
    for mid, offers in by_merchant.items():
        m = cat.merchants[mid]
        lines = [{"item_id": o.item_id, "name": o.name, "size": o.size or "to confirm",
                  "price": o.price_original, "currency": o.currency_original} for o in offers]
        ship = m.ships_to[look.market]
        body = messages.get(mid) or (
            f"Hello {m.name}, I would like a quote for the items below for a {brief.occasion}"
            + (f" on {brief.event_date}" if brief.event_date else "")
            + ". Please confirm availability in my sizes and a final price including delivery. Thank you.")
        out.append({
            "ts": int(time.time()), "merchant_id": mid, "merchant": m.name, "to": m.email,
            "from": contact_name or "GOA shopper", "market": look.market, "event_date": facts["event_date"],
            "items": lines, "subtotal": round(sum(x["price"] for x in lines), 2), "currency": m.currency,
            "shipping": ship.cost, "delivery_days": ship.days, "message": body,
            "message_source": source if mid in messages else "template", "latency_ms": ms,
            "status": "sent to merchant inbox (demo, not emailed)",
        })
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
    # One user message with the image, no system role: Gemma's chat template handles images most reliably this way,
    # the same shape catalogue/vision_tag.py uses. The page combines up to 3 photos into one image before sending.
    prompt = ("Describe the outfit style in this photo for a shopping brief: colours, fabrics, silhouettes, formality. "
              "Reply with JSON only: {\"notes\": \"one or two sentences\"}")
    msgs = [{"role": "user", "content": prompt}]
    try:
        reply = llm.chat("vision", msgs, json_mode=True, images=images[:3])
    except Exception:
        reply = llm.chat("vision", msgs, json_mode=False, images=images[:1])  # one retry: plain text, first image only
    try:
        notes = _extract_json(reply.text).get("notes", "")
    except Exception:
        notes = ""
    notes = notes or reply.text.strip()[:400]
    return Narration(notes, reply.provider, reply.latency_ms, reply.model)


def as_dict(n: Narration) -> dict:
    return asdict(n)
