"""Match each part of a brief to catalogue items by meaning (embeddings), plus a few honest boosts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from goa.catalogue import CATALOGUE_DIR, Catalogue
from goa.embedding import hashed_bow
from goa.schemas import Brief, CatalogueItem, Part

COLOUR_FAMILIES = {
    "green": ["green", "sage", "emerald", "olive", "forest", "bottle", "mint", "jade"],
    "blue": ["blue", "indigo", "navy", "teal"],
    "neutral": ["ivory", "cream", "stone", "beige", "natural", "white", "champagne", "nude", "camel", "tan"],
    "dark": ["black", "charcoal", "grey", "gray"],
    "red": ["red", "burgundy", "oxblood", "coral", "pink", "lilac", "purple"],
    "warm": ["yellow", "gold", "ochre", "orange", "terracotta", "burnt", "cognac", "brown", "rust"],
    "metallic": ["gold", "silver", "champagne"],
}


def families(colours: list[str]) -> set[str]:
    out = set()
    for c in colours:
        words = c.lower().replace("-", " ").split()
        for fam, keys in COLOUR_FAMILIES.items():
            if any(w in keys for w in words):
                out.add(fam)
    return out


@dataclass
class Candidate:
    item: CatalogueItem
    score: float
    colour_ok: bool


@lru_cache(maxsize=1)
def _index():
    vecs = np.load(CATALOGUE_DIR / "embeddings.npy")
    meta = json.loads((CATALOGUE_DIR / "embedding_ids.json").read_text())
    return vecs, meta


@lru_cache(maxsize=1)
def _fastembed_model(name: str):
    from fastembed import TextEmbedding

    return TextEmbedding(name)


def embed_query(text: str) -> np.ndarray:
    """Embed with the same backend that built the catalogue vectors."""
    _, meta = _index()
    if meta["backend"].startswith("fastembed"):
        v = np.array(list(_fastembed_model(meta["model"]).embed([text]))[0], dtype=np.float32)
    else:
        v = hashed_bow([text], dim=meta["dim"])[0]
    return v / (np.linalg.norm(v) + 1e-9)


def part_text(part: Part, brief: Brief) -> str:
    bits = [part.description, part.slot.value.replace("_", " ")]
    if part.colours:
        bits.append("colours: " + ", ".join(part.colours))
    if part.materials:
        bits.append("materials: " + ", ".join(part.materials))
    bits.append("occasion: " + brief.occasion)
    if brief.formality:
        bits.append("formality: " + brief.formality.value.replace("_", " "))
    bits += brief.style_notes
    if brief.weather:
        bits.append(brief.weather)
    return ". ".join(bits)


def match_part(cat: Catalogue, part: Part, brief: Brief, k: int = 12) -> list[Candidate]:
    """Every item in the part's slot, best first. colour_ok is False when the part asks for colours
    and the item shares none of their families (that is a different product, not a match)."""
    vecs, meta = _index()
    q = embed_query(part_text(part, brief))
    row = {iid: n for n, iid in enumerate(meta["ids"])}
    want = families(part.colours)
    occasion = brief.occasion.lower()
    out = []
    for item in cat.items:
        if item.slot != part.slot:
            continue
        score = float(vecs[row[item.id]] @ q)
        have = families(item.colours)
        colour_ok = not want or bool(want & have)
        if want and colour_ok:
            score += 0.15
        if brief.formality and item.formality == brief.formality:
            score += 0.1
        if any(occasion in o or o in occasion for o in item.occasions):
            score += 0.1
        mats = {m.lower() for m in item.materials}
        if any(m.lower() in mats for m in part.materials):
            score += 0.1
        out.append(Candidate(item, round(score, 4), colour_ok))
    out.sort(key=lambda c: (c.colour_ok, c.score), reverse=True)
    return out[:k]
