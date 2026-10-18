from datetime import date

from goa import rules
from goa.catalogue import load

CAT = load()


def item(iid):
    return CAT.by_id[iid]


def test_clothing_sizes():
    assert rules.clothing_size("M", "UK") == "M"
    assert rules.clothing_size("medium", "UK") == "M"
    assert rules.clothing_size("UK 10", "US") == "M"
    assert rules.clothing_size("10", "UK") == "M"
    assert rules.clothing_size("10", "US") == "XL"
    assert rules.clothing_size(None, "UK") is None
    assert rules.clothing_size("huge", "UK") is None


def test_shoe_sizes():
    assert rules.shoe_size("38", "UK") == "38"
    assert rules.shoe_size("UK 5", "EU") == "38"
    assert rules.shoe_size("7", "US") == "38"
    assert rules.shoe_size("5", "UK") == "38"


def test_in_stock_by_size():
    it = item("fyn-001")
    sold_out = [s for s, n in it.stock.items() if n == 0]
    in_stock = [s for s, n in it.stock.items() if n > 0]
    assert rules.in_stock(it, in_stock[0])
    if sold_out:
        assert not rules.in_stock(it, sold_out[0])
    assert rules.in_stock(it, None)


def test_arrives_a_day_before():
    today = date(2026, 12, 1)
    assert rules.arrives_in_time(10, date(2026, 12, 12), today)
    assert not rules.arrives_in_time(11, date(2026, 12, 12), today)
    assert rules.arrives_in_time(99, None, today)


def test_delivery_differs_by_market():
    it = item("imb-001")
    assert rules.delivery(CAT, it, "ZA")[0] < rules.delivery(CAT, it, "US")[0]


def test_currency_and_landed_price():
    assert round(rules.to_local(CAT, 100, "USD", "ZA")) == round(100 / 0.055)
    price, ship = rules.landed_local(CAT, item("lot-001"), "ZA")
    assert price > 0 and ship > 0


def test_budget_status_edges():
    assert rules.budget_status(100, 100) == "within"
    assert rules.budget_status(110, 100) == "near"
    assert rules.budget_status(110.01, 100) == "over"
    assert rules.budget_status(5, None) == "no_budget"
