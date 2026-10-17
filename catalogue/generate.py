"""Synthetic catalogue generator: 3 fictional merchants, 48 items. Deterministic (fixed seed).

Gaps on purpose, so the gap view has signal: no green linen jacket, no warm green coat,
no green shoes, and nothing in plus sizes above XL.
Run: python catalogue/generate.py
"""

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from goa.schemas import SIZES_BY_SLOT, CatalogueItem, Merchant, Slot  # noqa: E402

SEED = 7
CREDIT = "placeholder, replace with licensed photo"

MERCHANTS = [
    Merchant(id="m_fynbos", name="Fynbos Atelier", city="Cape Town", country="ZA", currency="ZAR",
             email="fynbos.orders@example.com", ships_to={"ZA": 4, "GB": 9, "US": 12}),
    Merchant(id="m_hudson", name="Hudson & Pine", city="New York", country="US", currency="USD",
             email="hudsonpine.hello@example.com", ships_to={"US": 3, "GB": 7, "ZA": 11}),
    Merchant(id="m_thorn", name="Thornbury Lane", city="London", country="GB", currency="GBP",
             email="thornbury.studio@example.com", ships_to={"GB": 2, "US": 6, "ZA": 8}),
]

GRAD = "graduation"
WED = "wedding guest"
JOB = "interview"
DIN = "formal dinner"

