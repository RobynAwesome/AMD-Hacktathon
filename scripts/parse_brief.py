"""Send one brief to Gemma and print the structured JSON.

Usage: python scripts/parse_brief.py [--market ZA|US|GB] [--no-cache] ["description"]
With no description it uses Thandi's brief from the concept note.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from goa import llm  # noqa: E402
from goa.brief import THANDI, BriefError, parse_brief  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?", default=THANDI)
    ap.add_argument("--market", default="ZA")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()
    try:
        res = parse_brief(args.text, market=args.market, use_cache=not args.no_cache)
    except llm.LLMConfigError as e:
        print(e, file=sys.stderr)
        return 2
    except BriefError as e:
        print(e, file=sys.stderr)
        return 1
    print(json.dumps(res.brief.model_dump(mode="json"), indent=2))
    print(
        f"attempts={res.attempts} latency_ms={res.latency_ms} cached={res.cached} "
        f"provider={res.provider} model={res.model} url={res.base_url}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
