"""Deterministic verification engine for GOA Creative Commerce.

AI proposes; this module decides eligibility. Every check is computed in Python
from catalogue and brief records — never from model output.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from goa.schemas import (
     CUSTOMER_INPUT_REASONS,
    CheckResult,
    CheckState,
    Composition,
    CompositionStatus,
    CreativeBrief,
    CustomerRequirements,
    DemandGap,
    EnquiryStatus,
    GapSourceType,
    ItemRevalidation,
    LineItem,
    PartOrigin,
    PartStatus,
    PartType,
    PendingInputPart,
    Product,
    ProductVariant,
    QuoteEnquiry,
    RequestedPart,
    SelectedPart,
    UnmetPart,
    UnmetReason,
    ValidationReceipt,
    VerificationResult,
)

ENGINE_VERSION = "goa-verify-1.0.0"


class VerificationError(ValueError):
    """Raised when a commercial action fails deterministic verification."""

    def __init__(self, message: str, *, code: str = "VERIFICATION_FAILED", receipt: ValidationReceipt | None = None):
        super().__init__(message)
        self.code = code
        self.receipt = receipt


def _check(state: CheckState, reason: str, **evidence: object) -> CheckResult:
    return CheckResult(state=state, reason=reason, evidence=dict(evidence))


def _colour_matches(required_colours: list[str], product: Product) -> bool:
    if not required_colours:
        return True
    haystack = f"{product.colour} {' '.join(product.style_tags)} {product.name}".lower()
    return any(req.lower() in haystack for req in required_colours)


def _material_matches(required_materials: list[str], product: Product) -> bool:
    if not required_materials:
        return True
    mat = product.material.lower()
    return any(req.lower() in mat for req in required_materials)


def _garment_keyword_matches(required_keywords: list[str], product: Product) -> bool:
    if not required_keywords:
        return True
    tokens = {t.lower() for t in product.style_tags}
    name_lower = product.name.lower()
    return any(kw.lower() in tokens or kw.lower() in name_lower for kw in required_keywords)


def resolve_variant(
    product: Product | None,
    *,
    requested_size: str | None,
    variant_id: str | None = None,
) -> ProductVariant | None:
    if product is None:
        return None
    if variant_id is not None:
        for v in product.variants:
            if v.variant_id == variant_id:
                return v
        return None
    if requested_size is None:
        return None
    target = requested_size.strip().upper()
    for v in product.variants:
        if v.size.strip().upper() == target:
            return v
    return None


def effective_requested_size(
    part: RequestedPart,
    *,
    brief_has_any_size: bool = True,
) -> str | None:
    """Return the size to verify, or None when customer size input is still required.

    Accessories in the GOA catalogue are ONE_SIZE, so once the customer has supplied
    their garment/shoe sizes (or explicitly requested an accessory), ONE_SIZE is used
    when no separate accessory size was specified. On an unresolved prompt with zero
    customer sizes and only inferred default parts, None is returned so nothing is
    prematurely marked AVAILABLE.
    """
    explicit_size = part.mandatory_constraints.size
    if explicit_size is not None:
        return explicit_size
    if part.part_type == PartType.ACCESSORY and (
        brief_has_any_size or part.origin != PartOrigin.INFERRED_DEFAULT
    ):
        return "ONE_SIZE"
    return None


def verify_product_for_part(
    part: RequestedPart,
    product: Product | None,
    *,
    evaluated_on: date,
    event_date: date | None,
    budget_cents: int | None,
    remaining_budget_cents: int | None = None,
    variant_id: str | None = None,
    required_quantity: int = 1,
    brief_has_any_size: bool = True,
) -> tuple[VerificationResult, ProductVariant | None, list[str]]:
    """Run all 7 deterministic verification checks on a (part, product) pair."""
    rejection_reasons: list[str] = []
    req_size = effective_requested_size(part, brief_has_any_size=brief_has_any_size)

    # 1. exists_in_catalogue
    if product is None:
        exists_chk = _check(CheckState.FAIL, "product does not exist in catalogue", product_id=None)
        rejection_reasons.append("Product does not exist in catalogue.")
        matched_variant = None
    elif not product.active:
        exists_chk = _check(
            CheckState.FAIL, "product is inactive in catalogue", product_id=product.product_id, active=False
        )
        rejection_reasons.append("Product is inactive.")
        matched_variant = None
    elif variant_id is not None and resolve_variant(product, requested_size=req_size, variant_id=variant_id) is None:
        exists_chk = _check(
            CheckState.FAIL,
            "requested variant_id does not exist on product",
            product_id=product.product_id,
            variant_id=variant_id,
        )
        rejection_reasons.append(f"Variant {variant_id} not found on product {product.product_id}.")
        matched_variant = None
    else:
        matched_variant = resolve_variant(product, requested_size=req_size, variant_id=variant_id)
        exists_chk = _check(
            CheckState.PASS,
            "product exists and is active in catalogue",
            product_id=product.product_id,
            merchant_id=product.merchant_id,
            variant_id=matched_variant.variant_id if matched_variant else variant_id,
        )

    # 2. correct_part_type (including mandatory garment/colour/material constraints)
    mc = part.mandatory_constraints
    if product is None:
        type_chk = _check(CheckState.FAIL, "cannot check part_type of missing product")
    elif product.part_type != part.part_type:
        type_chk = _check(
            CheckState.FAIL,
            "product part_type does not match requested part_type",
            expected=part.part_type.value,
            actual=product.part_type.value,
        )
        rejection_reasons.append(f"Part type mismatch: expected {part.part_type}, got {product.part_type}.")
    elif not _garment_keyword_matches(mc.required_garment_keywords, product):
        type_chk = _check(
            CheckState.FAIL,
            "product does not match mandatory garment subtype",
            required_garment_keywords=mc.required_garment_keywords,
            actual_tags=product.style_tags,
            actual_name=product.name,
        )
        rejection_reasons.append(
            f"Product does not match required garment type {mc.required_garment_keywords}."
        )
    elif not _colour_matches(mc.required_colours, product):
        type_chk = _check(
            CheckState.FAIL,
            "product does not match mandatory colour constraint",
            required_colours=mc.required_colours,
            actual_colour=product.colour,
        )
        rejection_reasons.append(
            f"Product colour '{product.colour}' does not match required {mc.required_colours}."
        )
    elif not _material_matches(mc.required_materials, product):
        type_chk = _check(
            CheckState.FAIL,
            "product does not match mandatory material constraint",
            required_materials=mc.required_materials,
            actual_material=product.material,
        )
        rejection_reasons.append(
            f"Product material '{product.material}' does not match required {mc.required_materials}."
        )
    else:
        type_chk = _check(
            CheckState.PASS,
            "part_type and mandatory garment attributes match",
            expected=part.part_type.value,
            actual=product.part_type.value,
        )

    # 3. size_available
    if req_size is None:
        size_chk = _check(
            CheckState.UNKNOWN,
            "customer size not provided; add your size to check availability",
            part_type=part.part_type.value,
        )
        rejection_reasons.append("Customer size is required before availability can be confirmed.")
    elif product is None:
        size_chk = _check(CheckState.FAIL, "cannot check size on missing product", requested_size=req_size)
    else:
        size_variant = resolve_variant(product, requested_size=req_size, variant_id=variant_id)
        if size_variant is None or size_variant.size.strip().upper() != req_size.strip().upper():
            offered = [v.size for v in product.variants]
            size_chk = _check(
                CheckState.FAIL,
                f"requested size {req_size} is not offered for this product",
                requested_size=req_size,
                offered_sizes=offered,
            )
            rejection_reasons.append(f"Size {req_size} not offered (offered: {offered}).")
            matched_variant = None
        else:
            matched_variant = size_variant
            size_chk = _check(
                CheckState.PASS,
                "requested size is offered",
                requested_size=req_size,
                variant_id=size_variant.variant_id,
            )

    # 4. stock_available
    if product is None:
        stock_chk = _check(CheckState.FAIL, "cannot check stock on missing product")
    elif size_chk.state == CheckState.UNKNOWN:
        stock_chk = _check(CheckState.UNKNOWN, "cannot check variant stock until size is known")
    elif size_chk.state == CheckState.FAIL or matched_variant is None:
        stock_chk = _check(CheckState.FAIL, "no matching size variant to check stock")
    elif matched_variant.stock_quantity < required_quantity:
        stock_chk = _check(
            CheckState.FAIL,
            f"insufficient stock for size {matched_variant.size}",
            variant_id=matched_variant.variant_id,
            stock_quantity=matched_variant.stock_quantity,
            required_quantity=required_quantity,
        )
        rejection_reasons.append(
            f"Zero/insufficient stock for size {matched_variant.size} (stock={matched_variant.stock_quantity})."
        )
    else:
        stock_chk = _check(
            CheckState.PASS,
            "positive variant stock available",
            variant_id=matched_variant.variant_id,
            stock_quantity=matched_variant.stock_quantity,
        )

    # 5. delivery_feasible (must arrive strictly before event_date, or on/before must_arrive_by)
    effective_event_date = event_date
    must_arrive_by = mc.must_arrive_by
    if effective_event_date is None and must_arrive_by is None:
        delivery_chk = _check(
            CheckState.UNKNOWN,
            "event date not provided; cannot verify delivery before event",
        )
        rejection_reasons.append("Event date is required to verify delivery lead time.")
    elif product is None or product.delivery_lead_days is None:
        delivery_chk = _check(
            CheckState.FAIL,
            "product delivery_lead_days is missing",
            delivery_lead_days=None if product is None else product.delivery_lead_days,
        )
        rejection_reasons.append("Product delivery lead time is unknown.")
    else:
        arrival = evaluated_on + timedelta(days=product.delivery_lead_days)
        latest_allowed = (
            min( effective_event_date - timedelta(days=1), must_arrive_by )
            if (effective_event_date is not None and must_arrive_by is not None)
            else (effective_event_date - timedelta(days=1) if effective_event_date is not None else must_arrive_by)
        )
        assert latest_allowed is not None
        if arrival <= latest_allowed:
            delivery_chk = _check(
                CheckState.PASS,
                "arrives before event date",
                lead_days=product.delivery_lead_days,
                evaluated_on=evaluated_on.isoformat(),
                arrival_date=arrival.isoformat(),
                latest_allowed_arrival=latest_allowed.isoformat(),
                event_date=effective_event_date.isoformat() if effective_event_date else None,
            )
        else:
            delivery_chk = _check(
                CheckState.FAIL,
                "delivery arrives on or after the event date",
                lead_days=product.delivery_lead_days,
                evaluated_on=evaluated_on.isoformat(),
                arrival_date=arrival.isoformat(),
                latest_allowed_arrival=latest_allowed.isoformat(),
                event_date=effective_event_date.isoformat() if effective_event_date else None,
            )
            rejection_reasons.append(
                f"Delivery takes {product.delivery_lead_days} days (arrives {arrival.isoformat()}), too late for event."
            )

    # 6. price_known
    if product is None:
        price_chk = _check(CheckState.FAIL, "cannot check price on missing product")
    elif (
        product.price_cents is None
        or isinstance(product.price_cents, bool)
        or not isinstance(product.price_cents, int)
        or product.price_cents <= 0
        or product.currency != "ZAR"
    ):
        price_chk = _check(
            CheckState.FAIL,
            "product price is missing or not a positive ZAR integer-cent value",
            price_cents=product.price_cents,
            currency=product.currency,
        )
        rejection_reasons.append("Product has no known ZAR price.")
    else:
        price_chk = _check(
            CheckState.PASS,
            "valid ZAR integer-cent price from catalogue",
            price_cents=product.price_cents,
            currency=product.currency,
        )

    # 7. budget_feasible
    caps = [
        c
        for c in (budget_cents, mc.max_price_cents, remaining_budget_cents)
        if c is not None
    ]
    if not caps:
        budget_chk = _check(
            CheckState.UNKNOWN,
            "budget not provided; cannot verify budget feasibility",
        )
        rejection_reasons.append("Customer budget is required to verify budget feasibility.")
    elif price_chk.state != CheckState.PASS or product is None or product.price_cents is None:
        budget_chk = _check(
            CheckState.FAIL,
            "cannot verify budget feasibility when price is unknown",
        )
    else:
        effective_cap = min(caps)
        total_price = product.price_cents * required_quantity
        if total_price <= effective_cap:
            budget_chk = _check(
                CheckState.PASS,
                "within customer budget",
                price_cents=total_price,
                effective_cap_cents=effective_cap,
                budget_cents=budget_cents,
                remaining_budget_cents=remaining_budget_cents,
            )
        else:
            budget_chk = _check(
                CheckState.FAIL,
                "exceeds available customer budget",
                price_cents=total_price,
                effective_cap_cents=effective_cap,
                budget_cents=budget_cents,
                remaining_budget_cents=remaining_budget_cents,
            )
            rejection_reasons.append(
                f"Price {total_price} cents exceeds available budget cap {effective_cap} cents."
            )

    checks = (exists_chk, type_chk, size_chk, stock_chk, delivery_chk, price_chk, budget_chk)
    states = [c.state for c in checks]
    if CheckState.FAIL in states:
        overall = CheckState.FAIL
    elif CheckState.UNKNOWN in states:
        overall = CheckState.UNKNOWN
    else:
        overall = CheckState.PASS

    result = VerificationResult(
        exists_in_catalogue=exists_chk,
        correct_part_type=type_chk,
        size_available=size_chk,
        stock_available=stock_chk,
        delivery_feasible=delivery_chk,
        price_known=price_chk,
        budget_feasible=budget_chk,
        overall=overall,
        engine_version=ENGINE_VERSION,
        evaluated_on=evaluated_on,
    )
    return result, matched_variant, rejection_reasons


def missing_customer_inputs_for_part(
    part: RequestedPart,
    brief: CreativeBrief,
) -> list[UnmetReason]:
    """Return any customer-input reasons blocking verification for `part`."""
    missing: list[UnmetReason] = []
    req_size = effective_requested_size(part, brief_has_any_size=bool(brief.sizes))
    if req_size is None:
        missing.append(UnmetReason.CUSTOMER_SIZE_REQUIRED)
    if brief.event_date is None and part.mandatory_constraints.must_arrive_by is None:
        missing.append(UnmetReason.EVENT_DATE_REQUIRED)
    if brief.budget_cents is None and part.mandatory_constraints.max_price_cents is None:
        missing.append(UnmetReason.BUDGET_REQUIRED)
    return missing


def classify_supply_unmet_reasons(
    part: RequestedPart,
    catalogue: Iterable[Product],
    *,
    evaluated_on: date,
    event_date: date | None,
    budget_cents: int | None,
    remaining_budget_cents: int | None,
    brief_has_any_size: bool = True,
) -> tuple[list[UnmetReason], str]:
    """Explain deterministically why an input-complete part could not be satisfied."""
    matching_type_results: list[tuple[Product, VerificationResult]] = []
    standalone_passing: list[Product] = []

    for prod in catalogue:
        if not prod.active:
            continue
        vr_standalone, _, _ = verify_product_for_part(
            part,
            prod,
            evaluated_on=evaluated_on,
            event_date=event_date,
            budget_cents=budget_cents,
            remaining_budget_cents=None,
            brief_has_any_size=brief_has_any_size,
        )
        if vr_standalone.correct_part_type.state == CheckState.PASS:
            matching_type_results.append((prod, vr_standalone))
            if vr_standalone.overall == CheckState.PASS:
                standalone_passing.append(prod)

    if not matching_type_results:
        attrs = []
        if part.mandatory_constraints.required_colours or part.desired_attributes.colours:
            attrs.append("/".join(part.mandatory_constraints.required_colours or part.desired_attributes.colours))
        if part.mandatory_constraints.required_materials or part.desired_attributes.materials:
            attrs.append("/".join(part.mandatory_constraints.required_materials or part.desired_attributes.materials))
        if part.mandatory_constraints.required_garment_keywords or part.desired_attributes.garment_keywords:
            attrs.append(
                "/".join(part.mandatory_constraints.required_garment_keywords or part.desired_attributes.garment_keywords)
            )
        desc = " ".join(attrs) if attrs else part.part_type.value.lower().replace("_", " ")
        return (
            [UnmetReason.NO_MATCHING_PRODUCT],
            f"Not on offer yet: no catalogue product matches '{desc}' ({part.part_type.value}).",
        )

    if standalone_passing and remaining_budget_cents is not None:
        cheapest = min(p.price_cents for p in standalone_passing if p.price_cents is not None)
        return (
            [UnmetReason.BUDGET_EXHAUSTED_BY_OTHER_PARTS],
            f"Not on offer within remaining budget: matching items start at R{cheapest / 100:.2f}, "
            f"but only R{remaining_budget_cents / 100:.2f} remains after earlier parts.",
        )

    reasons: list[UnmetReason] = []
    for _, vr in matching_type_results:
        if vr.price_known.state == CheckState.FAIL and UnmetReason.PRICE_UNKNOWN not in reasons:
            reasons.append(UnmetReason.PRICE_UNKNOWN)
        if vr.size_available.state == CheckState.FAIL and UnmetReason.SIZE_UNAVAILABLE not in reasons:
            reasons.append(UnmetReason.SIZE_UNAVAILABLE)
        if (
            vr.size_available.state == CheckState.PASS
            and vr.stock_available.state == CheckState.FAIL
            and UnmetReason.OUT_OF_STOCK not in reasons
        ):
            reasons.append(UnmetReason.OUT_OF_STOCK)
        if vr.delivery_feasible.state == CheckState.FAIL and UnmetReason.DELIVERY_TOO_LATE not in reasons:
            reasons.append(UnmetReason.DELIVERY_TOO_LATE)
        if (
            vr.price_known.state == CheckState.PASS
            and vr.budget_feasible.state == CheckState.FAIL
            and UnmetReason.OVER_BUDGET not in reasons
        ):
            reasons.append(UnmetReason.OVER_BUDGET)

    if not reasons:
        reasons = [UnmetReason.NO_MATCHING_PRODUCT]

    req_size = effective_requested_size(part, brief_has_any_size=brief_has_any_size)
    primary = reasons[0]
    explanations = {
        UnmetReason.SIZE_UNAVAILABLE: f"Not on offer yet in size {req_size}.",
        UnmetReason.OUT_OF_STOCK: f"Matching item is out of stock in size {req_size}.",
        UnmetReason.DELIVERY_TOO_LATE: "Matching item cannot be delivered before the event date.",
        UnmetReason.OVER_BUDGET: "Matching items exceed the customer's budget.",
        UnmetReason.PRICE_UNKNOWN: "Matching catalogue item has no confirmed price (price on request).",
        UnmetReason.NO_MATCHING_PRODUCT: "No matching product in the searched catalogues.",
    }
    return reasons, explanations.get(primary, "Not on offer yet.")


def revalidate_and_build_enquiry(
    *,
    enquiry_id: str,
    composition: Composition,
    brief: CreativeBrief,
    merchant_id: str,
    customer_authorized: bool,
    catalogue_by_id: dict[str, Product],
    evaluated_on: date,
    now: datetime | None = None,
    requested_part_ids: list[str] | None = None,
    quantities_by_part_id: dict[str, int] | None = None,
    notes: str | None = None,
) -> QuoteEnquiry:
    """Server-side revalidation and QuoteEnquiry construction (Correction B).

    - Rejects un-authorized submissions immediately.
    - Re-reads every selected item from `catalogue_by_id` (live price, live stock,
      merchant ownership, delivery lead days) and verifies against `brief`.
    - If `requested_part_ids` explicitly includes a part belonging to another merchant,
      raises VerificationError (incorrect merchant routing).
    - If `requested_part_ids` is None, scopes the enquiry to `merchant_id`'s selected
      parts and records any other merchants' parts in `excluded_parts_other_merchants`.
    """
    if customer_authorized is not True:
        raise VerificationError(
            "Customer authorization is required before sending a quote enquiry.",
            code="CUSTOMER_AUTHORIZATION_REQUIRED",
        )
    if brief.event_date is None:
        raise VerificationError(
            "Event date is required before revalidating a quote enquiry.",
            code="EVENT_DATE_REQUIRED",
        )

    ts = now or datetime.now(timezone.utc)
    parts_by_id = {p.part_id: p for p in brief.requested_parts}
    selected_by_id = {sp.part_id: sp for sp in composition.selected_parts}
    quantities = quantities_by_part_id or {}

    if requested_part_ids is not None:
        target_selected: list[SelectedPart] = []
        for pid in requested_part_ids:
            if pid not in selected_by_id:
                raise VerificationError(
                    f"Part {pid} is not a verified selected part in composition {composition.composition_id}.",
                    code="PART_NOT_SELECTED",
                )
            target_selected.append(selected_by_id[pid])
        excluded_other: list[str] = [
            sp.part_id
            for sp in composition.selected_parts
            if sp.part_id not in set(requested_part_ids) and sp.merchant_id != merchant_id
        ]
    else:
        target_selected = [sp for sp in composition.selected_parts if sp.merchant_id == merchant_id]
        excluded_other = [sp.part_id for sp in composition.selected_parts if sp.merchant_id != merchant_id]

    if not target_selected:
        raise VerificationError(
            f"Composition {composition.composition_id} has no selected items for merchant {merchant_id}.",
            code="NO_ITEMS_FOR_MERCHANT",
        )

    revalidations: list[ItemRevalidation] = []
    line_items: list[LineItem] = []
    running_total = 0

    for sp in target_selected:
        qty = quantities.get(sp.part_id, 1)
        live_product = catalogue_by_id.get(sp.product_id)
        req_part = parts_by_id.get(sp.part_id) or RequestedPart(
            part_id=sp.part_id,
            brief_id=brief.brief_id,
            part_type=sp.part_type,
        )
        # Ensure requested size reflects the selected variant size.
        if req_part.mandatory_constraints.size is None:
            req_part = req_part.model_copy(
                update={
                    "mandatory_constraints": req_part.mandatory_constraints.model_copy(
                        update={"size": sp.size}
                    )
                }
            )

        remaining_cap = (
            (brief.budget_cents - running_total) if brief.budget_cents is not None else None
        )
        vr, live_variant, _ = verify_product_for_part(
            req_part,
            live_product,
            evaluated_on=evaluated_on,
            event_date=brief.event_date,
            budget_cents=brief.budget_cents,
            remaining_budget_cents=remaining_cap,
            variant_id=sp.variant_id,
            required_quantity=qty,
            brief_has_any_size=True,
        )

        actual_merchant = live_product.merchant_id if live_product is not None else sp.merchant_id
        belongs = actual_merchant == merchant_id and sp.merchant_id == merchant_id
        verified_price = (
            live_product.price_cents
            if (live_product is not None and isinstance(live_product.price_cents, int) and live_product.price_cents > 0)
            else None
        )
        verified_stock = live_variant.stock_quantity if live_variant is not None else None

        # Price drift check: if catalogue price changed since composition, fail closed.
        if verified_price is not None and verified_price != sp.unit_price_cents:
            vr = vr.model_copy(
                update={
                    "price_known": _check(
                        CheckState.FAIL,
                        "catalogue price changed since composition; re-compose before enquiry",
                        composition_price_cents=sp.unit_price_cents,
                        live_price_cents=verified_price,
                    ),
                    "overall": CheckState.FAIL,
                }
            )

        revalidations.append(
            ItemRevalidation(
                part_id=sp.part_id,
                product_id=sp.product_id,
                variant_id=sp.variant_id,
                merchant_id=actual_merchant,
                belongs_to_addressed_merchant=belongs,
                verified_unit_price_cents=verified_price,
                verified_stock_quantity=verified_stock,
                verification_result=vr,
            )
        )

        if belongs and vr.overall == CheckState.PASS and verified_price is not None:
            running_total += verified_price * qty
            line_items.append(
                LineItem(
                    part_id=sp.part_id,
                    product_id=sp.product_id,
                    variant_id=sp.variant_id,
                    merchant_id=merchant_id,
                    product_name=live_product.name if live_product else sp.product_name,
                    size=live_variant.size if live_variant else sp.size,
                    quantity=qty,
                    unit_price_cents=verified_price,
                )
            )

    all_pass = bool(revalidations) and all(
        rv.belongs_to_addressed_merchant and rv.verification_result.overall == CheckState.PASS
        for rv in revalidations
    )
    receipt = ValidationReceipt(
        revalidated_at=ts,
        engine_version=ENGINE_VERSION,
        evaluated_on=evaluated_on,
        event_date=brief.event_date,
        budget_cents=brief.budget_cents,
        items=revalidations,
        all_items_pass=all_pass,
        excluded_parts_other_merchants=excluded_other,
    )
    receipt.receipt_digest = receipt.compute_digest()

    if any(not rv.belongs_to_addressed_merchant for rv in revalidations):
        raise VerificationError(
            f"Incorrect merchant routing: one or more items do not belong to {merchant_id}.",
            code="INCORRECT_MERCHANT_ROUTING",
            receipt=receipt,
        )
    if not receipt.all_items_pass:
        raise VerificationError(
            "Revalidation failed immediately before enquiry submission.",
            code="REVALIDATION_FAILED",
            receipt=receipt,
        )

    return QuoteEnquiry(
        enquiry_id=enquiry_id,
        composition_id=composition.composition_id,
        merchant_id=merchant_id,
        customer_requirements=CustomerRequirements(
            sizes=dict(brief.sizes),
            notes=notes,
            location=brief.location,
        ),
        line_items=line_items,
        event_date=brief.event_date,
        known_total_cents=running_total,
        customer_authorized=True,
        authorized_at=ts,
        status=EnquiryStatus.SENT_TO_DEMO_INBOX,
        created_at=ts,
        validation_receipt=receipt,
    )
