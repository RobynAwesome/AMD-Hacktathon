"""Turn a Brief into a verified look: matched, rule-checked, within budget, with gaps logged.

The model never sets a price, date or stock level here. Everything shown passes validate_look().
"""

from __future__ import annotations

import itertools
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import date

from goa import rules
from goa.catalogue import CACHE_ROOT, ROOT, Catalogue
from goa.match import Candidate, families, match_part
from goa.schemas import Brief, CatalogueItem, Part

SCOPES = ["local", "region", "global"]
OPTIONS_PER_PART = 3  # shown per part: the chosen item plus swaps
POOL_PER_PART = 6  # searched per part when fitting the budget
MAX_ABROAD = 2
GAPS_LOG = CACHE_ROOT / "gaps.jsonl"


@dataclass
class Offer:
    """One verified item for one part, priced for the shopper's market."""

    item_id: str
    name: str
    slot: str
    merchant_id: str
    merchant: str
    city: str
    hub_market: str
    image: str
    price_local: float
    shipping_local: float
    landed_local: float
    price_original: float
    currency_original: str
    days: int
    arrives: str
    score: float
    size: str | None
    why: str = ""


@dataclass
class PartResult:
    part: dict
    status: str  # available or not_on_offer
    options: list[Offer] = field(default_factory=list)
    reason: str | None = None  # for not_on_offer: no_match, out_of_stock_in_size, too_slow


@dataclass
class AbroadCard:
    part_index: int
    offer: Offer
    reason: str
    budget_status: str
    over_by: float


@dataclass
class Prefs:
    """Shopper choices made while the brief is read. Applied by code; no model call."""

    no_heels: bool = False
    local_first: bool = False
    rewearable: bool = False
    liked: list[str] = field(default_factory=list)  # item ids tapped as "more like this"


HEEL_WORDS = ("heel", "pump", "stiletto", "slingback")


def _has_heels(item: CatalogueItem) -> bool:
    text = f"{item.name} {item.category} {item.description}".lower()
    return any(w in text for w in HEEL_WORDS) and "flat" not in text


@dataclass
class Look:
    market: str
    currency: str
    scope: str
    parts: list[PartResult]
    chosen: list[int | None]  # index into each part's options, None for not_on_offer
    total_local: float
    budget_local: float | None
    budget_status: str
    abroad: list[AbroadCard]
    size: str | None
    shoe_size: str | None
    notes: list[str]
    receipt: dict = field(default_factory=dict)  # the work done, for the shopper to see

    def to_dict(self) -> dict:
        return asdict(self)


def in_scope(cat: Catalogue, item: CatalogueItem, market: str, scope: str) -> bool:
    m = cat.merchant(item)
    if scope == "local":
        return m.market == market
    if scope == "region":
        return m.region == cat.markets[market].region
    return True


def _offer(cat: Catalogue, c: Candidate, market: str, size: str | None, today: date) -> Offer:
    item, m = c.item, cat.merchant(c.item)
    days, _ = rules.delivery(cat, item, market)
    price, ship = rules.landed_local(cat, item, market)
    return Offer(
        item_id=item.id, name=item.name, slot=item.slot.value, merchant_id=m.id, merchant=m.name, city=m.city,
        hub_market=m.market, image=item.image, price_local=round(price, 2), shipping_local=round(ship, 2),
        landed_local=round(price + ship, 2), price_original=item.price, currency_original=item.currency,
        days=days, arrives=rules.arrival(days, today).isoformat(), score=c.score, size=size,
    )


def offers_total(offers: list[Offer]) -> float:
    """Item prices plus shipping charged once per merchant (one parcel per merchant)."""
    ship: dict[str, float] = {}
    for o in offers:
        ship[o.merchant_id] = max(ship.get(o.merchant_id, 0.0), o.shipping_local)
    return round(sum(o.price_local for o in offers) + sum(ship.values()), 2)


def chosen_offers(look: "Look") -> list[Offer]:
    return [p.options[i] for p, i in zip(look.parts, look.chosen) if i is not None]


def _budget_local(cat: Catalogue, brief: Brief, market: str) -> float | None:
    if brief.budget is None:
        return None
    return rules.to_local(cat, brief.budget.amount, brief.budget.currency, market)


def _best_combo(parts: list[PartResult], budget: float | None) -> tuple[list[int | None], float]:
    """Highest total match score whose landed total fits the budget; cheapest combination if none fits."""
    choices = [range(len(p.options)) if p.options else [None] for p in parts]
    best, best_key = None, None
    for combo in itertools.product(*choices):
        total = offers_total([p.options[i] for p, i in zip(parts, combo) if i is not None])
        score = sum(p.options[i].score for p, i in zip(parts, combo) if i is not None)
        fits = budget is None or total <= budget
        key = (fits, score if fits else -total)
        if best_key is None or key > best_key:
            best, best_key = list(combo), key
    return best, offers_total([p.options[i] for p, i in zip(parts, best) if i is not None])


