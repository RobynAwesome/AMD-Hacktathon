"""Token Factory usage for the shared team key, plus our own call log.

Usage: python scripts/usage.py [--recent 20]
Reads GET /v1/usage (counts toward nothing) and cache/calls.jsonl. Prints no prompt text.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from goa import llm, usage  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--recent", type=int, default=15)
args = ap.parse_args()

data = llm.refresh_usage()
if data is None:
    print("Could not read /v1/usage (no Token Factory key, or the host is unreachable).", file=sys.stderr)
s = usage.summary()
frac = s["fraction_remaining"]
print(f"guard:      {s['guard']}")
print(f"remaining:  {s['remaining']} of {s['limit']}" + (f"  ({frac:.0%})" if frac is not None else ""))
print(f"reset:      {s['reset'] or '-'}    rpm limit: {s['rpm'] or '-'}    our limiter: {s['limiter']['per_minute']}/min")
print(f"our calls:  {s['calls_live']} live, {s['calls_cached']} from cache, tokens in {s['tokens_in']}, out {s['tokens_out']}")
print("\nrecent calls:")
for c in usage.recent_calls(args.recent):
    tag = "cache" if c["cached"] else ("ERROR " + c["error"] if c.get("error") else f"{c['latency_ms']} ms")
    print(f"  {c['ts']}  {c['step']:<8} {c['provider']:<14} {tag:<14} in={c.get('tokens_in')} out={c.get('tokens_out')}")
if data:
    print("\nraw /v1/usage keys:", ", ".join(sorted(k for k in data if not isinstance(data[k], list))))
