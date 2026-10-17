"""Automated tests for the deterministic verification engine, matching honesty,
configuration boundary and LLM retry/fallback contract (Section 4 & 5).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import httpx
import pytest

from goa.brief import apply_customer_sizes, parse_brief_rule_based
from goa.compose import compose_outfit, swap_part_in_composition
from goa.config import load_llm_config
from goa.examples import CANONICAL_PROMPT
from goa.gaps import aggregate_demand_gaps, build_demand_gaps_for_composition
from goa.llm import interpret_brief
from goa.match import rank_and_verify_candidates
from goa.rules import (
    VerificationError,
    revalidate_and_build_enquiry,
    verify_product_for_part,
)
from goa.schemas import (
    CheckState,
    CompositionStatus,
    CreativeBrief,
    DesiredAttributes,
    Formality,
    GapSourceType,
    InterpretationSource,
    MandatoryConstraints,
    MatchMethod,
    PartOrigin,
    PartStatus,
    PartType,
    Product,
    ProductSourceType,
    ProductVariant,
    RequestedPart,
    SelectedBy,
    UnmetReason,
)
from goa.store import GoaStore

EVAL_DATE = date(2026, 10, 18)
EVENT_DATE = date(2026, 12, 12)
T0 = datetime(2026, 10, 18, 0, 0, tzinfo=timezone.utc)


def _make_product(
    *,
    product_id: str = "prd_test_dress",
    merchant_id: str = "mer_fynbos_atelier",
    name: str = "Emerald Linen Dress",
    part_type: PartType = PartType.DRESS_OR_SUIT,
    colour: str = "emerald green",
    material: str = "linen",
    style_tags: list[str] | None = None,
    formality: Formality = Formality.SMART_CASUAL,
    price_cents: int | None = 120000,
    delivery_lead_days: int = 4,
    size: str = "M",
    stock_quantity: int = 3,
    active: bool = True,
) -> Product:
    return Product(
        product_id=product_id,
        merchant_id=merchant_id,
        name=name,
        description=f"Synthetic {colour} {material} {name}",
        part_type=part_type,
        colour=colour,
        material=material,
        style_tags=style_tags if style_tags is not None else ["dress", "elegant", "breathable", "rewearable"],
        formality=formality,
        image_url=f"/catalogue/{product_id}.svg",
        image_licence="PROJECT_ORIGINAL_ARTWORK_LICENCE_PENDING_OWNER",
        image_attribution="Original vector illustration.",
        price_cents=price_cents,
        currency="ZAR",
        delivery_lead_days=delivery_lead_days,
        active=active,
        source_type=ProductSourceType.SYNTHETIC_DEMO,
        variants=[
            ProductVariant(
                variant_id=f"var_{product_id[4:]}_{size.lower()}",
                size=size,
                stock_quantity=stock_quantity,
            )
        ],
    )


def _make_brief_with_parts(
    parts: list[RequestedPart],
    *,
    brief_id: str = "brf_test",
    budget_cents: int | None = 250000,
    sizes: dict[PartType, str] | None = None,
    event_date: date | None = EVENT_DATE,
) -> CreativeBrief:
    sz = sizes if sizes is not None else {PartType.DRESS_OR_SUIT: "M", PartType.SHOES: "UK6", PartType.OUTER_LAYER: "M"}
    return CreativeBrief(
        brief_id=brief_id,
        session_id="ses_test",
        raw_prompt="Test graduation brief",
        occasion="graduation",
        event_date=event_date,
        location="Cape Town",
        budget_cents=budget_cents,
        preferred_colours=["green"],
        formality=Formality.SMART_CASUAL,
        style_preferences=["elegant"],
        sustainability_or_reuse_preferences=["rewearable"],
        sizes=sz,
        constraints=[],
        requested_parts=parts,
        uncertainties=[],
        interpretation_source=InterpretationSource.RULE_BASED_FALLBACK,
        created_at=T0,
    )


# --------------------------------------------------------- 1. Valid composition


def test_valid_composition():
    dress = _make_product(product_id="prd_dress_ok", price_cents=120000, size="M", stock_quantity=2)
    shoes = _make_product(
        product_id="prd_shoes_ok",
        name="Tan Block Heel Sandals",
        part_type=PartType.SHOES,
        colour="tan",
        material="leather",
        style_tags=["sandals", "comfortable"],
        price_cents=80000,
        size="UK6",
        stock_quantity=4,
    )
    parts = [
        RequestedPart(
            part_id="prt_1",
            brief_id="brf_test",
            part_type=PartType.DRESS_OR_SUIT,
            desired_attributes=DesiredAttributes(colours=["green"]),
            mandatory_constraints=MandatoryConstraints(size="M"),
        ),
        RequestedPart(
            part_id="prt_2",
            brief_id="brf_test",
            part_type=PartType.SHOES,
            desired_attributes=DesiredAttributes(colours=["tan"]),
            mandatory_constraints=MandatoryConstraints(size="UK6"),
        ),
    ]
    brief = _make_brief_with_parts(parts, budget_cents=250000)
    comp, _, gaps = compose_outfit(brief, [dress, shoes], evaluated_on=EVAL_DATE)

    assert comp.validation_status == CompositionStatus.VERIFIED_COMPLETE
    assert len(comp.selected_parts) == 2
    assert not comp.unmet_parts
    assert not comp.pending_input_parts
    assert comp.total_price_cents == 200000
    assert comp.merchant_scope == ["mer_fynbos_atelier"]
    assert gaps == []


# ----------------------------------------------------------- 2. Missing product


def test_missing_product():
    part = RequestedPart(
        part_id="prt_1",
        brief_id="brf_test",
        part_type=PartType.DRESS_OR_SUIT,
        mandatory_constraints=MandatoryConstraints(size="M"),
    )
    vr, variant, rejections = verify_product_for_part(
        part,
        None,
        evaluated_on=EVAL_DATE,
        event_date=EVENT_DATE,
        budget_cents=250000,
    )
    assert vr.exists_in_catalogue.state == CheckState.FAIL
    assert vr.overall == CheckState.FAIL
    assert variant is None
    assert rejections


# ---------------------------------------------------------- 3. Unavailable size


def test_unavailable_size():
    dress_only_s = _make_product(size="S", stock_quantity=5)
    part_wants_xl = RequestedPart(
        part_id="prt_1",
        brief_id="brf_test",
        part_type=PartType.DRESS_OR_SUIT,
        mandatory_constraints=MandatoryConstraints(size="XL"),
    )
    brief = _make_brief_with_parts([part_wants_xl], sizes={PartType.DRESS_OR_SUIT: "XL"})
    comp, candidates, gaps = compose_outfit(brief, [dress_only_s], evaluated_on=EVAL_DATE)

    vr = candidates["prt_1"][0].verification_result
    assert vr.size_available.state == CheckState.FAIL
    assert vr.overall == CheckState.FAIL
    assert comp.validation_status == CompositionStatus.EMPTY
    assert comp.unmet_parts[0].reasons == [UnmetReason.SIZE_UNAVAILABLE]
    assert len(gaps) == 1
    assert gaps[0].reason == UnmetReason.SIZE_UNAVAILABLE


# ---------------------------------------------------------------- 4. Zero stock


def test_zero_stock():
    dress_zero = _make_product(size="M", stock_quantity=0)
    part = RequestedPart(
        part_id="prt_1",
        brief_id="brf_test",
        part_type=PartType.DRESS_OR_SUIT,
        mandatory_constraints=MandatoryConstraints(size="M"),
    )
    brief = _make_brief_with_parts([part])
    comp, candidates, gaps = compose_outfit(brief, [dress_zero], evaluated_on=EVAL_DATE)

    vr = candidates["prt_1"][0].verification_result
    assert vr.size_available.state == CheckState.PASS
    assert vr.stock_available.state == CheckState.FAIL
    assert vr.overall == CheckState.FAIL
    assert not comp.selected_parts
    assert comp.unmet_parts[0].reasons == [UnmetReason.OUT_OF_STOCK]
    assert gaps[0].reason == UnmetReason.OUT_OF_STOCK


# ------------------------------------------------------------- 5. Late delivery


def test_late_delivery():
    slow_gown = _make_product(delivery_lead_days=70, size="M", stock_quantity=3)
    part = RequestedPart(
        part_id="prt_1",
        brief_id="brf_test",
        part_type=PartType.DRESS_OR_SUIT,
        mandatory_constraints=MandatoryConstraints(size="M"),
    )
    brief = _make_brief_with_parts([part])
    comp, candidates, gaps = compose_outfit(brief, [slow_gown], evaluated_on=EVAL_DATE)

    vr = candidates["prt_1"][0].verification_result
    assert vr.delivery_feasible.state == CheckState.FAIL
    assert vr.overall == CheckState.FAIL
    assert not comp.selected_parts
    assert comp.unmet_parts[0].reasons == [UnmetReason.DELIVERY_TOO_LATE]
    assert gaps[0].reason == UnmetReason.DELIVERY_TOO_LATE


# ----------------------------------------------------------- 6. Budget exceeded


def test_budget_exceeded():
    # Single item exceeds total budget, AND cumulative items exceed remaining budget.
    expensive_dress = _make_product(product_id="prd_exp", price_cents=260000, size="M", stock_quantity=2)
    part = RequestedPart(
        part_id="prt_1",
        brief_id="brf_test",
        part_type=PartType.DRESS_OR_SUIT,
        mandatory_constraints=MandatoryConstraints(size="M"),
    )
    brief = _make_brief_with_parts([part], budget_cents=250000)
    comp, candidates, gaps = compose_outfit(brief, [expensive_dress], evaluated_on=EVAL_DATE)

    assert candidates["prt_1"][0].verification_result.budget_feasible.state == CheckState.FAIL
    assert not comp.selected_parts
    assert comp.unmet_parts[0].reasons == [UnmetReason.OVER_BUDGET]
    assert gaps[0].reason == UnmetReason.OVER_BUDGET

    # Cumulative budget test: dress (R1,800) + shoes (R900) > R2,500 budget
    dress_ok = _make_product(product_id="prd_d1800", price_cents=180000, size="M", stock_quantity=2)
    shoes_900 = _make_product(
        product_id="prd_s900",
        part_type=PartType.SHOES,
        price_cents=90000,
        size="UK6",
        stock_quantity=2,
    )
    parts2 = [
        RequestedPart(part_id="prt_1", brief_id="brf_test", part_type=PartType.DRESS_OR_SUIT, mandatory_constraints=MandatoryConstraints(size="M")),
        RequestedPart(part_id="prt_2", brief_id="brf_test", part_type=PartType.SHOES, mandatory_constraints=MandatoryConstraints(size="UK6")),
    ]
    brief2 = _make_brief_with_parts(parts2, budget_cents=250000)
    comp2, _, gaps2 = compose_outfit(brief2, [dress_ok, shoes_900], evaluated_on=EVAL_DATE)

    assert comp2.validation_status == CompositionStatus.VERIFIED_PARTIAL
    assert len(comp2.selected_parts) == 1
    assert comp2.total_price_cents == 180000
    assert comp2.unmet_parts[0].reasons == [UnmetReason.BUDGET_EXHAUSTED_BY_OTHER_PARTS]
    assert gaps2[0].reason == UnmetReason.BUDGET_EXHAUSTED_BY_OTHER_PARTS


# ------------------------------------------------------------- 7. Missing price


def test_missing_price():
    poa_necklace = _make_product(
        product_id="prd_poa",
        part_type=PartType.ACCESSORY,
        price_cents=None,
        size="ONE_SIZE",
        stock_quantity=3,
    )
    part = RequestedPart(
        part_id="prt_1",
        brief_id="brf_test",
        part_type=PartType.ACCESSORY,
        origin=PartOrigin.EXPLICIT,
    )
    brief = _make_brief_with_parts([part])
    comp, candidates, gaps = compose_outfit(brief, [poa_necklace], evaluated_on=EVAL_DATE)

    vr = candidates["prt_1"][0].verification_result
    assert vr.price_known.state == CheckState.FAIL
    assert vr.budget_feasible.state == CheckState.FAIL
    assert vr.overall == CheckState.FAIL
    assert not comp.selected_parts
    assert comp.unmet_parts[0].reasons == [UnmetReason.PRICE_UNKNOWN]
    assert gaps[0].reason == UnmetReason.PRICE_UNKNOWN


# ------------------------------------------------------- 8. Partial composition


def test_partial_composition():
    dress = _make_product(product_id="prd_dress_ok", price_cents=120000, size="M", stock_quantity=2)
    ivory_jacket = _make_product(
        product_id="prd_ivory_jkt",
        name="Ivory Linen Jacket",
        part_type=PartType.OUTER_LAYER,
        colour="ivory",
        material="linen",
        style_tags=["jacket", "lightweight"],
        price_cents=89900,
        size="M",
        stock_quantity=2,
    )
    parts = [
        RequestedPart(
            part_id="prt_1",
            brief_id="brf_test",
            part_type=PartType.DRESS_OR_SUIT,
            desired_attributes=DesiredAttributes(colours=["green"]),
            mandatory_constraints=MandatoryConstraints(size="M", required_colours=["green"]),
        ),
        RequestedPart(
            part_id="prt_2",
            brief_id="brf_test",
            part_type=PartType.OUTER_LAYER,
            desired_attributes=DesiredAttributes(colours=["green"], materials=["linen"], garment_keywords=["jacket"]),
            mandatory_constraints=MandatoryConstraints(
                size="M",
                required_colours=["green"],
                required_materials=["linen"],
                required_garment_keywords=["jacket"],
            ),
        ),
    ]
    brief = _make_brief_with_parts(parts, budget_cents=250000)
    comp, _, gaps = compose_outfit(brief, [dress, ivory_jacket], evaluated_on=EVAL_DATE)

    assert comp.validation_status == CompositionStatus.VERIFIED_PARTIAL
    assert len(comp.selected_parts) == 1
    assert comp.selected_parts[0].part_id == "prt_1"
    assert len(comp.unmet_parts) == 1
    assert comp.unmet_parts[0].part_id == "prt_2"
    assert comp.unmet_parts[0].reasons == [UnmetReason.NO_MATCHING_PRODUCT]
    assert len(gaps) == 1


# ------------------------------------------------ 9. Incorrect merchant routing


def test_incorrect_merchant_routing():
    dress_fynbos = _make_product(
        product_id="prd_dress_fyn", merchant_id="mer_fynbos_atelier", price_cents=120000, size="M", stock_quantity=2
    )
    shoes_karoo = _make_product(
        product_id="prd_shoes_kar",
        merchant_id="mer_karoo_cobble",
        part_type=PartType.SHOES,
        price_cents=80000,
        size="UK6",
        stock_quantity=2,
    )
    parts = [
        RequestedPart(part_id="prt_1", brief_id="brf_test", part_type=PartType.DRESS_OR_SUIT, mandatory_constraints=MandatoryConstraints(size="M")),
        RequestedPart(part_id="prt_2", brief_id="brf_test", part_type=PartType.SHOES, mandatory_constraints=MandatoryConstraints(size="UK6")),
    ]
    brief = _make_brief_with_parts(parts, budget_cents=250000)
    catalogue = [dress_fynbos, shoes_karoo]
    cat_by_id = {p.product_id: p for p in catalogue}
    comp, _, _ = compose_outfit(brief, catalogue, evaluated_on=EVAL_DATE)

    # Attempting to route Karoo's shoes (`prt_2`) to Fynbos Atelier must fail closed.
    with pytest.raises(VerificationError) as exc_info:
        revalidate_and_build_enquiry(
            enquiry_id="enq_bad_route",
            composition=comp,
            brief=brief,
            merchant_id="mer_fynbos_atelier",
            customer_authorized=True,
            catalogue_by_id=cat_by_id,
            evaluated_on=EVAL_DATE,
            requested_part_ids=["prt_1", "prt_2"],
        )
    assert exc_info.value.code == "INCORRECT_MERCHANT_ROUTING"
    assert exc_info.value.receipt is not None
    assert exc_info.value.receipt.all_items_pass is False

    # Scoping to Fynbos Atelier without forcing foreign part_ids sends only Fynbos's item
    # and records Karoo's part in `excluded_parts_other_merchants`.
    enquiry = revalidate_and_build_enquiry(
        enquiry_id="enq_scoped_ok",
        composition=comp,
        brief=brief,
        merchant_id="mer_fynbos_atelier",
        customer_authorized=True,
        catalogue_by_id=cat_by_id,
        evaluated_on=EVAL_DATE,
    )
    assert [li.part_id for li in enquiry.line_items] == ["prt_1"]
    assert enquiry.validation_receipt.excluded_parts_other_merchants == ["prt_2"]


# ------------------------------------ 10. Revalidation failure before enquiry


def test_revalidation_failure_before_enquiry():
    dress = _make_product(product_id="prd_dress_ok", price_cents=120000, size="M", stock_quantity=1)
    part = RequestedPart(part_id="prt_1", brief_id="brf_test", part_type=PartType.DRESS_OR_SUIT, mandatory_constraints=MandatoryConstraints(size="M"))
    brief = _make_brief_with_parts([part], budget_cents=250000)
    comp, _, _ = compose_outfit(brief, [dress], evaluated_on=EVAL_DATE)

    # Simulate stock dropping to 0 between composition and enquiry submission.
    depleted = _make_product(product_id="prd_dress_ok", price_cents=120000, size="M", stock_quantity=0)
    with pytest.raises(VerificationError) as exc_info:
        revalidate_and_build_enquiry(
            enquiry_id="enq_depleted",
            composition=comp,
            brief=brief,
            merchant_id="mer_fynbos_atelier",
            customer_authorized=True,
            catalogue_by_id={"prd_dress_ok": depleted},
            evaluated_on=EVAL_DATE,
        )
    assert exc_info.value.code == "REVALIDATION_FAILED"
    assert exc_info.value.receipt is not None
    assert exc_info.value.receipt.all_items_pass is False
    assert exc_info.value.receipt.items[0].verification_result.stock_available.state == CheckState.FAIL


# ----------------------- 11. Attempted enquiry without customer authorization


def test_attempted_enquiry_without_customer_authorization():
    dress = _make_product(product_id="prd_dress_ok", price_cents=120000, size="M", stock_quantity=2)
    part = RequestedPart(part_id="prt_1", brief_id="brf_test", part_type=PartType.DRESS_OR_SUIT, mandatory_constraints=MandatoryConstraints(size="M"))
    brief = _make_brief_with_parts([part], budget_cents=250000)
    comp, _, _ = compose_outfit(brief, [dress], evaluated_on=EVAL_DATE)

    with pytest.raises(VerificationError) as exc_info:
        revalidate_and_build_enquiry(
            enquiry_id="enq_no_auth",
            composition=comp,
            brief=brief,
            merchant_id="mer_fynbos_atelier",
            customer_authorized=False,
            catalogue_by_id={"prd_dress_ok": dress},
            evaluated_on=EVAL_DATE,
        )
    assert exc_info.value.code == "CUSTOMER_AUTHORIZATION_REQUIRED"


# -------------------------------------------------- 12. Correct gap aggregation


def test_correct_gap_aggregation_and_missing_input_exclusion():
    store = GoaStore(":memory:")
    products = store.list_products()

    # Unresolved Thandi prompt (no sizes): must produce pending_input_parts and ZERO DemandGaps.
    unresolved = parse_brief_rule_based(CANONICAL_PROMPT, brief_id="brf_thandi_raw")
    comp_raw, _, gaps_raw = compose_outfit(unresolved, products, evaluated_on=EVAL_DATE)
    assert comp_raw.validation_status == CompositionStatus.EMPTY
    assert not comp_raw.selected_parts
    assert not comp_raw.unmet_parts
    assert len(comp_raw.pending_input_parts) == 4
    assert gaps_raw == []

    # Two briefs explicitly requesting a green linen jacket (which nobody stocks) -> aggregated count = 2.
    all_gaps = []
    for idx in (1, 2):
        part = RequestedPart(
            part_id=f"prt_jkt_{idx}",
            brief_id=f"brf_g{idx}",
            part_type=PartType.OUTER_LAYER,
            origin=PartOrigin.EXPLICIT,
            desired_attributes=DesiredAttributes(colours=["green"], materials=["linen"], garment_keywords=["jacket"]),
            mandatory_constraints=MandatoryConstraints(
                size="M",
                required_colours=["green"],
                required_materials=["linen"],
                required_garment_keywords=["jacket"],
            ),
        )
        b = _make_brief_with_parts([part], brief_id=f"brf_g{idx}")
        c, _, g = compose_outfit(
            b, products, evaluated_on=EVAL_DATE, gap_source_type=GapSourceType.SCRIPTED_EVALUATION
        )
        assert len(c.unmet_parts) == 1
        all_gaps.extend(g)

    rows = aggregate_demand_gaps(all_gaps, total_briefs=20)
    assert len(rows) == 1
    assert rows[0]["requested_item_label"] == "green linen jacket"
    assert rows[0]["brief_count"] == 2
    assert "2 of 20 briefs requested a green linen jacket" in str(rows[0]["summary"])


# ----------------------- Customer remix/swap & config/LLM/matching tests


def test_customer_swap_preserves_authorship_and_verifies():
    store = GoaStore(":memory:")
    products = store.list_products()
    cat_by_id = store.products_by_id()

    brief = apply_customer_sizes(
        parse_brief_rule_based(CANONICAL_PROMPT, brief_id="brf_swap"),
        {PartType.DRESS_OR_SUIT: "M", PartType.SHOES: "UK6", PartType.OUTER_LAYER: "M"},
    )
    comp, _, _ = compose_outfit(brief, products, evaluated_on=EVAL_DATE)
    dress_part_id = brief.requested_parts[0].part_id

    remixed = swap_part_in_composition(
        comp,
        brief,
        part_id=dress_part_id,
        new_product_id="prd_sage_tiered_cotton_maxi_dress",
        catalogue_by_id=cat_by_id,
        evaluated_on=EVAL_DATE,
    )
    swapped = next(sp for sp in remixed.selected_parts if sp.part_id == dress_part_id)
    assert swapped.product_id == "prd_sage_tiered_cotton_maxi_dress"
    assert swapped.selected_by == SelectedBy.CUSTOMER

    # Attempting to swap to a 70-day made-to-order gown must be rejected by rules.
    with pytest.raises(VerificationError):
        swap_part_in_composition(
            comp,
            brief,
            part_id=dress_part_id,
            new_product_id="prd_forest_green_made_to_order_gown",
            catalogue_by_id=cat_by_id,
            evaluated_on=EVAL_DATE,
        )


def test_config_boundary_resolves_primary_and_busi_aliases():
    cfg_empty = load_llm_config({})
    assert not cfg_empty.is_configured
    assert cfg_empty.base_url is None

    cfg_alias = load_llm_config(
        {
            "TOKEN_FACTORY_BASE_URL": "https://example.amd.test/v1",
            "TOKEN_FACTORY_API_KEY": "rc-test-key",
            "GEMMA_MODEL": "google/gemma-4-31b-it",
        }
    )
    assert cfg_alias.is_configured
    assert cfg_alias.base_url_source_env == "TOKEN_FACTORY_BASE_URL"
    assert cfg_alias.model_source_env == "GEMMA_MODEL"
    assert "rc-test-key" not in str(cfg_alias.public_summary())


def test_llm_adapter_retries_once_on_invalid_json_then_falls_back():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json={"choices": [{"message": {"content": "not valid json {{"}}]})

    cfg = load_llm_config(
        {
            "GOA_LLM_BASE_URL": "https://mock.tokenfactory.local/v1",
            "GOA_LLM_API_KEY": "rc-mock",
            "GOA_LLM_MODEL": "google/gemma-4-31b-it",
        }
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    brief, receipt = interpret_brief(CANONICAL_PROMPT, config=cfg, http_client=client)

    assert len(calls) == 2  # initial attempt + 1 retry
    assert receipt.attempts == 2
    assert receipt.succeeded is False
    assert receipt.fallback_used is True
    assert brief.interpretation_source == InterpretationSource.RULE_BASED_FALLBACK
    assert brief.sizes == {}


def test_embedding_method_refuses_without_real_embedding_scorer():
    dress = _make_product()
    part = RequestedPart(part_id="prt_1", brief_id="brf_test", part_type=PartType.DRESS_OR_SUIT, mandatory_constraints=MandatoryConstraints(size="M"))
    brief = _make_brief_with_parts([part])
    with pytest.raises(ValueError, match="refusing to label"):
        rank_and_verify_candidates(part, brief, [dress], evaluated_on=EVAL_DATE, method=MatchMethod.EMBEDDING)
