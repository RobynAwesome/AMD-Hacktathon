"""Candidate matching and ranking for GOA Creative Commerce.

Records the exact matching method that ran (`KEYWORD_BASELINE`, `TAG_OVERLAP` or
`EMBEDDING`). Tag or keyword matching is never labelled as embedding search.
AI/matching only proposes and ranks; `goa.rules` decides eligibility.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Callable, Iterable

from goa.rules import verify_product_for_part
from goa.schemas import (
    CheckState,
    CreativeBrief,
    Formality,
    MatchCandidate,
    MatchMethod,
    PartType,
    Product,
    RequestedPart,
)

WORD_RE = re.compile(r"[a-z0-9]+")

COLOUR_FAMILIES: dict[str, tuple[str, ...]] = {
    "green": ("green", "emerald", "sage", "olive", "forest", "bottle"),
    "emerald": ("emerald", "green"),
    "sage": ("sage", "green"),
    "olive": ("olive", "green"),
    "ivory": ("ivory", "white", "cream", "stone"),
    "white": ("white", "ivory"),
    "tan": ("tan", "camel", "nude", "natural", "brown"),
    "brown": ("brown", "tan", "chocolate"),
    "gold": ("gold", "brass"),
    "pink": ("pink", "blush"),
    "blue": ("blue", "cobalt", "navy"),
    "navy": ("navy", "blue"),
}

PART_DEFAULT_KEYWORDS: dict[PartType, list[str]] = {
    PartType.DRESS_OR_SUIT: ["dress", "suit", "jumpsuit"],
    PartType.SHOES: ["sandals", "heels", "loafers", "shoes", "sneakers", "oxfords", "espadrilles"],
    PartType.OUTER_LAYER: ["jacket", "blazer", "cardigan", "kimono", "trench", "coat"],
    PartType.ACCESSORY: ["clutch", "earrings", "bag", "belt", "tie", "cufflinks", "hat", "pocket"],
}


def _words(text: str) -> set[str]:
    return set(WORD_RE.findall(text.lower()))


def score_keyword_baseline(
    part: RequestedPart,
    brief: CreativeBrief,
    product: Product,
) -> tuple[float, list[str]]:
    """Plain static-store keyword search over product name + description only."""
    da = part.desired_attributes
    raw_terms: list[str] = []
    raw_terms.extend(da.garment_keywords)
    raw_terms.extend(da.colours or brief.preferred_colours[:1])
    raw_terms.extend(da.materials)
    if not raw_terms:
        raw_terms.extend(PART_DEFAULT_KEYWORDS.get(part.part_type, [])[:1])

    query_tokens: list[str] = []
    for term in raw_terms:
        for tok in WORD_RE.findall(term.lower()):
            if tok not in query_tokens:
                query_tokens.append(tok)

    if not query_tokens:
        return 0.0, []

    doc_tokens = _words(f"{product.name} {product.description}")
    matched = [f"keyword:{t}" for t in query_tokens if t in doc_tokens]
    # Static store keyword search requires all entered keywords to appear in title/description.
    if len(matched) < len(query_tokens):
        return 0.0, matched
    score = round(min(1.0, len(matched) / max(1, len(query_tokens))), 4)
    return score, matched


def score_tag_overlap(
    part: RequestedPart,
    brief: CreativeBrief,
    product: Product,
    *,
    preferred_merchant_id: str | None = None,
) -> tuple[float, list[str]]:
    """Structured tag and attribute overlap scorer (honest non-embedding matcher)."""
    if product.part_type != part.part_type:
        return 0.0, []

    da = part.desired_attributes
    matched: list[str] = []
    points = 0.0
    max_points = 1.0  # base point for matching part_type
    points += 1.0
    matched.append(f"part_type:{product.part_type.value}")

    # 1. Garment subtype keywords
    if da.garment_keywords:
        max_points += 2.5
        prod_tokens = {t.lower() for t in product.style_tags} | _words(product.name)
        hit_kw = [kw for kw in da.garment_keywords if kw.lower() in prod_tokens or kw.lower() in product.name.lower()]
        if hit_kw:
            points += 2.5
            matched.append(f"garment:{hit_kw[0].lower()}")

    # 2. Colours (part desired colours or brief preferred colours)
    wanted_colours = da.colours or (brief.preferred_colours if part.origin.value == "INFERRED_DEFAULT" else [])
    if wanted_colours:
        max_points += 2.5
        prod_col = product.colour.lower()
        hit_col = None
        for wc in wanted_colours:
            wc_low = wc.lower()
            if wc_low in prod_col:
                hit_col = product.colour
                points += 2.5
                break
            family = COLOUR_FAMILIES.get(wc_low, (wc_low,))
            if any(f in prod_col for f in family):
                hit_col = product.colour
                points += 2.0
                break
        if hit_col:
            matched.append(f"colour:{hit_col}")
    elif product.part_type in (PartType.SHOES, PartType.OUTER_LAYER, PartType.ACCESSORY):
        # Neutral versatility bonus when no specific colour was demanded on a secondary part
        if any(n in product.colour.lower() for n in ("tan", "ivory", "gold", "nude", "natural", "sage", "emerald")):
            max_points += 0.5
            points += 0.5
            matched.append(f"versatile_colour:{product.colour}")

    # 3. Materials
    if da.materials:
        max_points += 2.0
        prod_mat = product.material.lower()
        hit_mat = [m for m in da.materials if m.lower() in prod_mat]
        if hit_mat:
            points += 2.0
            matched.append(f"material:{product.material}")

    # 4. Style & reuse tags
    wanted_tags = list(
        dict.fromkeys(
            [t.lower() for t in da.style_tags]
            + [t.lower() for t in brief.style_preferences]
            + [t.lower() for t in brief.sustainability_or_reuse_preferences]
            + [t.lower() for t in part.optional_preferences]
        )
    )
    if wanted_tags:
        max_points += 2.0
        prod_tags = {t.lower() for t in product.style_tags} | _words(product.material)
        hits = [t for t in wanted_tags if t in prod_tags]
        if hits:
            frac = min(1.0, len(hits) / max(1, min(3, len(wanted_tags))))
            points += 2.0 * frac
            for h in hits:
                matched.append(f"style:{h}")

    # 5. Formality alignment
    target_formality: Formality | None = da.formality or brief.formality
    if target_formality is not None:
        max_points += 1.0
        if product.formality == target_formality:
            points += 1.0
            matched.append(f"formality:{product.formality.value}")
        else:
            order = [Formality.CASUAL, Formality.SMART_CASUAL, Formality.SEMI_FORMAL, Formality.FORMAL]
            if abs(order.index(product.formality) - order.index(target_formality)) == 1:
                points += 0.5
                matched.append(f"formality_near:{product.formality.value}")

    # 6. Single-merchant cohesion tie-breaker (small bonus to keep compositions single-merchant where possible)
    if preferred_merchant_id is not None and product.merchant_id == preferred_merchant_id:
        max_points += 0.4
        points += 0.4
        matched.append(f"merchant_cohesion:{preferred_merchant_id}")

    score = round(min(1.0, max(0.0, points / max_points)), 4)
    return score, matched


EmbeddingScorer = Callable[[RequestedPart, CreativeBrief, Product], tuple[float, list[str]]]


def rank_and_verify_candidates(
    part: RequestedPart,
    brief: CreativeBrief,
    catalogue: Iterable[Product],
    *,
    evaluated_on: date,
    method: MatchMethod = MatchMethod.TAG_OVERLAP,
    remaining_budget_cents: int | None = None,
    preferred_merchant_id: str | None = None,
    embedding_scorer: EmbeddingScorer | None = None,
) -> list[MatchCandidate]:
    """Score every catalogue product of the requested part_type and verify deterministically."""
    if method == MatchMethod.EMBEDDING and embedding_scorer is None:
        raise ValueError(
            "MatchMethod.EMBEDDING requested without a live embedding_scorer; refusing to label tag/keyword matching as EMBEDDING."
        )

    brief_has_any_size = bool(brief.sizes)
    candidates: list[MatchCandidate] = []

    for product in catalogue:
        if product.part_type != part.part_type:
            continue

        if method == MatchMethod.KEYWORD_BASELINE:
            score, matched_attrs = score_keyword_baseline(part, brief, product)
        elif method == MatchMethod.TAG_OVERLAP:
            score, matched_attrs = score_tag_overlap(
                part, brief, product, preferred_merchant_id=preferred_merchant_id
            )
        else:
            assert embedding_scorer is not None
            score, matched_attrs = embedding_scorer(part, brief, product)

        vr, variant, rejections = verify_product_for_part(
            part,
            product,
            evaluated_on=evaluated_on,
            event_date=brief.event_date,
            budget_cents=brief.budget_cents,
            remaining_budget_cents=remaining_budget_cents,
            brief_has_any_size=brief_has_any_size,
        )

        # In KEYWORD_BASELINE mode, a zero keyword score means the static search bar did not return the item.
        if method == MatchMethod.KEYWORD_BASELINE and score <= 0.0:
            rejections = list(rejections) + ["Did not match keyword search query."]

        candidates.append(
            MatchCandidate(
                part_id=part.part_id,
                product_id=product.product_id,
                variant_id=variant.variant_id if variant else None,
                merchant_id=product.merchant_id,
                semantic_score=score,
                match_method=method,
                matched_attributes=matched_attrs,
                verification_result=vr,
                rejection_reasons=rejections,
            )
        )

    # Sort eligible candidates first, then by highest semantic_score, then by lower price_cents for budget efficiency.
    prices = {p.product_id: (p.price_cents or 10**9) for p in catalogue}
    candidates.sort(
        key=lambda c: (
            1 if (c.verification_result.overall == CheckState.PASS and not c.rejection_reasons) else 0,
            c.semantic_score,
            -prices.get(c.product_id, 10**9),
        ),
        reverse=True,
    )
    return candidates
