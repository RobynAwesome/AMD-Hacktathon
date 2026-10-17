"""Creative brief interpretation, part decomposition and customer size updates.

Preserves user authorship and uncertainty:
- Never invents garment or shoe sizes that were not in the customer's prompt or
  explicit follow-up input.
- Records any date-year or formality inference in `CreativeBrief.uncertainties`.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from goa.schemas import (
    CreativeBrief,
    DesiredAttributes,
    Formality,
    InterpretationSource,
    MandatoryConstraints,
    PartOrigin,
    PartStatus,
    PartType,
    RequestedPart,
)

MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

KNOWN_COLOURS = (
    "emerald green", "sage green", "olive green", "forest green", "bottle green",
    "cobalt blue", "blush pink", "stone beige", "chocolate brown",
    "emerald", "sage", "olive", "green", "ivory", "white", "tan", "gold",
    "terracotta", "mustard", "navy", "black", "nude", "brown", "silver",
    "charcoal", "blue", "pink", "camel",
)

KNOWN_MATERIALS = (
    "vegan leather", "linen blend", "wool blend", "patent leather", "sterling silver",
    "linen", "cotton", "satin", "silk", "chiffon", "leather", "suede",
    "canvas", "raffia", "straw", "wool", "crepe", "velvet", "brass",
)

GARMENT_KEYWORDS_BY_PART: dict[PartType, tuple[str, ...]] = {
    PartType.DRESS_OR_SUIT: ("jumpsuit", "gown", "suit", "dress"),
    PartType.SHOES: ("sandals", "heels", "loafers", "sneakers", "oxfords", "derby", "espadrilles", "boots", "moccasins"),
    PartType.OUTER_LAYER: ("jacket", "blazer", "cardigan", "kimono", "trench", "coat", "overcoat", "bomber"),
    PartType.ACCESSORY: ("clutch", "earrings", "necklace", "bag", "belt", "hat", "tie", "cufflinks", "pocket-square"),
}


def _extract_budget_cents(text: str) -> int | None:
    m = re.search(r"\bR\s*([0-9][0-9,\s]*(?:\.[0-9]{1,2})?)", text, flags=re.IGNORECASE)
    if not m:
        return None
    cleaned = re.sub(r"[,\s]", "", m.group(1))
    if "." in cleaned:
        return int(round(float(cleaned) * 100))
    return int(cleaned) * 100


def _extract_event_date(text: str, *, reference_date: date, uncertainties: list[str]) -> date | None:
    m_iso = re.search(r"\b(20[2-9][0-9])-([01][0-9])-([0-3][0-9])\b", text)
    if m_iso:
        return date(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)))

    pattern = r"\b([0-3]?[0-9])\s+(january|jan|february|feb|march|mar|april|apr|may|june|jun|july|jul|august|aug|september|sept|sep|october|oct|november|nov|december|dec)(?:\s+(20[2-9][0-9]))?\b"
    m = re.search(pattern, text, flags=re.IGNORECASE)
    if not m:
        uncertainties.append("no specific event day supplied in prompt")
        return None
    day = int(m.group(1))
    month = MONTHS[m.group(2).lower()]
    if m.group(3):
        year = int(m.group(3))
    else:
        year = reference_date.year
        candidate = date(year, month, day)
        if candidate < reference_date:
            year += 1
        uncertainties.append(f"event year inferred as next occurrence ({year})")
    return date(year, month, day)


def _extract_sizes(text: str, uncertainties: list[str]) -> dict[PartType, str]:
    sizes: dict[PartType, str] = {}
    shoe_m = re.search(r"\b(?:shoe(?:\s+size)?\s*)?(UK\s*[0-9]{1,2})\b", text, flags=re.IGNORECASE)
    if shoe_m:
        sizes[PartType.SHOES] = re.sub(r"\s+", "", shoe_m.group(1)).upper()

    apparel_m = re.search(
        r"\b(?:size|i'm\s+a\s+size|im\s+a\s+size)\s+(XXL|XL|XS|S|M|L)\b",
        text,
        flags=re.IGNORECASE,
    )
    if apparel_m:
        sz = apparel_m.group(1).upper()
        sizes[PartType.DRESS_OR_SUIT] = sz
        sizes[PartType.OUTER_LAYER] = sz

    if PartType.DRESS_OR_SUIT not in sizes and PartType.OUTER_LAYER not in sizes:
        uncertainties.append("no garment size supplied in prompt; customer must add size before availability can be checked")
    if PartType.SHOES not in sizes:
        uncertainties.append("no shoe size supplied in prompt; customer must add shoe size before availability can be checked")
    return sizes


def _extract_formality(text: str, uncertainties: list[str]) -> Formality:
    low = text.lower()
    if "not formal" in low or "smart" in low:
        if "elegant but not formal" in low:
            uncertainties.append("'elegant but not formal' mapped to SMART_CASUAL")
        return Formality.SMART_CASUAL
    if "semi-formal" in low or "semi formal" in low or "statement" in low:
        return Formality.SEMI_FORMAL
    if "formal" in low or "classic" in low or "ball" in low:
        return Formality.FORMAL
    if "casual" in low or "picnic" in low:
        return Formality.CASUAL
    return Formality.SMART_CASUAL


def _extract_colours(text: str) -> list[str]:
    low = text.lower()
    found: list[str] = []
    for col in KNOWN_COLOURS:
        base = col.split()[0]
        if re.search(rf"\b{re.escape(col)}\b", low):
            norm = "green" if col in ("emerald", "emerald green") else base
            if norm not in found:
                found.append(norm)
    return found


def parse_brief_rule_based(
    raw_prompt: str,
    *,
    brief_id: str = "brf_session",
    session_id: str = "ses_default",
    reference_date: date = date(2026, 10, 18),
    customer_sizes: dict[PartType, str] | None = None,
    now: datetime | None = None,
) -> CreativeBrief:
    """Deterministic fallback parser that converts `raw_prompt` into a `CreativeBrief`."""
    ts = now or datetime.now(timezone.utc)
    uncertainties: list[str] = []
    low = raw_prompt.lower()

    event_date = _extract_event_date(raw_prompt, reference_date=reference_date, uncertainties=uncertainties)
    budget_cents = _extract_budget_cents(raw_prompt)
    if budget_cents is None:
        uncertainties.append("no budget supplied in prompt")

    sizes = _extract_sizes(raw_prompt, uncertainties)
    if customer_sizes:
        for pt, sz in customer_sizes.items():
            if sz and sz.strip():
                sizes[pt] = sz.strip().upper()
        uncertainties = [u for u in uncertainties if "size" not in u]

    formality = _extract_formality(raw_prompt, uncertainties)
    colours = _extract_colours(raw_prompt)

    location = None
    for loc in ("Cape Town", "Stellenbosch", "Johannesburg", "Durban", "Pretoria"):
        if loc.lower() in low:
            location = loc
            break

    occasion = "graduation" if "graduation" in low else ("ceremony" if "ceremony" in low else None)

    style_prefs: list[str] = []
    for tag in ("elegant", "outdoor", "lightweight", "breathable", "comfortable", "tailored", "floaty", "statement", "classic", "summer"):
        if tag in low:
            style_prefs.append(tag)
    if "warm" in low and "breathable" not in style_prefs:
        style_prefs.append("breathable")

    reuse_prefs: list[str] = []
    if "wear again" in low or "rewear" in low:
        reuse_prefs.append("rewearable")
    if "vegan" in low:
        reuse_prefs.append("vegan")

    constraints: list[str] = []
    if "outdoor" in low:
        constraints.append("outdoor event")
    if "warm" in low:
        constraints.append("warm weather")

    # Clause-level decomposition for explicit garment mentions, or 4-part graduation look default.
    explicit_parts: list[RequestedPart] = []
    clauses = re.split(r"[,.;]|\band\b|\bwith\b|\bover\b", low)
    seen_types: set[PartType] = set()
    part_counter = 0

    for clause in clauses:
        for pt, kw_list in GARMENT_KEYWORDS_BY_PART.items():
            hit_kws = [kw for kw in kw_list if re.search(rf"\b{re.escape(kw)}\b", clause)]
            if hit_kws and pt not in seen_types:
                seen_types.add(pt)
                part_counter += 1
                c_colours = _extract_colours(clause)
                c_mats = [m for m in KNOWN_MATERIALS if re.search(rf"\b{re.escape(m.replace(' ', '-'))}\b|\b{re.escape(m)}\b", clause)]
                must_arrive = (event_date - timedelta(days=1)) if event_date else None
                explicit_parts.append(
                    RequestedPart(
                        part_id=f"prt_{brief_id[4:]}_{part_counter}",
                        brief_id=brief_id,
                        part_type=pt,
                        origin=PartOrigin.EXPLICIT,
                        desired_attributes=DesiredAttributes(
                            colours=c_colours or (colours[:1] if pt == PartType.DRESS_OR_SUIT else []),
                            materials=c_mats,
                            style_tags=list(style_prefs),
                            formality=formality,
                            garment_keywords=hit_kws,
                        ),
                        mandatory_constraints=MandatoryConstraints(
                            size=sizes.get(pt),
                            must_arrive_by=must_arrive,
                            max_price_cents=budget_cents,
                            required_colours=c_colours,
                            required_materials=c_mats,
                            required_garment_keywords=hit_kws,
                        ),
                        optional_preferences=list(reuse_prefs),
                        status=PartStatus.PENDING_VERIFICATION,
                    )
                )

    if not explicit_parts:
        must_arrive = (event_date - timedelta(days=1)) if event_date else None
        default_specs = [
            (PartType.DRESS_OR_SUIT, colours, style_prefs + reuse_prefs),
            (PartType.SHOES, [], ["comfortable", "outdoor"] if "outdoor" in low else ["elegant"]),
            (PartType.OUTER_LAYER, [], ["lightweight"] + reuse_prefs),
            (PartType.ACCESSORY, [], ["elegant"] + reuse_prefs),
        ]
        for idx, (pt, p_cols, p_tags) in enumerate(default_specs, start=1):
            explicit_parts.append(
                RequestedPart(
                    part_id=f"prt_{brief_id[4:]}_{idx}",
                    brief_id=brief_id,
                    part_type=pt,
                    origin=PartOrigin.INFERRED_DEFAULT,
                    desired_attributes=DesiredAttributes(
                        colours=list(p_cols),
                        style_tags=list(dict.fromkeys(p_tags)),
                        formality=formality,
                    ),
                    mandatory_constraints=MandatoryConstraints(
                        size=sizes.get(pt),
                        must_arrive_by=must_arrive,
                        max_price_cents=budget_cents,
                    ),
                    optional_preferences=list(reuse_prefs),
                    status=PartStatus.PENDING_VERIFICATION,
                )
            )

    return CreativeBrief(
        brief_id=brief_id,
        session_id=session_id,
        raw_prompt=raw_prompt,
        occasion=occasion,
        event_date=event_date,
        location=location,
        budget_cents=budget_cents,
        preferred_colours=colours,
        formality=formality,
        style_preferences=style_prefs,
        sustainability_or_reuse_preferences=reuse_prefs,
        sizes=sizes,
        constraints=constraints,
        requested_parts=explicit_parts,
        uncertainties=uncertainties,
        interpretation_source=InterpretationSource.RULE_BASED_FALLBACK,
        created_at=ts,
    )


def apply_customer_sizes(
    brief: CreativeBrief,
    sizes: dict[PartType, str],
) -> CreativeBrief:
    """Return a copy of `brief` updated with explicit customer-supplied sizes."""
    merged_sizes = dict(brief.sizes)
    for pt, val in sizes.items():
        if val and val.strip():
            merged_sizes[pt] = val.strip().upper()

    updated_parts: list[RequestedPart] = []
    for part in brief.requested_parts:
        new_sz = merged_sizes.get(part.part_type)
        mc = part.mandatory_constraints.model_copy(update={"size": new_sz})
        updated_parts.append(
            part.model_copy(
                update={
                    "mandatory_constraints": mc,
                    "status": PartStatus.PENDING_VERIFICATION,
                }
            )
        )

    cleaned_uncertainties = [u for u in brief.uncertainties if "size" not in u.lower()]
    if PartType.SHOES not in merged_sizes:
        cleaned_uncertainties.append("shoe size not supplied")
    return brief.model_copy(
        update={
            "sizes": merged_sizes,
            "requested_parts": updated_parts,
            "uncertainties": cleaned_uncertainties,
        }
    )


def brief_from_eval_record(
    record: dict[str, Any],
    *,
    session_id: str = "ses_eval",
    now: datetime | None = None,
) -> CreativeBrief:
    """Convert one entry from `data/eval/briefs_v1.json` into a validated `CreativeBrief`."""
    ts = now or datetime(2026, 10, 18, 0, 0, tzinfo=timezone.utc)
    eval_id = record["eval_id"]
    brief_id = f"brf_{eval_id}"
    event_date = date.fromisoformat(record["event_date"]) if record.get("event_date") else None
    must_arrive = (event_date - timedelta(days=1)) if event_date else None
    budget_cents = record.get("budget_cents")
    sizes = {PartType(k): v for k, v in record.get("sizes", {}).items()}
    formality = Formality(record["formality"]) if record.get("formality") else None

    parts: list[RequestedPart] = []
    for idx, p in enumerate(record["parts"], start=1):
        pt = PartType(p["part_type"])
        parts.append(
            RequestedPart(
                part_id=f"prt_{eval_id}_{idx}",
                brief_id=brief_id,
                part_type=pt,
                origin=PartOrigin(p.get("origin", "EXPLICIT")),
                desired_attributes=DesiredAttributes(
                    colours=list(p.get("colours", [])),
                    materials=list(p.get("materials", [])),
                    style_tags=list(p.get("style_tags", [])),
                    formality=formality,
                    garment_keywords=list(p.get("garment_keywords", [])),
                ),
                mandatory_constraints=MandatoryConstraints(
                    size=sizes.get(pt),
                    must_arrive_by=must_arrive,
                    max_price_cents=budget_cents,
                    required_colours=list(p.get("required_colours", [])),
                    required_materials=list(p.get("required_materials", [])),
                    required_garment_keywords=list(p.get("required_garment_keywords", [])),
                ),
                optional_preferences=list(record.get("sustainability_or_reuse_preferences", [])),
                status=PartStatus.PENDING_VERIFICATION,
            )
        )

    uncertainties: list[str] = []
    if not sizes:
        uncertainties.append("no customer sizes supplied in evaluation prompt")
    if event_date is None:
        uncertainties.append("no event date supplied in evaluation prompt")

    return CreativeBrief(
        brief_id=brief_id,
        session_id=session_id,
        raw_prompt=record["raw_prompt"],
        occasion=record.get("occasion"),
        event_date=event_date,
        location=record.get("location"),
        budget_cents=budget_cents,
        preferred_colours=list(record.get("preferred_colours", [])),
        formality=formality,
        style_preferences=list(record.get("style_preferences", [])),
        sustainability_or_reuse_preferences=list(record.get("sustainability_or_reuse_preferences", [])),
        sizes=sizes,
        constraints=[],
        requested_parts=parts,
        uncertainties=uncertainties,
        interpretation_source=InterpretationSource.SCRIPTED_EVALUATION,
        created_at=ts,
    )
