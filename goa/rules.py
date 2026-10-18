"""Deterministic rules. Code, not the model, decides stock, size, delivery, price and budget."""

from __future__ import annotations

import re
from datetime import date, timedelta

from goa.catalogue import Catalogue
from goa.schemas import CLOTHING_SIZES, ONE_SIZE, CatalogueItem, Slot

NEAR_BUDGET = 0.10  # up to 10% over counts as "near budget"

# Clothing sizes as people say them, per size system, mapped to the catalogue's XS to XL.
DRESS_SIZES = {
    "UK": {"4": "XS", "6": "XS", "8": "S", "10": "M", "12": "L", "14": "XL", "16": "XL"},
    "US": {"0": "XS", "2": "XS", "4": "S", "6": "M", "8": "L", "10": "XL", "12": "XL"},
    "EU": {"32": "XS", "34": "XS", "36": "S", "38": "M", "40": "L", "42": "XL", "44": "XL"},
}
SHOE_OFFSET_TO_EU = {"UK": 33, "US": 31, "EU": 0}  # rough women's conversion, stated in the README
WORD_SIZES = {"EXTRA SMALL": "XS", "SMALL": "S", "MEDIUM": "M", "LARGE": "L", "EXTRA LARGE": "XL", "XXS": "XS"}


def clothing_size(raw: str | None, size_system: str) -> str | None:
    """'M', 'medium', 'UK 10', '10' -> 'M'. None if unknown or not given."""
    if not raw:
        return None
    s = raw.strip().upper()
    if s in CLOTHING_SIZES:
        return s
    if s in WORD_SIZES:
        return WORD_SIZES[s]
    m = re.match(r"^(UK|US|EU)?\s*(\d{1,2})$", s)
    if m:
        system = m.group(1) or size_system
        return DRESS_SIZES.get(system, {}).get(m.group(2))
    return None


def shoe_size(raw: str | None, size_system: str) -> str | None:
    """'EU 38', '38', 'UK 5', '5' -> '38'."""
    if not raw:
        return None
    m = re.match(r"^(UK|US|EU)?\s*(\d{1,2}(?:\.5)?)$", raw.strip().upper())
    if not m:
        return None
    system = m.group(1) or ("EU" if float(m.group(2)) >= 30 else size_system)
    eu = round(float(m.group(2)) + SHOE_OFFSET_TO_EU[system])
    return str(eu)


def size_for(item: CatalogueItem, clothing: str | None, shoes: str | None) -> str | None:
    if item.slot == Slot.accessory:
        return ONE_SIZE
    if item.slot == Slot.shoes:
        return shoes
    return clothing


def in_stock(item: CatalogueItem, size: str | None) -> bool:
    """Size unknown: in stock in at least one size (the page asks for a size before sending an enquiry)."""
    if size is None:
        return any(v > 0 for v in item.stock.values())
    return item.stock.get(size, 0) > 0


def delivery(cat: Catalogue, item: CatalogueItem, market: str) -> tuple[int, float]:
    """Delivery days and shipping cost (merchant currency) to the shopper's market."""
    s = cat.merchant(item).ships_to[market]
    return s.days, s.cost


def arrival(days: int, today: date) -> date:
    return today + timedelta(days=days)


def arrives_in_time(days: int, event_date: date | None, today: date) -> bool:
    """Arrives at least one day before the event. No event date: any delivery time is fine."""
    if event_date is None:
        return True
    return arrival(days, today) <= event_date - timedelta(days=1)


def to_local(cat: Catalogue, amount: float, currency: str, market: str) -> float:
    target = cat.markets[market]
    return amount * cat.fx[currency] / target.fx_to_usd


def landed_local(cat: Catalogue, item: CatalogueItem, market: str) -> tuple[float, float]:
    """Item price and shipping, both in the shopper's currency."""
    _, ship = delivery(cat, item, market)
    return to_local(cat, item.price, item.currency, market), to_local(cat, ship, item.currency, market)


def budget_status(total: float, budget: float | None) -> str:
    if budget is None:
        return "no_budget"
    if total <= budget:
        return "within"
    if total <= budget * (1 + NEAR_BUDGET):
        return "near"
    return "over"


def check_item(cat: Catalogue, item: CatalogueItem, market: str, size: str | None,
               event_date: date | None, today: date) -> str | None:
    """None if the item passes every item-level rule, else the reason it fails."""
    if not in_stock(item, size):
        return "out_of_stock_in_size"
    days, _ = delivery(cat, item, market)
    if not arrives_in_time(days, event_date, today):
        return "too_slow"
    return None


def season(hemisphere: str, when: date) -> str:
    north = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
             6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"}[when.month]
    if hemisphere == "north":
        return north
    return {"winter": "summer", "summer": "winter", "spring": "autumn", "autumn": "spring"}[north]
