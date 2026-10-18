"""Show which provider and model each step uses, and whether prize locks hold.

Usage: python scripts/check_llm.py [--models [provider]]
Exits 1 in GOA_MODE=submission when a prize-locked step is routed elsewhere.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from goa import llm  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--models", nargs="?", const="", default=None, help="list models for a provider")
args = ap.parse_args()

print(f"mode: {llm.mode()}")
print(f"{'step':<9} {'provider':<14} {'model':<28} {'key':<4} lock")
for step in llm.STEPS:
    r = llm.route(step)
    lock = "-"
    if r.locked_to:
        lock = "ok" if r.provider == r.locked_to else f"BROKEN (needs {r.locked_to})"
    print(f"{step:<9} {r.provider:<14} {r.model:<28} {'yes' if r.key else 'no':<4} {lock}")

problems = llm.lock_problems()
if problems:
    print("\n" + "\n".join(f"- {p}" for p in problems), file=sys.stderr)
    if llm.mode() == "submission":
        sys.exit(1)

if args.models is not None:
    try:
        ids = llm.list_models(args.models or None)
    except llm.LLMConfigError as e:
        print(e, file=sys.stderr)
        sys.exit(2)
    print("\n".join(ids))