def _fails_reason(failures: list[str], had_colour_match: bool) -> str:
    if not had_colour_match or not failures:
        return "no_match"
    return max(set(failures), key=failures.count)


def _liked_boost(cat: Catalogue, liked: list[str]):
    """Similarity to items the shopper tapped as "more like this", from the stored embeddings."""
    if not liked:
        return lambda item: 0.0
    from goa.match import _index

    vecs, meta = _index()
    row = {iid: n for n, iid in enumerate(meta["ids"])}
    picks = [vecs[row[i]] for i in liked if i in row]
    if not picks:
        return lambda item: 0.0
    return lambda item: max(float(vecs[row[item.id]] @ v) for v in picks)


def compose(cat: Catalogue, brief: Brief, market: str | None = None, scope: str = "global",
            size: str | None = None, shoe_size: str | None = None, today: date | None = None,
            log_gaps: bool = True, prefs: Prefs | None = None) -> Look:
    market = market or brief.market
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {SCOPES}")
    today = today or date.today()
    mk = cat.markets[market]
    clothing = rules.clothing_size(size or brief.size, mk.size_system)
    shoes = rules.shoe_size(shoe_size or brief.shoe_size, mk.size_system)
    notes = []
    if clothing is None:
        notes.append("Add your clothing size to check stock in your size.")
    if shoes is None and any(p.slot.value == "shoes" for p in brief.parts):
        notes.append("Add your shoe size to check shoe stock.")

    prefs = prefs or Prefs()
    boost = _liked_boost(cat, prefs.liked)
    receipt = {"searched": sum(1 for i in cat.items if in_scope(cat, i, market, scope)
                               and i.slot.value in {p.slot.value for p in brief.parts}),
               "hubs": {}, "checked": 0, "ruled_out": {}, "colour_mismatch": 0}

    parts: list[PartResult] = []
    outside: list[list[Offer]] = []
    for part in brief.parts:
        cands = match_part(cat, part, brief, k=40)
        for c in cands:
            if prefs.local_first and cat.merchant(c.item).market == market:
                c.score = round(c.score + 0.1, 4)
            if prefs.rewearable and c.item.formality.value in ("smart_casual", "casual"):
                c.score = round(c.score + 0.05, 4)
            if prefs.liked:
                c.score = round(c.score + 0.15 * boost(c.item), 4)
        cands.sort(key=lambda c: (c.colour_ok, c.score), reverse=True)
        valid, failures, had_colour = [], [], False
        abroad_valid = []
        for c in cands:
            in_reach = in_scope(cat, c.item, market, scope)
            if not c.colour_ok:
                receipt["colour_mismatch"] += in_reach
                continue
            if prefs.no_heels and part.slot.value == "shoes" and _has_heels(c.item):
                if in_reach:
                    receipt["ruled_out"]["has_heels"] = receipt["ruled_out"].get("has_heels", 0) + 1
                continue
            sz = rules.size_for(c.item, clothing, shoes)
            if in_reach:
                had_colour = True
                receipt["checked"] += 1
                city = cat.merchant(c.item).city
                receipt["hubs"][city] = receipt["hubs"].get(city, 0) + 1
                why_not = rules.check_item(cat, c.item, market, sz, brief.event_date, today)
                if why_not:
                    failures.append(why_not)
                    receipt["ruled_out"][why_not] = receipt["ruled_out"].get(why_not, 0) + 1
                else:
                    valid.append(_offer(cat, c, market, sz, today))
            elif rules.check_item(cat, c.item, market, sz, brief.event_date, today) is None:
                abroad_valid.append(_offer(cat, c, market, sz, today))
        outside.append(abroad_valid[:OPTIONS_PER_PART])
        if valid:
            # Best matches plus the cheapest valid items, so the budget search always has affordable choices.
            best = valid[: POOL_PER_PART - 2]
            cheap = sorted((o for o in valid if o not in best), key=lambda o: o.landed_local)[:2]
            parts.append(PartResult(part.model_dump(mode="json"), "available", best + cheap))
        else:
            parts.append(PartResult(part.model_dump(mode="json"), "not_on_offer",
                                    reason=_fails_reason(failures, had_colour)))

    budget = _budget_local(cat, brief, market)
    chosen, total = _best_combo(parts, budget)
    # Show the chosen item first, then the best-scoring alternatives as swaps.
    for p, i in zip(parts, chosen):
        if i is not None:
            pick = p.options[i]
            p.options = [pick] + [o for o in p.options if o is not pick][: OPTIONS_PER_PART - 1]
    chosen = [0 if i is not None else None for i in chosen]
    look = Look(market=market, currency=mk.currency, scope=scope, parts=parts, chosen=chosen,
                total_local=total, budget_local=round(budget, 2) if budget else None,
                budget_status=rules.budget_status(total, budget), abroad=[], size=clothing,
                shoe_size=shoes, notes=notes, receipt=receipt)
    if scope != "global":
        look.abroad = worth_it_abroad(look, outside, budget)

    problems = validate_look(cat, look, brief, today)
    if problems:
        raise AssertionError("grounding check failed: " + "; ".join(problems))
    if log_gaps:
        log_gap_entries(look, brief)
    return look


