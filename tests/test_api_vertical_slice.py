"""End-to-end API vertical slice tests for GOA Creative Commerce.

Exercises the complete customer-to-demo-merchant flow over FastAPI:
1. Health and fictional catalogue inspection (3 merchants, 48 products)
2. Unresolved customer prompt (`sizes={}`) -> `NEEDS_CUSTOMER_INPUT`, 0 session demand gaps
3. Follow-up customer size update -> deterministic verification -> `AVAILABLE` parts
4. Customer remix (`SelectedBy.CUSTOMER`) and save (`saved=True`, no purchase intent)
5. Quote enquiry guardrails (403 on unauthorized, 422 on client-supplied `validation_receipt`,
   200 with server-issued `ValidationReceipt` + SHA-256 `receipt_digest`)
6. Fictional merchant demo inbox and data-driven unmet-demand dashboard (`5 of 20 briefs`)
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from goa.app import create_app
from goa.examples import CANONICAL_PROMPT
from goa.store import GoaStore


def make_client() -> TestClient:
    return TestClient(create_app(GoaStore(":memory:")))


def test_health_and_catalogue_endpoints() -> None:
    client = make_client()

    health = client.get("/api/v1/health")
    assert health.status_code == 200
    hdata = health.json()
    assert hdata["status"] == "ok"
    assert hdata["merchant_count"] == 3
    assert hdata["product_count"] == 48
    assert hdata["canonical_prompt"] == CANONICAL_PROMPT

    cat = client.get("/api/v1/catalogue")
    assert cat.status_code == 200
    cdata = cat.json()
    assert len(cdata["merchants"]) == 3
    assert len(cdata["products"]) == 48
    assert all(m["is_fictional"] is True for m in cdata["merchants"])
    assert all(
        p["image_licence"] == "PROJECT_ORIGINAL_ARTWORK_LICENCE_PENDING_OWNER"
        for p in cdata["products"]
    )


def test_customer_to_merchant_vertical_slice_flow() -> None:
    client = make_client()

    # 1. Interpret Thandi's raw prompt without sizes (sizes={})
    resp1 = client.post(
        "/api/v1/briefs/interpret",
        json={"raw_prompt": CANONICAL_PROMPT, "sizes": {}, "match_method": "TAG_OVERLAP"},
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    brief1 = data1["brief"]
    comp1 = data1["composition"]

    assert brief1["sizes"] == {}
    assert all(
        p["status"] == "NEEDS_CUSTOMER_INPUT"
        for p in brief1["requested_parts"]
        if p["part_type"] in ("DRESS_OR_SUIT", "SHOES", "OUTER_LAYER")
    )
    # Garments/footwear without sizes must be routed to pending_input_parts, NOT unmet_parts
    pending_types = {p["part_type"] for p in comp1["pending_input_parts"]}
    assert "DRESS_OR_SUIT" in pending_types
    assert "SHOES" in pending_types
    for p in comp1["pending_input_parts"]:
        assert p["missing_inputs"] == ["CUSTOMER_SIZE_REQUIRED"]
        assert "size" in p["explanation"].lower()

    # Missing customer sizes must NOT create demo session demand gaps
    gaps_initial = client.get("/api/v1/merchants/gaps").json()
    assert gaps_initial["demo_session_gaps_aggregated"] == []

    # 2. Customer supplies follow-up sizes (M, UK6, M)
    brief_id = brief1["brief_id"]
    resp2 = client.post(
        f"/api/v1/briefs/{brief_id}/sizes",
        json={
            "sizes": {"DRESS_OR_SUIT": "M", "SHOES": "UK6", "OUTER_LAYER": "M"},
            "match_method": "TAG_OVERLAP",
        },
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    comp2 = data2["composition"]
    assert comp2["pending_input_parts"] == []
    assert len(comp2["selected_parts"]) >= 3
    assert comp2["total_price_cents"] <= 250000

    # 3. Remix a part with an alternative verified candidate and preserve SelectedBy.CUSTOMER
    comp_id = comp2["composition_id"]
    garment_part = next(
        sp for sp in comp2["selected_parts"] if sp["part_type"] == "DRESS_OR_SUIT"
    )
    garment_candidates = [
        c
        for c in data2["candidates_by_part"][garment_part["part_id"]]
        if c["verification_result"]["overall"] == "PASS"
        and not c["rejection_reasons"]
        and c["product_id"] != garment_part["product_id"]
    ]
    assert len(garment_candidates) >= 1
    alt_cand = garment_candidates[0]

    remix_resp = client.post(
        f"/api/v1/compositions/{comp_id}/remix",
        json={
            "part_id": garment_part["part_id"],
            "product_id": alt_cand["product_id"],
            "variant_id": alt_cand["variant_id"],
        },
    )
    assert remix_resp.status_code == 200
    remixed_comp = remix_resp.json()["composition"]
    remixed_id = remixed_comp["composition_id"]
    swapped_part = next(
        sp for sp in remixed_comp["selected_parts"] if sp["part_id"] == garment_part["part_id"]
    )
    assert swapped_part["product_id"] == alt_cand["product_id"]
    assert swapped_part["selected_by"] == "CUSTOMER"

    # 4. Save composition without commercial commitment
    save_resp = client.post(f"/api/v1/compositions/{remixed_id}/save")
    assert save_resp.status_code == 200
    assert save_resp.json()["composition"]["saved"] is True

    # 5. Quote enquiry guardrails:
    target_merchant_id = swapped_part["merchant_id"]
    merchant_part_ids = [
        sp["part_id"]
        for sp in remixed_comp["selected_parts"]
        if sp["merchant_id"] == target_merchant_id
    ]

    # 5a. Unauthorized enquiry -> 403
    unauth_resp = client.post(
        "/api/v1/enquiries",
        json={
            "composition_id": remixed_id,
            "merchant_id": target_merchant_id,
            "customer_authorized": False,
            "part_ids": merchant_part_ids,
        },
    )
    assert unauth_resp.status_code == 403
    assert unauth_resp.json()["detail"]["code"] == "CUSTOMER_AUTHORIZATION_REQUIRED"

    # 5b. Client-supplied validation_receipt -> 422 (extra='forbid')
    forged_resp = client.post(
        "/api/v1/enquiries",
        json={
            "composition_id": remixed_id,
            "merchant_id": target_merchant_id,
            "customer_authorized": True,
            "part_ids": merchant_part_ids,
            "validation_receipt": {"forged": True},
        },
    )
    assert forged_resp.status_code == 422

    # 5c. Authorized enquiry -> 200 with server-issued ValidationReceipt + SHA-256 digest
    enq_resp = client.post(
        "/api/v1/enquiries",
        json={
            "composition_id": remixed_id,
            "merchant_id": target_merchant_id,
            "customer_authorized": True,
            "part_ids": merchant_part_ids,
            "notes": "Please confirm hem adjustment turnaround before 12 December.",
        },
    )
    assert enq_resp.status_code == 200
    enquiry = enq_resp.json()["enquiry"]
    assert enquiry["status"] == "SENT_TO_DEMO_INBOX"
    assert enquiry["is_demo"] is True
    assert enquiry["customer_authorized"] is True
    assert len(enquiry["validation_receipt"]["receipt_digest"]) == 64
    assert all(
        ir["verification_result"]["overall"] == "PASS"
        for ir in enquiry["validation_receipt"]["items"]
    )

    # 6. Fictional merchant inbox shows the delivered demo enquiry
    inbox_resp = client.get(f"/api/v1/merchants/{target_merchant_id}/inbox")
    assert inbox_resp.status_code == 200
    inbox = inbox_resp.json()
    assert inbox["is_demo_inbox"] is True
    assert inbox["enquiry_count"] == 1
    assert inbox["enquiries"][0]["enquiry_id"] == enquiry["enquiry_id"]


def test_merchant_gaps_endpoint_reports_frozen_evaluation_and_excludes_missing_sizes() -> None:
    client = make_client()
    resp = client.get("/api/v1/merchants/gaps")
    assert resp.status_code == 200
    data = resp.json()

    assert data["briefs_hash_verified"] is True
    assert data["evaluation_brief_count"] == 20
    top_gap = data["evaluation_gaps_aggregated"][0]
    assert top_gap["brief_count"] == 5
    assert top_gap["requested_item_label"] == "green linen jacket"
    assert "5 of 20 briefs" in top_gap["summary"]

    comp = data["evaluation_comparison"]
    assert (
        comp["goa_tag_overlap"]["valid_partial_or_complete_rate"]
        > comp["keyword_baseline"]["valid_partial_or_complete_rate"]
    )
    assert comp["goa_tag_overlap"]["catalogue_grounding_rate"] == 1.0
