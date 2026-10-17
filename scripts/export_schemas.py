"""Export JSON Schemas and examples for all public contracts.

Usage: uv run python scripts/export_schemas.py [--check]
--check exits non-zero if committed files are out of date.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from goa.examples import EXAMPLES, EXTRA_EXAMPLES  # noqa: E402
from goa.schemas import PUBLIC_CONTRACTS, SCHEMA_VERSION  # noqa: E402

OUT = ROOT / "schemas" / f"v{SCHEMA_VERSION.split('.')[0]}"


def render() -> dict[Path, str]:
    files: dict[Path, str] = {}
    for name, model in PUBLIC_CONTRACTS.items():
        schema = model.model_json_schema(mode="validation")
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"https://goa.example/schemas/v{SCHEMA_VERSION}/{name}.schema.json"
        schema["x-goa-schema-version"] = SCHEMA_VERSION
        files[OUT / f"{name}.schema.json"] = json.dumps(schema, indent=2, sort_keys=True) + "\n"
        example = EXAMPLES[name]().model_dump(mode="json")
        files[OUT / "examples" / f"{name}.example.json"] = json.dumps(example, indent=2, sort_keys=True) + "\n"
    for stem, (_contract, factory) in EXTRA_EXAMPLES.items():
        example = factory().model_dump(mode="json")
        files[OUT / "examples" / f"{stem}.example.json"] = json.dumps(example, indent=2, sort_keys=True) + "\n"
    return files


def main() -> int:
    check = "--check" in sys.argv
    stale = []
    for path, content in render().items():
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
    if check and stale:
        print("Stale schema exports:", *stale, sep="\n  ")
        return 1
    print(("Schemas up to date" if check else f"Wrote schemas to {OUT.relative_to(ROOT)}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
