"""Instant pre-read while Gemma works: plain code and CPU embeddings, no model calls.

Pulls what it safely can from the text (occasion, date, place, budget, colours, setting, sizes) as
editable chips, and shows a first glance of nearby catalogue pieces, labelled as not yet checked.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

import numpy as np

from goa import rules
from goa.catalogue import Catalogue
from goa.match import COLOUR_FAMILIES, _index, embed_query

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
OCCASIONS = {"graduation": "graduation", "wedding": "wedding guest", "interview": "interview",
             "dinner": "formal dinner", "gala": "formal dinner", "black tie": "formal dinner", "party": "party"}
CITIES = ["Cape Town", "Johannesburg", "Durban", "Pretoria", "Lagos", "Abuja", "New York", "Brooklyn",
          "Manhattan", "London", "Cotswolds", "Milan", "Lake Como", "Shenzhen", "Shanghai", "Beijing"]
CURRENCY = [(r"\bR\s?(\d[\d,\s]*)", "ZAR"), (r"(\d[\d,]*)\s?(?:rand|zar)\b", "ZAR"),
            (r"₦\s?(\d[\d,]*)", "NGN"), (r"(\d[\d,]*)\s?(?:naira|ngn)\b", "NGN"),
            (r"\$\s?(\d[\d,]*)", "USD"), (r"£\s?(\d[\d,]*)", "GBP"), (r"€\s?(\d[\d,]*)", "EUR"),
            (r"(\d[\d,]*)\s?(?:yuan|cny|rmb)\b", "CNY"), (r"¥\s?(\d[\d,]*)", "CNY")]


def _next_date(day: int, month: int, today: date) -> date | None:
    try:
        d = date(today.year, month, day)
    except ValueError:
        return None
    return d if d >= today else date(today.year + 1, month, day)


def chips(text: str, today: date) -> list[dict]:
    t = text.lower()
    out = []
    for word, occ in OCCASIONS.items():
        if word in t:
            out.append({"key": "occasion", "label": occ, "value": occ})
            break
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*", t) \
        or re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})\b", t)
    when = None
    if m:
        a, b = m.groups()
        day, mon = (int(a), b) if a.isdigit() else (int(b), a)
        when = _next_date(day, MONTHS[mon], today)
    elif "tomorrow" in t:
        when = today + timedelta(days=1)
    elif "next week" in t:
        when = today + timedelta(days=7)
    if when:
        out.append({"key": "event_date", "label": when.strftime("%d %b %Y"), "value": when.isoformat()})
    for city in CITIES:
        if city.lower() in t:
            out.append({"key": "location", "label": city, "value": city})
            break
    for pattern, ccy in CURRENCY:
        bm = re.search(pattern, text, re.I)
        if bm:
            amount = float(re.sub(r"[,\s]", "", bm.group(1)))
            if amount > 0:
                out.append({"key": "budget", "label": f"{ccy} {amount:,.0f}", "value": {"amount": amount, "currency": ccy}})
                break
    seen = []
    for words in COLOUR_FAMILIES.values():
        for w in words:
            if re.search(rf"\b{w}\b", t) and w not in seen:
                seen.append(w)
    for w in seen[:3]:
        out.append({"key": "colour", "label": w, "value": w})
    for word in ("outdoor", "indoor", "beach", "garden"):
        if word in t:
            out.append({"key": "setting", "label": word, "value": word})
            break
    sm = re.search(r"\b(xxs|xs|xl|xxl|size\s+\w+)\b", t)
    if sm:
        out.append({"key": "size", "label": sm.group(1).upper().replace("SIZE ", ""), "value": sm.group(1).replace("size ", "").upper()})
    return out


def first_glance(cat: Catalogue, text: str, market: str, n: int = 6) -> list[dict]:
    """Closest catalogue pieces to the raw text, by embedding. Not checked for size, stock or delivery."""
    vecs, meta = _index()
    scores = vecs @ embed_query(text)
    order = np.argsort(-scores)
    out, slots = [], {}
    for idx in order:
        item = cat.by_id[meta["ids"][int(idx)]]
        if slots.get(item.slot.value, 0) >= 2:  # a spread across slots, not six dresses
            continue
        slots[item.slot.value] = slots.get(item.slot.value, 0) + 1
        m = cat.merchant(item)
        out.append({"id": item.id, "name": item.name, "merchant": m.name, "city": m.city, "image": item.image,
                    "price_local": round(rules.to_local(cat, item.price, item.currency, market), 2)})
        if len(out) == n:
            break
    return out


def hubs(cat: Catalogue) -> list[dict]:
    counts: dict[str, int] = {}
    for item in cat.items:
        city = cat.merchant(item).city
        counts[city] = counts.get(city, 0) + 1
    return [{"city": c, "items": n} for c, n in sorted(counts.items(), key=lambda kv: -kv[1])]


def preread(cat: Catalogue, text: str, market: str, today: date | None = None) -> dict:
    today = today or date.today()
    found = chips(text, today)
    return {"chips": found, "first_glance": first_glance(cat, text, market), "hubs": hubs(cat),
            "needs_size": not any(c["key"] == "size" for c in found)}


def fallback_brief(text: str, market: str = "ZA", today: date | None = None):
    """Build a structured Brief from pre-read chips when a live LLM call is unavailable on serverless."""
    from goa.schemas import Brief, Budget, Formality, Part, Slot

    today = today or date.today()
    found = chips(text, today)
    by_key = {c["key"]: c["value"] for c in found}
    colours = [c["value"] for c in found if c["key"] == "colour"]
    occ = str(by_key.get("occasion") or "graduation")
    ev_date = date.fromisoformat(by_key["event_date"]) if "event_date" in by_key else None
    loc = by_key.get("location")
    setting = by_key.get("setting")
    bval = by_key.get("budget")
    budget = Budget(amount=float(bval["amount"]), currency=str(bval["currency"]), soft="around" in text.lower() or "about" in text.lower()) if bval else None
    size = by_key.get("size")
    tl = text.lower()
    formality = Formality.black_tie if "black tie" in tl else Formality.formal if "formal" in tl and "not formal" not in tl else Formality.smart_casual if "casual" in tl or "not formal" in tl else Formality.cocktail
    c_str = ", ".join(colours) if colours else "versatile"
    parts = [
        Part(slot=Slot.garment, description=f"{c_str} {occ} outfit: {text.strip()[:120]}", colours=colours, materials=[]),
        Part(slot=Slot.shoes, description=f"{'flat ' if 'flat' in tl or 'no heel' in tl else ''}shoes for {occ}", colours=[], materials=["leather"]),
        Part(slot=Slot.accessory, description=f"understated accessory for {occ}", colours=[], materials=[]),
    ]
    if any(w in tl for w in ("jacket", "blazer", "shawl", "wrap", "coat", "cool", "evening", "outdoor")):
        parts.insert(2, Part(slot=Slot.outer_layer, description=f"light outer layer or jacket for {occ}", colours=colours[:1], materials=["linen"]))
    return Brief(
        occasion=occ, event_date=ev_date, location=loc, market=market, setting=setting,
        weather="warm day" if "warm" in tl else None, budget=budget, size=size, shoe_size=None,
        colours=colours, formality=formality,
        style_notes=[w for w in ("elegant", "rewearable", "relaxed", "tailored", "minimal", "bold") if w in tl or (w == "rewearable" and "wear again" in tl)],
        constraints=["no heels"] if ("flat" in tl or "no heel" in tl) else [],
        parts=parts,
    )