# (slot, category, name, description, colours, materials, formality, occasions, price)
ITEMS = {
    "m_fynbos": [
        ("garment", "midi dress", "Sage linen wrap midi", "Linen-blend wrap dress with flutter sleeves, breathable for warm days.", ["sage green"], ["linen", "viscose"], "smart_casual", [GRAD, WED], 1350),
        ("garment", "maxi dress", "Emerald satin slip maxi", "Bias-cut satin slip dress, fluid and elegant.", ["emerald green"], ["satin"], "cocktail", [WED, DIN, GRAD], 1890),
        ("garment", "jumpsuit", "Olive wide-leg jumpsuit", "Belted cotton jumpsuit with wide legs and a V neck.", ["olive"], ["cotton"], "smart_casual", [GRAD, JOB], 1250),
        ("garment", "shirt dress", "Ivory cotton shirt dress", "Crisp poplin shirt dress with a tie waist, easy to rewear.", ["ivory"], ["cotton"], "smart_casual", [GRAD, JOB], 990),
        ("garment", "suit", "Stone linen two-piece suit", "Unstructured linen blazer and trousers, relaxed tailoring.", ["stone"], ["linen"], "smart_casual", [GRAD, WED, JOB], 2450),
        ("garment", "midi dress", "Protea print tea dress", "Floral print tea dress with puff sleeves.", ["pink", "green"], ["viscose"], "casual", [GRAD], 850),
        ("shoes", "block heels", "Tan block-heel sandals", "Leather sandals with a low block heel, steady on grass.", ["tan"], ["leather"], "smart_casual", [GRAD, WED], 750),
        ("shoes", "flats", "Gold pointed flats", "Metallic leather flats, all-day comfort.", ["gold"], ["leather"], "smart_casual", [GRAD, WED, DIN], 620),
        ("shoes", "espadrilles", "Natural wedge espadrilles", "Jute wedge espadrilles with ankle ties.", ["natural", "beige"], ["jute", "canvas"], "casual", [GRAD], 540),
        ("shoes", "loafers", "Brown suede loafers", "Soft suede loafers, unlined.", ["brown"], ["suede"], "smart_casual", [GRAD, JOB], 980),
        ("outer_layer", "kimono", "Cream crochet kimono", "Light open-knit cover-up for evening breeze.", ["cream"], ["cotton"], "casual", [GRAD, WED], 690),
        ("outer_layer", "blazer", "Black cropped blazer", "Cropped single-button blazer.", ["black"], ["polyester", "viscose"], "smart_casual", [JOB, GRAD, DIN], 1150),
        ("outer_layer", "wrap", "Gold silk shawl", "Lightweight silk shawl for warm nights.", ["gold"], ["silk"], "cocktail", [WED, DIN], 580),
        ("accessory", "bag", "Woven straw clutch", "Hand-woven clutch with a leather strap.", ["natural"], ["straw", "leather"], "casual", [GRAD, WED], 420),
        ("accessory", "earrings", "Brass leaf earrings", "Handmade brass drop earrings.", ["gold"], ["brass"], "smart_casual", [GRAD, WED, DIN], 320),
        ("accessory", "hat", "Wide-brim sun hat", "Packable wide-brim hat for outdoor ceremonies.", ["natural"], ["straw"], "casual", [GRAD], 380),
    ],
    "m_hudson": [
        ("garment", "sheath dress", "Navy crepe sheath", "Tailored crepe sheath dress, knee length.", ["navy"], ["crepe"], "formal", [JOB, GRAD, DIN], 148),
        ("garment", "midi dress", "Forest green knit midi", "Ribbed knit midi with long sleeves, warm for winter events.", ["forest green"], ["wool blend"], "smart_casual", [GRAD, WED], 128),
        ("garment", "suit", "Charcoal wool suit", "Slim two-piece suit in Italian wool.", ["charcoal"], ["wool"], "formal", [JOB, GRAD, WED, DIN], 395),
        ("garment", "maxi dress", "Black velvet maxi", "Long-sleeve velvet maxi dress.", ["black"], ["velvet"], "black_tie", [DIN, WED], 210),
        ("garment", "jumpsuit", "Burgundy crepe jumpsuit", "Halter jumpsuit with a fluid leg.", ["burgundy"], ["crepe"], "cocktail", [WED, DIN, GRAD], 165),
        ("garment", "midi dress", "Mint pleated midi", "Pleated chiffon midi with a tie neck.", ["mint green"], ["chiffon"], "cocktail", [WED, GRAD], 138),
        ("shoes", "pumps", "Black leather pumps", "Classic 75mm pumps.", ["black"], ["leather"], "formal", [JOB, DIN, GRAD], 140),
        ("shoes", "ankle boots", "Cognac heeled ankle boots", "Leather ankle boots with a stacked heel.", ["cognac"], ["leather"], "smart_casual", [GRAD, JOB], 175),
        ("shoes", "oxfords", "Dark brown oxfords", "Goodyear-welted leather oxfords.", ["dark brown"], ["leather"], "formal", [JOB, WED, DIN, GRAD], 220),
        ("shoes", "block heels", "Nude block heels", "Suede block heels with an ankle strap.", ["nude"], ["suede"], "smart_casual", [GRAD, WED], 120),
        ("outer_layer", "coat", "Camel wool coat", "Long double-breasted wool coat.", ["camel"], ["wool"], "formal", [GRAD, JOB, DIN, WED], 320),
        ("outer_layer", "trench", "Classic beige trench", "Water-resistant cotton trench.", ["beige"], ["cotton"], "smart_casual", [JOB, GRAD], 245),
        ("outer_layer", "cardigan", "Grey cashmere cardigan", "Fine-gauge cashmere cardigan.", ["grey"], ["cashmere"], "smart_casual", [GRAD, JOB], 185),
        ("accessory", "bag", "Black leather tote", "Structured tote, fits a laptop.", ["black"], ["leather"], "smart_casual", [JOB], 160),
        ("accessory", "scarf", "Plaid wool scarf", "Oversized brushed wool scarf.", ["red", "green"], ["wool"], "casual", [GRAD], 55),
        ("accessory", "tie", "Silk knit tie", "Square-end knit tie.", ["navy"], ["silk"], "formal", [JOB, WED, DIN], 65),
    ],
    "m_thorn": [
        ("garment", "midi dress", "Bottle green tweed shift", "Wool tweed shift dress with a round neck.", ["bottle green"], ["wool"], "smart_casual", [GRAD, JOB], 145),
        ("garment", "maxi dress", "Champagne sequin gown", "Floor-length sequin gown.", ["champagne"], ["polyester"], "black_tie", [DIN, WED], 260),
        ("garment", "suit", "Navy pinstripe suit", "Three-piece pinstripe suit.", ["navy"], ["wool"], "formal", [JOB, WED, GRAD, DIN], 340),
        ("garment", "midi dress", "Lilac tea dress", "Floral georgette tea dress.", ["lilac"], ["georgette"], "smart_casual", [WED, GRAD], 98),
        ("garment", "co-ord set", "Ivory blouse and skirt set", "Silk blouse with a matching midi skirt.", ["ivory"], ["silk"], "cocktail", [GRAD, WED, DIN], 185),
        ("garment", "jumpsuit", "Black tailored jumpsuit", "Sleeveless tailored jumpsuit.", ["black"], ["crepe"], "formal", [DIN, JOB], 135),
        ("shoes", "brogues", "Oxblood brogues", "Polished leather brogues.", ["oxblood"], ["leather"], "smart_casual", [GRAD, JOB], 125),
        ("shoes", "slingbacks", "Silver slingbacks", "Kitten-heel metallic slingbacks.", ["silver"], ["leather"], "cocktail", [WED, DIN, GRAD], 95),
        ("shoes", "chelsea boots", "Black chelsea boots", "Waterproof leather chelsea boots.", ["black"], ["leather"], "smart_casual", [GRAD, JOB], 150),
        ("shoes", "flats", "Navy ballet flats", "Soft leather ballet flats.", ["navy"], ["leather"], "smart_casual", [GRAD, JOB], 75),
        ("outer_layer", "coat", "Charcoal peacoat", "Heavy wool peacoat.", ["charcoal"], ["wool"], "smart_casual", [GRAD, JOB], 210),
        ("outer_layer", "blazer", "Ivory linen blazer", "Relaxed linen blazer.", ["ivory"], ["linen"], "smart_casual", [GRAD, WED], 140),
        ("outer_layer", "cape", "Black wool cape", "Evening cape with a satin lining.", ["black"], ["wool"], "black_tie", [DIN, WED], 230),
        ("accessory", "bag", "Green leather crossbody", "Small crossbody bag in bottle green.", ["bottle green"], ["leather"], "smart_casual", [GRAD, WED], 110),
        ("accessory", "fascinator", "Feather fascinator", "Headpiece with feathers and netting.", ["ivory"], ["feather"], "formal", [WED], 60),
        ("accessory", "earrings", "Pearl drop earrings", "Freshwater pearl drops.", ["white"], ["pearl", "silver"], "formal", [GRAD, WED, DIN, JOB], 70),
    ],
}

