"""Synthetic catalogue generator: 7 fictional merchants in 6 markets. Deterministic (fixed seed).

Merchants (all fictional):
  Imbali House (Johannesburg), Ridge & Rand (Durban), Fynbos Atelier (Cape Town), Ọ̀ṢỌ́ Studio (Lagos),
  Hudson & Pine (New York), Thornbury Lane (London), Via Seta (Milan), Lotus Thread (Shenzhen).
Every merchant ships to every market, with delivery days and a shipping cost.
Gaps on purpose, so the gap view has signal: no green outer layer anywhere, no green shoes,
and nothing above XL.
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
MARKETS = {m["code"]: m for m in json.loads((HERE.parent / "goa" / "markets.json").read_text())["markets"]}

# Delivery days from a merchant's market (row) to the shopper's market (column).
DAYS = {
    "ZA": {"ZA": 3, "NG": 7, "GB": 8, "EU": 9, "US": 11, "CN": 12},
    "NG": {"NG": 3, "ZA": 7, "GB": 6, "EU": 7, "US": 9, "CN": 12},
    "US": {"US": 3, "GB": 6, "EU": 7, "NG": 10, "ZA": 11, "CN": 9},
    "GB": {"GB": 2, "EU": 4, "US": 6, "NG": 6, "ZA": 8, "CN": 9},
    "EU": {"EU": 3, "GB": 4, "US": 7, "NG": 7, "ZA": 9, "CN": 9},
    "CN": {"CN": 3, "US": 8, "GB": 8, "EU": 8, "ZA": 10, "NG": 11},
}

# (id, name, about, city, country, market, email, intl shipping in USD)
MERCHANT_ROWS = [
    ("m_imbali", "Imbali House", "Black-owned Johannesburg label: sculptural tailoring, Karoo mohair and merino, and silk printed from paintings by Johannesburg artists.",
     "Johannesburg", "ZA", "ZA", "imbali.house@example.com", 22),
    ("m_ridge", "Ridge & Rand", "Durban leather studio: sneakers, loafers, mules and bags in South African leather, made in KwaZulu-Natal.",
     "Durban", "ZA", "ZA", "ridgeandrand@example.com", 22),
    ("m_fynbos", "Fynbos Atelier", "Cape Town studio: linens, merino knitwear and a print line drawn by a Cape Town illustrator.",
     "Cape Town", "ZA", "ZA", "fynbos.orders@example.com", 25),
    ("m_oso", "Ọ̀ṢỌ́ Studio", "Contemporary Lagos label: minimal tailoring, oversized shirting, column dresses and raw silk.",
     "Lagos", "NG", "NG", "oso.studio@example.com", 24),
    ("m_hudson", "Hudson & Pine", "New York tailoring and winter-ready knitwear.",
     "New York", "US", "US", "hudsonpine.hello@example.com", 28),
    ("m_thorn", "Thornbury Lane", "London heritage fabrics: tweed, wool and polished leather.",
     "London", "GB", "GB", "thornbury.studio@example.com", 20),
    ("m_seta", "Via Seta", "Milan atelier for silk, cashmere and fine Italian leather.",
     "Milan", "IT", "EU", "viaseta.atelier@example.com", 22),
    ("m_lotus", "Lotus Thread", "Shenzhen label: sharp prices, fast production, long shipping.",
     "Shenzhen", "CN", "CN", "lotus.thread@example.com", 12),
]


def _cost(usd: float, currency_market: str) -> float:
    return round(usd / MARKETS[currency_market]["fx_to_usd"], 0)


def make_merchant(mid, name, about, city, country, market, email, intl_usd) -> Merchant:
    region = MARKETS[market]["region"]
    ships = {}
    for to, days in DAYS[market].items():
        if to == market:
            usd = 5
        elif MARKETS[to]["region"] == region:
            usd = round(intl_usd * 0.6)
        else:
            usd = intl_usd
        ships[to] = {"days": days, "cost": _cost(usd, market)}
    return Merchant(id=mid, name=name, about=about, city=city, country=country, market=market,
                    region=region, currency=MARKETS[market]["currency"], email=email, ships_to=ships)


MERCHANTS = [make_merchant(*row) for row in MERCHANT_ROWS]

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
        ("garment", "midi dress", "Coastline print linen midi", "Linen midi printed with a line drawing of the Atlantic coast by a Cape Town illustrator.", ["olive", "cream"], ["linen"], "smart_casual", [GRAD, WED], 1450),
        ("shoes", "block heels", "Tan block-heel sandals", "Leather sandals with a low block heel, steady on grass.", ["tan"], ["leather"], "smart_casual", [GRAD, WED], 750),
        ("shoes", "flats", "Gold pointed flats", "Metallic leather flats, all-day comfort.", ["gold"], ["leather"], "smart_casual", [GRAD, WED, DIN], 620),
        ("shoes", "espadrilles", "Natural wedge espadrilles", "Jute wedge espadrilles with ankle ties.", ["natural", "beige"], ["jute", "canvas"], "casual", [GRAD], 540),
        ("shoes", "loafers", "Brown suede loafers", "Soft suede loafers, unlined.", ["brown"], ["suede"], "smart_casual", [GRAD, JOB], 980),
        ("outer_layer", "cardigan", "Cream merino rib cardigan", "Fine-rib merino cardigan for cool evenings.", ["cream"], ["merino wool"], "smart_casual", [GRAD, WED, JOB], 890),
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
    "m_imbali": [
        ("garment", "column dress", "Emerald painted-print silk column", "Silk twill column dress printed from an original abstract painting by a Johannesburg artist.", ["emerald green", "gold"], ["silk"], "cocktail", [GRAD, WED, DIN], 2600),
        ("garment", "blazer dress", "Ink sculptural blazer dress", "Double-breasted blazer dress with a sculpted shoulder.", ["black"], ["wool crepe"], "formal", [JOB, GRAD, DIN], 2950),
        ("garment", "suit", "Sage wide-leg trouser suit", "Relaxed single-breasted suit with wide trousers.", ["sage green"], ["linen", "wool"], "smart_casual", [GRAD, JOB, WED], 3100),
        ("garment", "shirt dress", "Indigo shweshwe shirt dress", "Oversized shirt dress in indigo shweshwe with a hidden placket.", ["indigo blue"], ["cotton", "shweshwe"], "smart_casual", [GRAD], 1650),
        ("garment", "co-ord set", "Ochre pleated skirt set", "Boxy top and knife-pleated midi skirt.", ["ochre"], ["crepe"], "smart_casual", [GRAD, WED], 1980),
        ("garment", "knit dress", "Charcoal merino column dress", "Fine merino knit dress, long sleeves, ankle length.", ["charcoal"], ["merino wool"], "smart_casual", [JOB, GRAD, DIN], 1850),
        ("shoes", "mules", "Black sculpted-heel mules", "Leather mules on a sculpted low heel.", ["black"], ["leather"], "cocktail", [WED, DIN, GRAD], 1350),
        ("outer_layer", "coat", "Karoo mohair wrap coat", "Brushed mohair wrap coat, spun and woven in the Eastern Cape.", ["oatmeal", "cream"], ["mohair"], "smart_casual", [GRAD, JOB, WED, DIN], 3400),
        ("outer_layer", "jacket", "Cropped tailored jacket", "Cropped jacket with a shweshwe lining.", ["black"], ["wool blend", "shweshwe"], "smart_casual", [JOB, GRAD], 2200),
        ("accessory", "scarf", "Painted-print silk scarf", "Silk scarf printed from the same original painting as the column dress.", ["gold", "green", "black"], ["silk"], "smart_casual", [GRAD, WED, DIN], 650),
        ("accessory", "necklace", "Minimal brass collar", "Hand-forged brass collar.", ["gold"], ["brass"], "smart_casual", [GRAD, WED, DIN], 520),
        ("accessory", "earrings", "Bead and silver drop earrings", "Single strand of black glass beads on silver.", ["black", "silver"], ["glass beads", "silver"], "smart_casual", [GRAD, WED, DIN, JOB], 420),
    ],
    "m_oso": [
        ("garment", "shirt dress", "Oversized poplin shirt dress", "Crisp oversized shirt dress with a dropped shoulder.", ["white"], ["cotton"], "smart_casual", [GRAD, JOB], 85000),
        ("garment", "column dress", "Emerald washed-crepe column", "Bias-cut column dress in washed crepe.", ["emerald green"], ["crepe"], "cocktail", [WED, GRAD, DIN], 120000),
        ("garment", "co-ord set", "Indigo wrap skirt set", "Hand-dyed indigo cotton, cut as a clean wrap skirt and boxy top.", ["indigo blue"], ["cotton"], "smart_casual", [GRAD, WED], 98000),
        ("garment", "suit", "Stone boxy linen two-piece", "Boxy jacket and straight trousers in heavy linen.", ["stone"], ["linen"], "smart_casual", [GRAD, JOB], 140000),
        ("garment", "jumpsuit", "Black tuxedo jumpsuit", "Tailored jumpsuit with satin lapels.", ["black"], ["wool blend", "satin"], "formal", [DIN, WED], 165000),
        ("shoes", "slides", "Tan square-toe slides", "Square-toe leather slides.", ["tan"], ["leather"], "casual", [GRAD], 42000),
        ("shoes", "block heels", "Black sculpted block heels", "Leather heels on a sculpted block.", ["black"], ["leather"], "cocktail", [WED, DIN, GRAD], 65000),
        ("outer_layer", "overshirt", "Cream linen overshirt", "Oversized linen overshirt to wear open.", ["cream"], ["linen"], "casual", [GRAD], 58000),
        ("outer_layer", "blazer", "Navy raw-silk blazer", "Unstructured blazer in raw silk.", ["navy"], ["silk"], "smart_casual", [JOB, WED, GRAD], 125000),
        ("accessory", "cuff", "Hammered brass cuff", "Wide hammered brass cuff.", ["gold"], ["brass"], "smart_casual", [GRAD, WED, DIN], 18000),
        ("accessory", "bag", "Cognac leather bucket bag", "Soft leather bucket bag.", ["cognac"], ["leather"], "smart_casual", [GRAD, WED], 70000),
        ("accessory", "earrings", "Sculptural silver earrings", "Cast silver earrings.", ["silver"], ["silver"], "smart_casual", [GRAD, WED, DIN], 35000),
    ],
    "m_ridge": [
        ("shoes", "sneakers", "White leather court sneakers", "Low-top sneakers in South African leather.", ["white"], ["leather"], "casual", [GRAD], 1450),
        ("shoes", "mules", "Tan leather block mules", "Low block-heel mules, steady on grass.", ["tan"], ["leather"], "smart_casual", [GRAD, WED], 1290),
        ("shoes", "loafers", "Black leather loafers", "Hand-lasted penny loafers.", ["black"], ["leather"], "smart_casual", [JOB, GRAD], 1590),
        ("shoes", "boots", "Cognac Chelsea boots", "Leather Chelsea boots on a crepe sole.", ["cognac"], ["leather"], "smart_casual", [GRAD, JOB], 1890),
        ("shoes", "slingbacks", "Bone leather slingbacks", "Kitten-heel slingbacks.", ["cream"], ["leather"], "cocktail", [WED, DIN, GRAD], 1390),
        ("shoes", "sandals", "Black strappy block sandals", "Strappy sandals on a low block heel.", ["black"], ["leather"], "smart_casual", [GRAD, WED, DIN], 1190),
        ("accessory", "bag", "Black structured tote", "Structured leather tote that fits a laptop.", ["black"], ["leather"], "smart_casual", [JOB, GRAD], 1690),
        ("accessory", "bag", "Cognac mini crossbody", "Small crossbody bag with an adjustable strap.", ["cognac"], ["leather"], "smart_casual", [GRAD, WED], 990),
        ("accessory", "belt", "Woven leather belt", "Hand-woven leather belt.", ["tan"], ["leather"], "smart_casual", [GRAD, JOB], 520),
        ("accessory", "bag", "Stone saddle-stitched clutch", "Saddle-stitched leather clutch.", ["stone"], ["leather"], "smart_casual", [WED, DIN, GRAD], 890),
    ],
    "m_seta": [
        ("garment", "midi dress", "Bottle green silk midi", "Bias-cut silk midi with a cowl neck.", ["bottle green"], ["silk"], "cocktail", [WED, GRAD, DIN], 320),
        ("garment", "suit", "Cream linen trouser suit", "Soft-shouldered linen blazer and wide trousers.", ["cream"], ["linen"], "smart_casual", [GRAD, WED, JOB], 420),
        ("garment", "wrap dress", "Navy crepe wrap dress", "Knee-length wrap dress in heavy crepe.", ["navy"], ["crepe"], "smart_casual", [JOB, GRAD], 210),
        ("garment", "gown", "Black silk evening gown", "Floor-length silk gown with an open back.", ["black"], ["silk"], "black_tie", [DIN, WED], 590),
        ("garment", "jumpsuit", "Olive pleated jumpsuit", "Pleated viscose jumpsuit with a halter neck.", ["olive"], ["viscose"], "smart_casual", [GRAD], 240),
        ("shoes", "sandals", "Tan suede block sandals", "Italian suede sandals on a low block heel.", ["tan"], ["suede"], "smart_casual", [GRAD, WED], 165),
        ("shoes", "loafers", "Black leather loafers", "Hand-finished Italian leather loafers.", ["black"], ["leather"], "smart_casual", [JOB, GRAD], 195),
        ("shoes", "heels", "Gold strappy heels", "Fine-strap heels in metallic leather.", ["gold"], ["leather"], "cocktail", [WED, DIN], 180),
        ("outer_layer", "coat", "Camel cashmere wrap coat", "Belted cashmere wrap coat.", ["camel"], ["cashmere"], "formal", [GRAD, WED, DIN, JOB], 690),
        ("outer_layer", "duster", "Ivory silk duster", "Lightweight silk duster for warm evenings.", ["ivory"], ["silk"], "cocktail", [WED, GRAD], 260),
        ("outer_layer", "blazer", "Navy unstructured blazer", "Unlined wool blazer.", ["navy"], ["wool"], "smart_casual", [JOB, GRAD], 280),
        ("accessory", "scarf", "Printed silk scarf", "Twill scarf in green and gold.", ["green", "gold"], ["silk"], "smart_casual", [GRAD, WED], 85),
        ("accessory", "bag", "Cognac leather mini bag", "Top-handle mini bag.", ["cognac"], ["leather"], "smart_casual", [GRAD, WED, DIN], 210),
        ("accessory", "earrings", "Gold hoop earrings", "Gold-plated silver hoops.", ["gold"], ["silver"], "smart_casual", [GRAD, WED, DIN, JOB], 70),
    ],
    "m_lotus": [
        ("garment", "midi dress", "Jade silk qipao-inspired midi", "Mandarin-collar silk midi with knot buttons.", ["jade green"], ["silk"], "cocktail", [WED, DIN, GRAD], 680),
        ("garment", "co-ord set", "Black pleated skirt set", "Fitted top and pleated midi skirt.", ["black"], ["polyester"], "smart_casual", [JOB, GRAD], 320),
        ("garment", "shirt dress", "Sage linen shirt dress", "Relaxed linen shirt dress with a tie belt.", ["sage green"], ["linen"], "casual", [GRAD], 260),
        ("garment", "suit", "Navy slim suit", "Slim two-piece suit.", ["navy"], ["polyester", "wool blend"], "formal", [JOB, WED, GRAD], 890),
        ("garment", "slip dress", "Champagne satin slip dress", "Midi slip dress in liquid satin.", ["champagne"], ["satin"], "cocktail", [WED, DIN], 350),
        ("garment", "maxi dress", "White tiered maxi", "Tiered cotton maxi with puff sleeves.", ["white"], ["cotton"], "casual", [GRAD, WED], 290),
        ("shoes", "block heels", "Black patent block heels", "Patent block heels with a square toe.", ["black"], ["faux leather"], "smart_casual", [GRAD, JOB, DIN], 220),
        ("shoes", "flats", "Pearl-strap flats", "Ivory flats with a faux-pearl strap.", ["ivory"], ["faux leather"], "smart_casual", [WED, GRAD], 180),
        ("shoes", "sneakers", "White leather sneakers", "Minimal leather sneakers.", ["white"], ["leather"], "casual", [GRAD], 260),
        ("outer_layer", "jacket", "Cropped tweed jacket", "Pink and cream tweed jacket with fringed edges.", ["pink", "cream"], ["polyester tweed"], "smart_casual", [GRAD, WED], 380),
        ("outer_layer", "trench", "Lightweight stone trench", "Packable trench coat.", ["stone"], ["polyester"], "smart_casual", [JOB, GRAD], 420),
        ("outer_layer", "coat", "Grey wool-blend coat", "Single-breasted coat.", ["grey"], ["wool blend"], "smart_casual", [GRAD, JOB], 560),
        ("accessory", "hair clip", "Pearl hair clip set", "Set of three faux-pearl clips.", ["white"], ["faux pearl"], "smart_casual", [GRAD, WED], 60),
        ("accessory", "bag", "Black top-handle mini bag", "Structured mini bag.", ["black"], ["faux leather"], "smart_casual", [GRAD, WED, DIN], 160),
    ],
}

PREFIX = {"m_imbali": "imb", "m_fynbos": "fyn", "m_oso": "oso", "m_ridge": "rid", "m_hudson": "hud", "m_thorn": "thr", "m_seta": "set", "m_lotus": "lot"}


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
