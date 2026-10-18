"""Baseline: plain keyword search over the same catalogue, the way a static store works.

For each part the shopper types its words into a search box. Results are ranked by how many query
words appear in the product text. The store does not know the shopper's date or budget, so nothing is
filtered by delivery, size or price: the shopper has to open items and check those by hand.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from goa.catalogue import Catalogue
from goa.compose import in_scope
from goa.schemas import CatalogueItem, Part

STOP = {"a", "an", "and", "or", "the", "for", "with", "that", "to", "of", "in", "on", "i", "my", "something", "some"}


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if w not in STOP and len(w) > 2}


def item_text(item: CatalogueItem) -> str:
    return " ".join([item.name, item.category, item.description, " ".join(item.colours), " ".join(item.materials)])


@dataclass
class Hit:
    item: CatalogueItem
    score: int


def search(cat: Catalogue, part: Part, market: str, scope: str) -> list[Hit]:
    q = words(part.description + " " + " ".join(part.colours) + " " + " ".join(part.materials))
    hits = []
    for item in cat.items:
        if item.slot != part.slot or not in_scope(cat, item, market, scope):
            continue
        score = len(q & words(item_text(item)))
        if score:
            hits.append(Hit(item, score))
    hits.sort(key=lambda h: (-h.score, h.item.price))
    return hits
