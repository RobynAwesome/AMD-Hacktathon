"""Drawn product images (600x800 PNG), one per item: the item's shape in its main colour on a soft studio ground.
No text on the image. These stand in until licensed photos replace them under the same file names.
Credits stay "placeholder", so vision_tag.py still skips them.
Run: python catalogue/product_art.py
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from placeholders import rgb_for

HERE = Path(__file__).resolve().parent
W, H, K = 600, 800, 2  # drawn at 2x, then scaled down for smooth edges
GROUND = (238, 235, 243)


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def P(pts):
    return [(x * K, y * K) for x, y in pts]


def dress(d, c, hem=690, waist=330, flare=150, sleeves=True):
    ol = shade(c, 0.72)
    if sleeves:
        d.polygon(P([(222, 175), (180, 205), (165, 290), (205, 300), (230, 235)]), fill=c, outline=ol, width=3 * K)
        d.polygon(P([(378, 175), (420, 205), (435, 290), (395, 300), (370, 235)]), fill=c, outline=ol, width=3 * K)
    d.polygon(P([(240, 160), (275, 172), (300, 215), (325, 172), (360, 160), (378, 175), (368, waist), (300 + flare, hem),
                 (300 - flare, hem), (232, waist), (222, 175)]), fill=c, outline=ol, width=3 * K)
    d.line(P([(234, waist), (366, waist)]), fill=ol, width=3 * K)
    for x in (255, 300, 345):
        d.line(P([(x, waist + 20), (x + (x - 300) * 0.6, hem - 10)]), fill=shade(c, 0.85), width=2 * K)


def jumpsuit(d, c):
    ol = shade(c, 0.72)
    d.polygon(P([(240, 160), (300, 205), (360, 160), (378, 175), (372, 340), (360, 700), (310, 700), (300, 420),
                 (290, 700), (240, 700), (228, 340), (222, 175)]), fill=c, outline=ol, width=3 * K)
    d.line(P([(230, 340), (370, 340)]), fill=ol, width=3 * K)


def jacket(d, c, length=520, sleeves=True, lapel=True, top=150):
    ol = shade(c, 0.72)
    if sleeves:
        d.polygon(P([(210, top + 20), (165, top + 60), (150, length - 40), (192, length - 30), (215, top + 110)]), fill=c, outline=ol, width=3 * K)
        d.polygon(P([(390, top + 20), (435, top + 60), (450, length - 40), (408, length - 30), (385, top + 110)]), fill=c, outline=ol, width=3 * K)
    d.polygon(P([(230, top), (300, top + 30), (370, top), (392, top + 22), (395, length), (205, length), (208, top + 22)]),
              fill=c, outline=ol, width=3 * K)
    if lapel:
        d.polygon(P([(262, top + 12), (300, top + 150), (280, top + 60)]), fill=shade(c, 0.88), outline=ol, width=2 * K)
        d.polygon(P([(338, top + 12), (300, top + 150), (320, top + 60)]), fill=shade(c, 0.88), outline=ol, width=2 * K)
    d.line(P([(300, top + 150), (300, length)]), fill=ol, width=2 * K)
    for y in (top + 190, top + 250):
        d.ellipse(P([(292, y - 6), (304, y + 6)]), fill=shade(c, 0.6))


def cape(d, c):
    ol = shade(c, 0.72)
    d.polygon(P([(250, 170), (300, 190), (350, 170), (470, 560), (130, 560)]), fill=c, outline=ol, width=3 * K)
    d.line(P([(300, 190), (300, 560)]), fill=ol, width=2 * K)


def suit(d, c):
    ol = shade(c, 0.72)
    d.polygon(P([(228, 420), (372, 420), (365, 720), (312, 720), (300, 500), (288, 720), (235, 720)]), fill=shade(c, 0.94), outline=ol, width=3 * K)
    jacket(d, c, length=470, top=130)


def coord(d, c):
    ol = shade(c, 0.72)
    d.polygon(P([(235, 170), (300, 195), (365, 170), (395, 200), (385, 330), (215, 330), (205, 200)]), fill=c, outline=ol, width=3 * K)
    d.polygon(P([(232, 360), (368, 360), (420, 690), (180, 690)]), fill=c, outline=ol, width=3 * K)


def shoe(d, c, kind, x0, y0, s=1.45):
    ol = shade(c, 0.6)

    def P(pts):  # shoe points are drawn relative to (x0, y0), then scaled up
        return [((x0 + (x - x0) * s) * K, (y0 + (y - y0) * s) * K) for x, y in pts]
    if kind == "boot":
        d.polygon(P([(x0 + 40, y0 - 120), (x0 + 110, y0 - 120), (x0 + 112, y0 - 20), (x0 + 200, y0 + 10), (x0 + 205, y0 + 40),
                     (x0 + 20, y0 + 40), (x0 + 30, y0 - 20)]), fill=c, outline=ol, width=3 * K)
    elif kind == "heel":
        d.polygon(P([(x0, y0 - 40), (x0 + 60, y0 - 50), (x0 + 120, y0 - 10), (x0 + 205, y0 + 20), (x0 + 210, y0 + 40),
                     (x0 + 120, y0 + 30), (x0 + 40, y0 - 5)]), fill=c, outline=ol, width=3 * K)
        d.polygon(P([(x0 + 2, y0 - 38), (x0 + 30, y0 - 22), (x0 + 30, y0 + 40), (x0 + 6, y0 + 40)]), fill=shade(c, 0.8), outline=ol, width=2 * K)
    else:
        d.polygon(P([(x0, y0), (x0 + 30, y0 - 35), (x0 + 120, y0 - 30), (x0 + 200, y0 + 5), (x0 + 210, y0 + 35), (x0, y0 + 35)]),
                  fill=c, outline=ol, width=3 * K)
        d.line(P([(x0, y0 + 30), (x0 + 210, y0 + 30)]), fill=shade(c, 0.5), width=4 * K)


def shoes(d, c, kind):
    shoe(d, shade(c, 0.9), kind, 105, 420)
    shoe(d, c, kind, 165, 570)


def bag(d, c):
    ol = shade(c, 0.65)
    d.arc(P([(220, 240), (380, 440)]), 180, 360, fill=ol, width=10 * K)
    d.polygon(P([(170, 340), (430, 340), (460, 600), (140, 600)]), fill=c, outline=ol, width=3 * K)
    d.polygon(P([(170, 340), (430, 340), (420, 410), (180, 410)]), fill=shade(c, 0.88), outline=ol, width=2 * K)
    d.rectangle(P([(288, 400), (312, 425)]), fill=shade(c, 0.55))


def earrings(d, c):
    for x in (240, 360):
        d.ellipse(P([(x - 10, 260), (x + 10, 280)]), fill=shade(c, 0.7))
        d.line(P([(x, 280), (x, 360)]), fill=shade(c, 0.7), width=3 * K)
        d.ellipse(P([(x - 45, 360), (x + 45, 500)]), fill=c, outline=shade(c, 0.65), width=3 * K)


def necklace(d, c):
    d.arc(P([(170, 170), (430, 520)]), 20, 160, fill=c, width=8 * K)
    d.ellipse(P([(270, 480), (330, 560)]), fill=c, outline=shade(c, 0.65), width=3 * K)


def cuff(d, c):
    d.ellipse(P([(170, 300), (430, 560)]), outline=c, width=48 * K)
    d.ellipse(P([(170, 300), (430, 560)]), outline=shade(c, 0.65), width=3 * K)


def scarf(d, c):
    ol = shade(c, 0.7)
    d.polygon(P([(200, 200), (400, 200), (380, 380), (430, 640), (350, 650), (300, 420), (250, 650), (170, 640), (220, 380)]),
              fill=c, outline=ol, width=3 * K)
    for x in range(175, 250, 12):
        d.line(P([(x, 642), (x - 2, 672)]), fill=ol, width=2 * K)


def hat(d, c, small=False):
    ol = shade(c, 0.65)
    if small:
        d.ellipse(P([(220, 330), (380, 450)]), fill=c, outline=ol, width=3 * K)
        d.line(P([(330, 340), (420, 230)]), fill=shade(c, 0.6), width=4 * K)
        return
    d.ellipse(P([(120, 420), (480, 540)]), fill=c, outline=ol, width=3 * K)
    d.chord(P([(210, 280), (390, 560)]), 180, 360, fill=c, outline=ol, width=3 * K)
    d.rectangle(P([(210, 400), (390, 425)]), fill=shade(c, 0.6))


def tie(d, c):
    ol = shade(c, 0.65)
    d.polygon(P([(270, 180), (330, 180), (315, 240), (285, 240)]), fill=c, outline=ol, width=3 * K)
    d.polygon(P([(285, 240), (315, 240), (360, 600), (300, 660), (240, 600)]), fill=c, outline=ol, width=3 * K)


def draw_item(item) -> Image.Image:
    c = rgb_for(item["colours"][0])
    img = Image.new("RGB", (W * K, H * K), GROUND)
    shadow = Image.new("L", (W * K, H * K), 0)
    ImageDraw.Draw(shadow).ellipse(P([(110, 650), (490, 700)]), fill=90)
    img.paste((200, 194, 210), mask=shadow.filter(ImageFilter.GaussianBlur(18 * K)))
    d = ImageDraw.Draw(img)
    cat = item["category"]
    if cat in ("midi dress", "shirt dress", "knit dress", "sheath dress", "blazer dress"):
        dress(d, c, hem=610, flare=110 if cat == "sheath dress" else 140)
    elif cat in ("maxi dress", "column dress"):
        dress(d, c, hem=700, flare=90 if cat == "column dress" else 165, sleeves=cat == "maxi dress")
    elif cat == "jumpsuit":
        jumpsuit(d, c)
    elif cat == "suit":
        suit(d, c)
    elif cat == "co-ord set":
        coord(d, c)
    elif cat in ("coat", "trench"):
        jacket(d, c, length=660)
    elif cat in ("blazer", "jacket", "overshirt"):
        jacket(d, c, length=520, lapel=cat != "overshirt")
    elif cat in ("cardigan", "wrap"):
        jacket(d, c, length=560, lapel=False)
    elif cat == "cape":
        cape(d, c)
    elif cat in ("ankle boots", "chelsea boots"):
        shoes(d, c, "boot")
    elif cat in ("block heels", "pumps", "slingbacks", "mules", "sandals"):
        shoes(d, c, "heel")
    elif item["slot"] == "shoes":
        shoes(d, c, "flat")
    elif cat == "bag":
        bag(d, c)
    elif cat == "earrings":
        earrings(d, c)
    elif cat == "necklace":
        necklace(d, c)
    elif cat == "cuff":
        cuff(d, c)
    elif cat == "scarf":
        scarf(d, c)
    elif cat in ("hat", "fascinator"):
        hat(d, c, small=cat == "fascinator")
    elif cat == "tie":
        tie(d, c)
    else:
        bag(d, c)
    return img.resize((W, H), Image.LANCZOS)


def main() -> None:
    data = json.loads((HERE / "catalogue.json").read_text())
    for item in data["items"]:
        draw_item(item).save(HERE / item["image"], optimize=True)
    print(f"drew {len(data['items'])} product images")


if __name__ == "__main__":
    main()