def worth_it_abroad(look: Look, outside: list[list[Offer]], budget: float | None) -> list[AbroadCard]:
    """Items from hubs outside the chosen scope that arrive in time and are cheaper, a better match,
    or fill a part nothing in scope can. Within budget or near it (up to 10% over), never over."""
    cards = []
    for idx, (part, offers) in enumerate(zip(look.parts, outside)):
        current = part.options[look.chosen[idx]] if look.chosen[idx] is not None else None
        for o in offers:
            rest = [x.options[look.chosen[j]] for j, x in enumerate(look.parts) if j != idx and look.chosen[j] is not None]
            new_total = offers_total(rest + [o])
            status = rules.budget_status(new_total, budget)
            if status == "over":
                continue
            if current is None:
                reason = f"Nothing in scope fills this part. {o.merchant} ({o.city}) arrives {o.arrives}."
                benefit = 2.0
            elif o.landed_local <= current.landed_local * 0.9:
                saving = current.landed_local - o.landed_local
                reason = f"{saving:,.0f} {look.currency} cheaper than the best in scope, shipping included."
                benefit = saving / max(current.landed_local, 1)
            elif o.score >= current.score + 0.1:
                reason = f"A closer match to your brief from {o.city}, arriving {o.arrives}."
                benefit = o.score - current.score
            else:
                continue
            over_by = round(max(0.0, new_total - budget), 2) if budget else 0.0
            cards.append((benefit, AbroadCard(idx, o, reason, status, over_by)))
            break
    cards.sort(key=lambda t: t[0], reverse=True)
    return [c for _, c in cards[:MAX_ABROAD]]


def validate_look(cat: Catalogue, look: Look, brief: Brief, today: date) -> list[str]:
    """Grounding check: every shown item exists and passes every rule, and the numbers add up."""
    problems = []
    shown = [(p, o) for p in look.parts for o in p.options] + [(look.parts[c.part_index], c.offer) for c in look.abroad]
    for part, o in shown:
        item = cat.by_id.get(o.item_id)
        if item is None:
            problems.append(f"{o.item_id} not in catalogue")
            continue
        if item.slot.value != part.part["slot"]:
            problems.append(f"{o.item_id} is in the wrong slot")
        if rules.check_item(cat, item, look.market, o.size, brief.event_date, today):
            problems.append(f"{o.item_id} fails a rule")
        price, ship = rules.landed_local(cat, item, look.market)
        if abs(price + ship - o.landed_local) > 0.01:
            problems.append(f"{o.item_id} price mismatch")
    if abs(offers_total(chosen_offers(look)) - look.total_local) > 0.05:
        problems.append("total mismatch")
    return problems


def log_gap_entries(look: Look, brief: Brief) -> None:
    gaps = [p for p in look.parts if p.status == "not_on_offer"]
    if not gaps:
        return
    try:
        GAPS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with GAPS_LOG.open("a", encoding="utf-8") as f:
            for p in gaps:
                f.write(json.dumps({
                    "ts": int(time.time()), "market": look.market, "scope": look.scope, "occasion": brief.occasion,
                    "slot": p.part["slot"], "description": p.part["description"], "colours": p.part["colours"],
                    "colour_families": sorted(families(p.part["colours"])), "materials": p.part["materials"],
                    "reason": p.reason,
                }) + "\n")
    except OSError:
        pass


def swap(look: Look, part_index: int, option_index: int) -> Look:
    """Swap one part to another verified option and recompute the total."""
    if look.parts[part_index].status != "available":
        raise ValueError("that part has no options")
    if not 0 <= option_index < len(look.parts[part_index].options):
        raise ValueError("no such option")
    look.chosen[part_index] = option_index
    look.total_local = offers_total(chosen_offers(look))
    look.budget_status = rules.budget_status(look.total_local, look.budget_local)
    return look


def part_from_dict(d: dict) -> Part:
    return Part.model_validate(d)
