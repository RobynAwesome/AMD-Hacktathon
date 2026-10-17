"""Outfit composition and customer-authored remixing for GOA Creative Commerce.

Separates three outcomes per requested part:
- `selected_parts` (`AVAILABLE`): verified by deterministic rules and within budget.
- `unmet_parts` (`NOT_ON_OFFER_YET`): all customer inputs present, no eligible supply.
- `pending_input_parts` (`NEEDS_CUSTOMER_INPUT`): waiting on customer size/date/budget;
  never shown as available and never logged as a merchant demand gap.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Iterable

from goa.gaps import build_demand_gaps_for_composition
from goa.match import EmbeddingScorer, rank_and_verify_candidates
from goa.rules import (
    VerificationError,
    classify_supply_unmet_reasons,
    missing_customer_inputs_for_part,
    verify_product_for_part,
)
from goa.schemas import (
    CheckState,
    Composition,
    CompositionStatus,
    CreativeBrief,
    DemandGap,
    GapSourceType,
    MatchCandidate,
    MatchMethod,
    PartStatus,
    PendingInputPart,
    Product,
    SelectedBy,
    SelectedPart,
    UnmetPart,
    UnmetReason,
)


def _explain_missing_inputs(reasons: list[UnmetReason]) -> str:
    messages: list[str] = []
    if UnmetReason.CUSTOMER_SIZE_REQUIRED in reasons:
        messages.append("Add your size to check availability.")
    if UnmetReason.EVENT_DATE_REQUIRED in reasons:
        messages.append("Add your event date to check delivery timing.")
    if UnmetReason.BUDGET_REQUIRED in reasons:
        messages.append("Add your total budget to check price eligibility.")
    return " ".join(messages) or "Additional customer details required to check availability."


def compose_outfit(
    brief: CreativeBrief,
    catalogue: Iterable[Product],
    *,
    evaluated_on: date,
    method: MatchMethod = MatchMethod.TAG_OVERLAP,
    composition_id: str | None = None,
    gap_source_type: GapSourceType = GapSourceType.DEMO_SESSION,
    searched_merchant_ids: list[str] | None = None,
    embedding_scorer: EmbeddingScorer | None = None,
    now: datetime | None = None,
) -> tuple[Composition, dict[str, list[MatchCandidate]], list[DemandGap]]:
    """Compose a verified complete or partial outfit from `brief` and `catalogue`."""
    ts = now or datetime.now(timezone.utc)
    products = list(catalogue)
    prod_by_id = {p.product_id: p for p in products}
    merchant_ids = (
        list(searched_merchant_ids)
        if searched_merchant_ids is not None
        else sorted({p.merchant_id for p in products})
    )

    selected_parts: list[SelectedPart] = []
    unmet_parts: list[UnmetPart] = []
    pending_input_parts: list[PendingInputPart] = []
    candidates_by_part: dict[str, list[MatchCandidate]] = {}
    running_total = 0
    preferred_merchant: str | None = None

    for part in brief.requested_parts:
        missing = missing_customer_inputs_for_part(part, brief)
        rem_budget = (brief.budget_cents - running_total) if brief.budget_cents is not None else None

        candidates = rank_and_verify_candidates(
            part,
            brief,
            products,
            evaluated_on=evaluated_on,
            method=method,
            remaining_budget_cents=rem_budget,
            preferred_merchant_id=preferred_merchant,
            embedding_scorer=embedding_scorer,
        )
        candidates_by_part[part.part_id] = candidates

        if missing:
            part.status = PartStatus.NEEDS_CUSTOMER_INPUT
            pending_input_parts.append(
                PendingInputPart(
                    part_id=part.part_id,
                    part_type=part.part_type,
                    desired_attributes=part.desired_attributes,
                    missing_inputs=missing,
                    explanation=_explain_missing_inputs(missing),
                )
            )
            continue

        chosen = next((c for c in candidates if c.eligible), None)
        if chosen is not None and chosen.variant_id is not None:
            prod = prod_by_id[chosen.product_id]
            variant = next(v for v in prod.variants if v.variant_id == chosen.variant_id)
            assert prod.price_cents is not None
            part.status = PartStatus.AVAILABLE
            selected_parts.append(
                SelectedPart(
                    part_id=part.part_id,
                    part_type=part.part_type,
                    product_id=prod.product_id,
                    variant_id=variant.variant_id,
                    merchant_id=prod.merchant_id,
                    product_name=prod.name,
                    size=variant.size,
                    unit_price_cents=prod.price_cents,
                    selected_by=SelectedBy.SYSTEM_SUGGESTION,
                    semantic_score=chosen.semantic_score,
                    matched_attributes=chosen.matched_attributes,
                    verification_result=chosen.verification_result,
                )
            )
            running_total += prod.price_cents
            if preferred_merchant is None:
                preferred_merchant = prod.merchant_id
        else:
            part.status = PartStatus.NOT_ON_OFFER_YET
            reasons, explanation = classify_supply_unmet_reasons(
                part,
                products,
                evaluated_on=evaluated_on,
                event_date=brief.event_date,
                budget_cents=brief.budget_cents,
                remaining_budget_cents=rem_budget,
                brief_has_any_size=bool(brief.sizes),
            )
            unmet_parts.append(
                UnmetPart(
                    part_id=part.part_id,
                    part_type=part.part_type,
                    desired_attributes=part.desired_attributes,
                    reasons=reasons,
                    explanation=explanation,
                )
            )

    if selected_parts and not unmet_parts and not pending_input_parts:
        status = CompositionStatus.VERIFIED_COMPLETE
    elif selected_parts:
        status = CompositionStatus.VERIFIED_PARTIAL
    else:
        status = CompositionStatus.EMPTY

    comp_id = composition_id or f"cmp_{brief.brief_id[4:]}"
    composition = Composition(
        composition_id=comp_id,
        brief_id=brief.brief_id,
        selected_parts=selected_parts,
        unmet_parts=unmet_parts,
        pending_input_parts=pending_input_parts,
        total_price_cents=running_total,
        budget_cents=brief.budget_cents,
        validation_status=status,
        merchant_scope=sorted({sp.merchant_id for sp in selected_parts}),
        created_at=ts,
    )
    gaps = build_demand_gaps_for_composition(
        composition,
        searched_merchant_ids=merchant_ids,
        source_type=gap_source_type,
        now=ts,
    )
    return composition, candidates_by_part, gaps


def swap_part_in_composition(
    composition: Composition,
    brief: CreativeBrief,
    *,
    part_id: str,
    new_product_id: str,
    catalogue_by_id: dict[str, Product],
    evaluated_on: date,
    new_variant_id: str | None = None,
    new_composition_id: str | None = None,
    now: datetime | None = None,
) -> Composition:
    """Customer-authored swap of a part (`selected_by = CUSTOMER`), verified by rules."""
    ts = now or datetime.now(timezone.utc)
    part = next((p for p in brief.requested_parts if p.part_id == part_id), None)
    if part is None:
        raise VerificationError(f"Part {part_id} not found on brief {brief.brief_id}.", code="PART_NOT_FOUND")

    other_selected = [sp for sp in composition.selected_parts if sp.part_id != part_id]
    other_total = sum(sp.unit_price_cents for sp in other_selected)
    rem_budget = (brief.budget_cents - other_total) if brief.budget_cents is not None else None

    product = catalogue_by_id.get(new_product_id)
    vr, variant, rejections = verify_product_for_part(
        part,
        product,
        evaluated_on=evaluated_on,
        event_date=brief.event_date,
        budget_cents=brief.budget_cents,
        remaining_budget_cents=rem_budget,
        variant_id=new_variant_id,
        brief_has_any_size=bool(brief.sizes),
    )
    if vr.overall != CheckState.PASS or product is None or variant is None or product.price_cents is None:
        raise VerificationError(
            f"Chosen product {new_product_id} failed verification: {'; '.join(rejections)}",
            code="SWAP_CANDIDATE_INELIGIBLE",
        )

    new_sp = SelectedPart(
        part_id=part.part_id,
        part_type=part.part_type,
        product_id=product.product_id,
        variant_id=variant.variant_id,
        merchant_id=product.merchant_id,
        product_name=product.name,
        size=variant.size,
        unit_price_cents=product.price_cents,
        selected_by=SelectedBy.CUSTOMER,
        semantic_score=1.0,
        matched_attributes=["customer_selected:true"],
        verification_result=vr,
    )

    updated_selected = [new_sp if sp.part_id == part_id else sp for sp in composition.selected_parts]
    if all(sp.part_id != part_id for sp in composition.selected_parts):
        updated_selected.append(new_sp)

    updated_unmet = [u for u in composition.unmet_parts if u.part_id != part_id]
    updated_pending = [p for p in composition.pending_input_parts if p.part_id != part_id]
    new_total = sum(sp.unit_price_cents for sp in updated_selected)

    if updated_selected and not updated_unmet and not updated_pending:
        status = CompositionStatus.VERIFIED_COMPLETE
    elif updated_selected:
        status = CompositionStatus.VERIFIED_PARTIAL
    else:
        status = CompositionStatus.EMPTY

    return Composition(
        composition_id=new_composition_id or f"{composition.composition_id}_remix",
        brief_id=composition.brief_id,
        parent_composition_id=composition.composition_id,
        selected_parts=updated_selected,
        unmet_parts=updated_unmet,
        pending_input_parts=updated_pending,
        total_price_cents=new_total,
        budget_cents=composition.budget_cents,
        validation_status=status,
        merchant_scope=sorted({sp.merchant_id for sp in updated_selected}),
        saved=composition.saved,
        created_at=ts,
    )
