"""Run the frozen 20-brief evaluation and write the machine-readable receipt to `evidence/eval/`."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from goa.evaluation import run_frozen_evaluation  # noqa: E402
from goa.store import GoaStore  # noqa: E402


def main() -> int:
    store = GoaStore(":memory:")
    products = store.list_products()
    report, gaps = run_frozen_evaluation(products)

    out_dir = ROOT / "evidence" / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "evaluation_v1_results.json"
    out_file.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")

    goa = report["goa_tag_overlap"]
    base = report["keyword_baseline"]
    print(f"Frozen set: {report['evaluation_set']} (SHA-256 verified: {report['briefs_hash_verified']})")
    print(
        f"GOA (TAG_OVERLAP): complete={goa['verified_complete_count']}/20 "
        f"({goa['valid_complete_composition_rate']*100:.1f}%), "
        f"partial={goa['verified_partial_count']}/20, "
        f"grounding={goa['catalogue_grounding_rate']*100:.1f}%, "
        f"mean_steps={goa['mean_steps_to_sendable_enquiry']}, "
        f"gaps_logged={goa['total_demand_gaps_logged']}"
    )
    print(
        f"KEYWORD_BASELINE : complete={base['verified_complete_count']}/20 "
        f"({base['valid_complete_composition_rate']*100:.1f}%), "
        f"partial={base['verified_partial_count']}/20, "
        f"grounding={base['catalogue_grounding_rate']*100:.1f}%, "
        f"mean_steps={base['mean_steps_to_sendable_enquiry']}, "
        f"gaps_logged={base['total_demand_gaps_logged']}"
    )
    print("Top aggregated demand gaps (GOA):")
    for row in goa["aggregated_demand_gaps"][:5]:
        print("  -", row["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
