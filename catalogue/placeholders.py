"""Placeholder product images (600x800 PNG), one per item, in the item's main colour.
Replace each with a licensed photo of the same file name, then run vision_tag.py.
Run: python catalogue/placeholders.py
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent

COLOURS = {
    "green": (78, 128, 92), "sage": (156, 175, 136), "emerald": (31, 120, 82), "olive": (110, 112, 60),
    "forest": (34, 85, 52), "bottle": (25, 77, 52), "mint": (170, 220, 190), "ivory": (240, 234, 214),
    "cream": (238, 228, 205), "stone": (190, 180, 160), "natural": (214, 196, 160), "beige": (215, 197, 165),
    "tan": (196, 150, 100), "brown": (110, 75, 50), "cognac": (150, 85, 40), "camel": (190, 145, 95),
    "gold": (200, 165, 80), "silver": (190, 192, 198), "champagne": (230, 210, 170), "black": (30, 30, 32),
    "charcoal": (60, 62, 66), "grey": (140, 140, 145), "navy": (30, 45, 85), "burgundy": (110, 30, 45),
    "oxblood": (90, 25, 30), "lilac": (190, 165, 210), "pink": (225, 150, 170), "red": (180, 40, 45),
    "nude": (220, 185, 160), "white": (245, 245, 245), "indigo": (40, 55, 110), "ochre": (200, 140, 40),
    "terracotta": (190, 95, 65), "jade": (60, 150, 110), "coral": (230, 100, 80), "orange": (230, 130, 40),
    "burnt": (190, 90, 40), "yellow": (230, 200, 60), "oatmeal": (222, 210, 186),
}


def rgb_for(colour: str) -> tuple[int, int, int]:
    for word in colour.lower().split():
        if word in COLOURS:
            return COLOURS[word]
    return (150, 150, 150)


def font(size: int):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def wrap(text: str, width: int) -> list[str]:
    lines, line = [], ""
    for w in text.split():
        if len(line) + len(w) + 1 > width:
            lines.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    return lines + [line]


def main() -> None:
    data = json.loads((HERE / "catalogue.json").read_text())
    for item in data["items"]:
        bg = rgb_for(item["colours"][0])
        fg = (20, 20, 20) if sum(bg) > 420 else (245, 245, 245)
        img = Image.new("RGB", (600, 800), bg)
        d = ImageDraw.Draw(img)
        y = 300
        for line in wrap(item["name"], 20):
            d.text((300, y), line, fill=fg, font=font(38), anchor="mm")
            y += 50
        d.text((300, y + 20), item["slot"].replace("_", " "), fill=fg, font=font(24), anchor="mm")
        d.text((300, 760), "placeholder", fill=fg, font=font(18), anchor="mm")
        img.save(HERE / item["image"])
    print(f"wrote {len(data['items'])} placeholder images")


if __name__ == "__main__":
    main()
