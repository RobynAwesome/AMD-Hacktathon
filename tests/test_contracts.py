"""Contract tests: every public schema parses, examples validate, invariants hold."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from goa import examples as ex
from goa.schemas import (
    PUBLIC_CONTRACTS,
    CheckResult,
    CheckState,
    CompositionStatus,
    DemandGap,
    GapSourceType,
    PartType,
    Product,
    UnmetReason,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas" / "v1"


def test_exported_schemas_are_current():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "export_schemas.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("name", sorted(PUBLIC_CONTRACTS))
def test_json_schema_is_valid_and_example_conforms(name):
    schema = json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert schema["x-goa-schema-version"] == "1.0.0"
    example = json.loads((SCHEMA_DIR / "examples" / f"{name}.example.json").read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema).iter_errors(example))
    assert not errors, [e.message for e in errors]
    # Round-trip through Pydantic.
    PUBLIC_CONTRACTS[name].model_validate(example)


def test_money_rejects_floats():
    data = ex.example_product().model_dump()
    data["price_cents"] = 1299.0
    with pytest.raises(ValidationError):
        Product.model_validate(data)


def test_money_rejects_strings_and_negative():
    data = ex.example_product().model_dump()
    for bad in ("129900", -5, 0):
        data["price_cents"] = bad
        with pytest.raises(ValidationError):
            Product.model_validate(data)


def test_missing_price_is_representable_not_defaulted():
    data = ex.example_product().model_dump()
    data["price_cents"] = None
    assert Product.model_validate(data).price_cents is None


def test_unknown_fields_rejected():
    data = ex.example_merchant().model_dump()
    data["partner_since"] = "2020"
    with pytest.raises(ValidationError):
        type(ex.example_merchant()).model_validate(data)


def test_verification_overall_cannot_claim_pass_with_unknown():
    v = ex.example_verification().model_dump()
    v["size_available"] = CheckResult(state=CheckState.UNKNOWN, reason="no size").model_dump()
    with pytest.raises(ValidationError):
        type(ex.example_verification()).model_validate(v)
    v["overall"] = "UNKNOWN"
    assert type(ex.example_verification()).model_validate(v).overall == CheckState.UNKNOWN


def test_selected_part_must_be_verified():
    comp = ex.example_composition().model_dump()
    comp["selected_parts"][0]["verification_result"]["price_known"] = {
        "state": "FAIL", "reason": "missing", "evidence": {}
    }
    comp["selected_parts"][0]["verification_result"]["overall"] = "FAIL"
    with pytest.raises(ValidationError):
        type(ex.example_composition()).model_validate(comp)


def test_incomplete_composition_cannot_be_complete():
    comp = ex.example_composition().model_dump()
    comp["validation_status"] = CompositionStatus.VERIFIED_COMPLETE
    with pytest.raises(ValidationError):
        type(ex.example_composition()).model_validate(comp)


def test_composition_total_must_match_and_respect_budget():
    comp = ex.example_composition().model_dump()
    comp["total_price_cents"] = 1
    with pytest.raises(ValidationError):
        type(ex.example_composition()).model_validate(comp)
    comp = ex.example_composition().model_dump()
    comp["budget_cents"] = 100000
    with pytest.raises(ValidationError):
        type(ex.example_composition()).model_validate(comp)


def test_brief_parts_must_reference_brief():
    brief = ex.example_brief().model_dump()
    brief["requested_parts"][0]["brief_id"] = "brf_other"
    with pytest.raises(ValidationError):
        type(ex.example_brief()).model_validate(brief)


def test_customer_input_reason_is_not_a_demand_gap():
    with pytest.raises(ValidationError):
        DemandGap(
            gap_id="gap_x", brief_id="brf_x", part_type=PartType.SHOES,
            desired_attributes={}, reason=UnmetReason.CUSTOMER_SIZE_REQUIRED,
            merchant_scope=[], source_type=GapSourceType.DEMO_SESSION, created_at=ex.T0,
        )


def test_enquiry_requires_authorization_literal_true():
    enq = ex.example_quote_enquiry().model_dump()
    enq["customer_authorized"] = False
    with pytest.raises(ValidationError):
        type(ex.example_quote_enquiry()).model_validate(enq)


def test_enquiry_line_items_must_belong_to_addressed_merchant():
    enq = ex.example_quote_enquiry().model_dump()
    enq["line_items"][0]["merchant_id"] = "mer_someone_else"
    with pytest.raises(ValidationError):
        type(ex.example_quote_enquiry()).model_validate(enq)


def test_enquiry_is_always_demo():
    enq = ex.example_quote_enquiry()
    assert enq.is_demo is True
    assert "Not a payment" in enq.disclaimer
