"""Compose with hand-written briefs (no model call)."""

from datetime import date

import pytest

from goa import compose as C
from goa.catalogue import load
from goa.schemas import Brief

CAT = load()
TODAY = date(2026, 10, 18)


def thandi(**over):
    d = {
        "occasion": "graduation", "event_date": "2026-12-12", "location": "Cape Town", "market": "ZA",
        "budget": {"amount": 2500, "currency": "ZAR"}, "size": "M", "shoe_size": "38", "colours": ["green"],
        "formality": "smart_casual", "style_notes": ["elegant", "rewearable"],
        "parts": [
            {"slot": "garment", "description": "green elegant dress, rewearable", "colours": ["green"]},
            {"slot": "shoes", "description": "comfortable heels for grass"},
            {"slot": "outer_layer", "description": "light green linen jacket", "colours": ["green"], "materials": ["linen"]},
            {"slot": "accessory", "description": "statement jewellery"},
        ],
    }
    d.update(over)
    return Brief.model_validate(d)


@pytest.fixture(autouse=True)
def gaps_to_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "GAPS_LOG", tmp_path / "gaps.jsonl")


@pytest.mark.parametrize("market", ["ZA", "NG", "US", "GB", "EU", "CN"])
@pytest.mark.parametrize("scope", C.SCOPES)
def test_every_look_passes_grounding(market, scope):
    look = C.compose(CAT, thandi(), market=market, scope=scope, today=TODAY)
    assert C.validate_look(CAT, look, thandi(), TODAY) == []


def test_green_jacket_is_a_logged_gap():
    look = C.compose(CAT, thandi(), scope="global", today=TODAY)
    outer = look.parts[2]
    assert outer.status == "not_on_offer" and outer.reason == "no_match"
    assert "green" in C.GAPS_LOG.read_text()


def test_within_budget_and_shipping_counted():
    look = C.compose(CAT, thandi(), scope="local", today=TODAY)
    assert look.budget_status == "within"
    chosen = C.chosen_offers(look)
    per_merchant = {o.merchant_id: o.shipping_local for o in chosen}
    assert abs(sum(o.price_local for o in chosen) + sum(per_merchant.values()) - look.total_local) < 0.05
    assert all(o.shipping_local > 0 for p in look.parts for o in p.options)


def test_local_scope_only_uses_local_merchants():
    look = C.compose(CAT, thandi(), scope="local", today=TODAY)
    assert {o.hub_market for p in look.parts for o in p.options} == {"ZA"}


def test_abroad_cards_are_outside_scope_and_never_over_budget():
    for market in ["ZA", "US", "GB"]:
        look = C.compose(CAT, thandi(), market=market, scope="local", today=TODAY)
        for card in look.abroad:
            assert card.offer.hub_market != market
            assert card.budget_status in ("within", "near", "no_budget")


def test_too_slow_items_are_dropped():
    soon = thandi(event_date="2026-10-22")  # 4 days away: only local, fast merchants arrive in time
    look = C.compose(CAT, soon, scope="global", today=TODAY)
    for p in look.parts:
        for o in p.options:
            assert o.days <= 3


def test_swap_recomputes_total():
    look = C.compose(CAT, thandi(), scope="global", today=TODAY)
    idx = next(i for i, p in enumerate(look.parts) if len(p.options) > 1)
    C.swap(look, idx, 1)
    assert look.parts[idx].options[1] in C.chosen_offers(look)
    assert abs(look.total_local - C.offers_total(C.chosen_offers(look))) < 0.05
