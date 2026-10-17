"""Regression tests for the FEP architecture reconciliation (Checkpoint 2A).

Correction A: Thandi's original prompt has no size -> no invented size, no AVAILABLE status,
              missing input is never an unmet supply part or a demand gap.
Correction B: a QuoteEnquiry cannot validate itself; every line item needs one exact,
              passed, server-issued revalidation with matching price/stock/merchant.
Correction E: project-original artwork is not declared CC0 without an owner dedication.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from goa import examples as ex
from goa.schemas import (
    Composition,
    CompositionStatus,
    CreativeBrief,
    PartStatus,
    PartType,
    PendingInputPart,
    QuoteEnquiry,
    UnmetPart,
    UnmetReason,
    ValidationReceipt,
)

# ------------------------------------------------------------------ Correction A


def test_canonical_thandi_fixture_has_no_invented_size_or_availability():
    brief = ex.example_brief()
    assert "size" not in brief.raw_prompt.lower()
    assert brief.sizes == {}
    for part in brief.requested_parts:
        assert part.mandatory_constraints.size is None
        assert part.status != PartStatus.AVAILABLE
    assert any("size" in u for u in brief.uncertainties)


def test_followup_fixture_records_customer_supplied_size():
    brief = ex.example_brief_followup()
    assert brief.sizes == {PartType.DRESS_OR_SUIT: "M"}
    assert brief.requested_parts[0].mandatory_constraints.size == "M"


def test_brief_rejects_part_size_the_customer_did_not_supply():
    data = ex.example_brief().model_dump()
    data["requested_parts"][0]["mandatory_constraints"]["size"] = "M"
    with pytest.raises(ValidationError, match="did not supply"):
        CreativeBrief.model_validate(data)


def test_unmet_part_rejects_customer_input_reasons():
    with pytest.raises(ValidationError):
        UnmetPart(
            part_id="prt_x", part_type=PartType.SHOES, desired_attributes={},
            reasons=[UnmetReason.CUSTOMER_SIZE_REQUIRED], explanation="x",
        )


def test_pending_input_part_rejects_supply_reasons():
    with pytest.raises(ValidationError):
        PendingInputPart(
            part_id="prt_x", part_type=PartType.SHOES, desired_attributes={},
            missing_inputs=[UnmetReason.OUT_OF_STOCK], explanation="x",
        )


def test_composition_with_pending_input_cannot_be_complete():
    data = ex.example_composition().model_dump()
    data["unmet_parts"] = []
    data["validation_status"] = CompositionStatus.VERIFIED_COMPLETE
    with pytest.raises(ValidationError):
        Composition.model_validate(data)


def test_part_cannot_be_both_pending_and_unmet():
    data = ex.example_composition().model_dump()
    data["pending_input_parts"][0]["part_id"] = data["unmet_parts"][0]["part_id"]
    with pytest.raises(ValidationError, match="exactly one"):
        Composition.model_validate(data)


# ------------------------------------------------------------------ Correction B


def _enquiry_data():
    return ex.example_quote_enquiry().model_dump()


def _resign(data):
    """Recompute a digest as an attacker could, to prove the other checks still bite."""
    receipt = ValidationReceipt.model_validate(data["validation_receipt"])
    data["validation_receipt"]["receipt_digest"] = receipt.compute_digest()
    return data


def test_valid_enquiry_example_passes():
    assert QuoteEnquiry.model_validate(_enquiry_data()).is_demo


def test_tampered_receipt_digest_rejected():
    data = _enquiry_data()
    data["validation_receipt"]["budget_cents"] = 999999
    with pytest.raises(ValidationError, match="digest"):
        QuoteEnquiry.model_validate(data)


def test_line_item_without_revalidation_rejected():
    data = _enquiry_data()
    extra = dict(data["line_items"][0], part_id="prt_unrevalidated")
    data["line_items"].append(extra)
    data["known_total_cents"] *= 2
    with pytest.raises(ValidationError, match="exactly one revalidation"):
        QuoteEnquiry.model_validate(data)


def test_revalidation_for_different_variant_rejected():
    data = _enquiry_data()
    data["line_items"][0]["variant_id"] = "var_example_dress_l"
    with pytest.raises(ValidationError, match="does not match"):
        QuoteEnquiry.model_validate(data)


def test_client_altered_price_rejected():
    data = _enquiry_data()
    data["line_items"][0]["unit_price_cents"] = 1000
    data["known_total_cents"] = 1000
    with pytest.raises(ValidationError, match="verified catalogue price"):
        QuoteEnquiry.model_validate(data)


def test_quantity_above_verified_stock_rejected():
    data = _enquiry_data()
    data["line_items"][0]["quantity"] = 5
    data["known_total_cents"] = 5 * data["line_items"][0]["unit_price_cents"]
    with pytest.raises(ValidationError, match="stock"):
        QuoteEnquiry.model_validate(data)


def test_enquiry_over_budget_rejected_even_with_resigned_receipt():
    data = _enquiry_data()
    data["validation_receipt"]["budget_cents"] = 100000
    _resign(data)
    with pytest.raises(ValidationError, match="budget"):
        QuoteEnquiry.model_validate(data)


def test_receipt_all_items_pass_must_reflect_items():
    data = _enquiry_data()["validation_receipt"]
    data["items"][0]["belongs_to_addressed_merchant"] = False
    with pytest.raises(ValidationError, match="all_items_pass"):
        ValidationReceipt.model_validate(data)


def test_receipt_merchant_mismatch_rejected():
    data = _enquiry_data()
    data["validation_receipt"]["items"][0]["merchant_id"] = "mer_other"
    _resign(data)
    with pytest.raises(ValidationError, match="another merchant"):
        QuoteEnquiry.model_validate(data)


# ------------------------------------------------------------------ Correction E


def test_original_artwork_not_declared_cc0():
    product = ex.example_product()
    assert "CC0" not in product.image_licence
    assert "PENDING_OWNER" in product.image_licence
    assert product.image_attribution
