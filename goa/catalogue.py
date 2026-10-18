"""Load the catalogue, merchants and markets once."""

from __future__ import annotations

import json
import os
import tempfile
from functools import lru_cache
from pathlib import Path

from goa.schemas import CatalogueItem, Market, Merchant

ROOT = Path(__file__).resolve().parent.parent
CATALOGUE_DIR = ROOT / "catalogue"


def _resolve_cache_root() -> Path:
    default = ROOT / "cache"
    if os.environ.get("VERCEL"):
        return Path(tempfile.gettempdir()) / "goa_cache"
    try:
        default.mkdir(parents=True, exist_ok=True)
        return default
    except OSError:
        return Path(tempfile.gettempdir()) / "goa_cache"


CACHE_ROOT = _resolve_cache_root()


@lru_cache(maxsize=1)
def load() -> "Catalogue":
    data = json.loads((CATALOGUE_DIR / "catalogue.json").read_text(encoding="utf-8"))
    markets = json.loads((ROOT / "goa" / "markets.json").read_text(encoding="utf-8"))["markets"]
    tags_path = CATALOGUE_DIR / "vision_tags.json"
    tags = json.loads(tags_path.read_text(encoding="utf-8")) if tags_path.exists() else {}
    items = []
    for raw in data["items"]:
        raw["vision_tags"] = tags.get(raw["id"], raw.get("vision_tags"))
        items.append(CatalogueItem.model_validate(raw))
    return Catalogue(
        items=items,
        merchants={m["id"]: Merchant.model_validate(m) for m in data["merchants"]},
        markets={m["code"]: Market.model_validate(m) for m in markets},
    )


class Catalogue:
    def __init__(self, items: list[CatalogueItem], merchants: dict[str, Merchant], markets: dict[str, Market]):
        self.items = items
        self.by_id = {i.id: i for i in items}
        self.merchants = merchants
        self.markets = markets
        self.fx = {m.currency: m.fx_to_usd for m in markets.values()}

    def merchant(self, item: CatalogueItem) -> Merchant:
        return self.merchants[item.merchant_id]