PREFIX = {"m_fynbos": "fyn", "m_hudson": "hud", "m_thorn": "thr"}


def stock_for(slot: Slot, rng: random.Random) -> dict[str, int]:
    sizes = SIZES_BY_SLOT[slot]
    if slot == Slot.shoes:
        sizes = sizes[1:-1]  # 36 to 45
    # Mostly in stock, with some sold-out sizes so the size rule matters.
    return {s: rng.choice([0, 1, 1, 2, 3, 4]) for s in sizes}


def build() -> dict:
    rng = random.Random(SEED)
    items = []
    merchants = {m.id: m for m in MERCHANTS}
    for mid, rows in ITEMS.items():
        for n, (slot, cat, name, desc, colours, mats, form, occ, price) in enumerate(rows, start=1):
            iid = f"{PREFIX[mid]}-{n:03d}"
            item = CatalogueItem(
                id=iid, merchant_id=mid, name=name, slot=slot, category=cat, description=desc,
                colours=colours, materials=mats, formality=form, occasions=occ,
                price=price, currency=merchants[mid].currency,
                stock=stock_for(Slot(slot), rng),
                image=f"images/{iid}.png", image_credit=CREDIT,
            )
            items.append(item)
    return {
        "merchants": [m.model_dump(mode="json") for m in MERCHANTS],
        "items": [i.model_dump(mode="json") for i in items],
    }


if __name__ == "__main__":
    data = build()
    out = HERE / "catalogue.json"
    out.write_text(json.dumps(data, indent=2))
    print(f"wrote {len(data['items'])} items from {len(data['merchants'])} merchants to {out}")
