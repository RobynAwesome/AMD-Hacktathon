import json
from pathlib import Path

import numpy as np

from goa.schemas import SIZES_BY_SLOT, CatalogueItem, Merchant

ROOT = Path(__file__).resolve().parent.parent
CAT = json.loads((ROOT / "catalogue" / "catalogue.json").read_text())
MARKETS = {m["code"]: m for m in json.loads((ROOT / "goa" / "markets.json").read_text())["markets"]}
FX = {m["currency"]: m["fx_to_usd"] for m in MARKETS.values()}
ITEMS = [CatalogueItem.model_validate(i) for i in CAT["items"]]
MERCHANTS = {m["id"]: Merchant.model_validate(m) for m in CAT["merchants"]}


def test_size_and_unique_ids():
    assert 90 <= len(ITEMS) <= 120
    assert len({i.id for i in ITEMS}) == len(ITEMS)


def test_images_exist():
    for i in ITEMS:
        assert (ROOT / "catalogue" / i.image).exists(), i.image


def test_stock_keys_fit_slot_and_merchants_resolve():
    for i in ITEMS:
        assert set(i.stock) <= set(SIZES_BY_SLOT[i.slot])
        assert i.merchant_id in MERCHANTS
        assert i.currency == MERCHANTS[i.merchant_id].currency


def test_every_merchant_ships_to_every_market():
    for m in MERCHANTS.values():
        assert set(m.ships_to) == set(MARKETS), m.id
        assert m.ships_to[m.market].days <= 4
        assert m.region == MARKETS[m.market]["region"]


def test_every_market_has_an_affordable_look():
    # A garment and shoes that arrive within 10 days, together with shipping under USD 250.
    for code in MARKETS:
        def cheapest(slot):
            costs = []
            for i in ITEMS:
                ship = MERCHANTS[i.merchant_id].ships_to[code]
                if i.slot.value == slot and ship.days <= 10:
                    costs.append((i.price + ship.cost) * FX[i.currency])
            return min(costs)

        assert cheapest("garment") + cheapest("shoes") < 250, code


def test_african_designers_present():
    names = {m.name for m in MERCHANTS.values()}
    assert {"Imbali House", "Adire Atelier"} <= names


def test_deliberate_gaps_exist():
    green = lambda i: any("green" in c for c in i.colours)  # noqa: E731
    assert not any(i.slot.value == "outer_layer" and green(i) for i in ITEMS)
    assert not any(i.slot.value == "shoes" and green(i) for i in ITEMS)


def test_embeddings_match_catalogue():
    vecs = np.load(ROOT / "catalogue" / "embeddings.npy")
    meta = json.loads((ROOT / "catalogue" / "embedding_ids.json").read_text())
    assert vecs.shape[0] == len(ITEMS) and meta["ids"] == [i.id for i in ITEMS]
    assert np.allclose(np.linalg.norm(vecs, axis=1), 1, atol=1e-3)
