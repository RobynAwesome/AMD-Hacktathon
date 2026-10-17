"""Tag each product photo once with Gemma 4 vision on Token Factory. Cached in vision_tags.json.

Skips placeholder images (their tags would be meaningless) unless --include-placeholders.
Run after real photos are in: python catalogue/vision_tag.py
"""

import argparse
import base64
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from goa import llm  # noqa: E402
from goa.brief import _extract_json  # noqa: E402

PROMPT = (
    "Describe this clothing product photo for search. Return JSON only: "
    '{"colours": [..], "fabric": "..", "silhouette": "..", "formality": '
    '"casual|smart_casual|cocktail|formal|black_tie", "style": [..], "season": ".."}'
)


def tag(path: Path) -> dict:
    b64 = base64.b64encode(path.read_bytes()).decode()
    mime = "image/png" if path.suffix == ".png" else "image/jpeg"
    messages = [{"role": "user", "content": [
        {"type": "text", "text": PROMPT},
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
    ]}]
    return _extract_json(llm.chat(messages).text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-placeholders", action="store_true")
    args = ap.parse_args()
    data = json.loads((HERE / "catalogue.json").read_text())
    cache_path = HERE / "vision_tags.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    done = skipped = 0
    for item in data["items"]:
        if item["id"] in cache:
            continue
        if item["image_credit"].startswith("placeholder") and not args.include_placeholders:
            skipped += 1
            continue
        try:
            cache[item["id"]] = tag(HERE / item["image"])
        except llm.LLMConfigError as e:
            print(e, file=sys.stderr)
            return 2
        done += 1
        cache_path.write_text(json.dumps(cache, indent=2))
    print(f"tagged {done}, skipped {skipped} placeholders, cached {len(cache)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
