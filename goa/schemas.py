"""Data shapes for GOA: markets, merchants, catalogue items and the brief."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class Slot(str, Enum):
    garment = "garment"
    shoes = "shoes"
    outer_layer = "outer_layer"
    accessory = "accessory"


class Formality(str, Enum):
    casual = "casual"
    smart_casual = "smart_casual"
    cocktail = "cocktail"
    formal = "formal"
    black_tie = "black_tie"


CLOTHING_SIZES = ["XS", "S", "M", "L", "XL"]
SHOE_SIZES = [str(n) for n in range(35, 47)]  # EU sizes
ONE_SIZE = "ONE"

SIZES_BY_SLOT = {
    Slot.garment: CLOTHING_SIZES,
    Slot.outer_layer: CLOTHING_SIZES,
    Slot.shoes: SHOE_SIZES,
    Slot.accessory: [ONE_SIZE],
}


class Market(BaseModel):
    code: str  # ZA, US, GB
    name: str
    currency: str
    fx_to_usd: float  # 1 unit of this currency in USD, fixed for the demo
    size_system: str  # UK, US, EU (what users in this market usually say)
    hemisphere: str  # north or south
    default_city: str


class Merchant(BaseModel):
    id: str
    name: str
    city: str
    country: str
    currency: str
    email: str
    ships_to: dict[str, int]  # market code to delivery days

    @field_validator("email")
    @classmethod
    def example_domain_only(cls, v: str) -> str:
        if not v.endswith("@example.com"):
            raise ValueError("merchant emails must use example.com")
        return v


class CatalogueItem(BaseModel):
    id: str
    merchant_id: str
    name: str
    slot: Slot
    category: str
    description: str
    colours: list[str]
    materials: list[str]
    formality: Formality
    occasions: list[str]
    price: float = Field(gt=0)
    currency: str
    stock: dict[str, int]
    image: str
    image_credit: str
    vision_tags: dict | None = None

    @model_validator(mode="after")
    def stock_keys_fit_slot(self) -> "CatalogueItem":
        allowed = SIZES_BY_SLOT[self.slot]
        bad = [k for k in self.stock if k not in allowed]
        if bad:
            raise ValueError(f"{self.id}: stock sizes {bad} not valid for {self.slot.value}")
        if any(v < 0 for v in self.stock.values()):
            raise ValueError(f"{self.id}: negative stock")
        return self


class Budget(BaseModel):
    amount: float = Field(gt=0)
    currency: str
    soft: bool = False  # true for "around R2000"


class Part(BaseModel):
    slot: Slot
    description: str  # what the person wants for this part, in their words
    colours: list[str] = []
    materials: list[str] = []


class Brief(BaseModel):
    occasion: str
    event_date: date | None = None
    location: str | None = None
    market: str
    setting: str | None = None  # indoor, outdoor
    weather: str | None = None
    budget: Budget | None = None  # total for the whole look
    size: str | None = None  # clothing size as the person said it, never invented
    shoe_size: str | None = None
    colours: list[str] = []
    formality: Formality | None = None
    style_notes: list[str] = []
    constraints: list[str] = []
    parts: list[Part] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def at_most_one_garment(self) -> "Brief":
        garments = sum(1 for p in self.parts if p.slot == Slot.garment)
        if garments > 1:
            raise ValueError("parts must contain at most one garment")
        return self

    def check_date(self, today: date) -> None:
        if self.event_date is not None and self.event_date < today:
            raise ValueError(f"event_date {self.event_date} is in the past (today is {today})")
