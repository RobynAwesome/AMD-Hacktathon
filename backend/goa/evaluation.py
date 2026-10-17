"""Evaluation harness comparing GOA matching against the plain keyword baseline
on the 20 frozen evaluation briefs (`data/eval/briefs_v1.json`).

Invariants:
- Verifies the LF-normalised SHA-256 of `briefs_v1.json` against the freeze receipt.
- Never fabricates human blind fit scores (left null pending Robyn & Busi review).
- Never claims revenue, conversion or retention uplift.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from goa.brief import brief_from_eval_record
from goa.compose import compose_outfit
from goa.config import DATA_DIR, EVIDENCE_DIR
from goa.gaps import aggregate_demand_gaps
from goa.schemas import (
    CheckState,
    Composition,
    CompositionStatus,
    DemandGap,
    GapSourceType,
    MatchMethod,
    Product,
)

EXPECTED_BRIEFS_V1_SHA256 = "b52ec5e8ec858e39581b49ed7c2802f630721c03ab68eeefed12d89a63cd2baf"


def verify_frozen_briefs_hash(briefs_path: Path | None = None) -> tuple[str, bool]:
    path = briefs_path or (DATA_DIR / "eval" / "briefs_v1.json")
    raw_lf = path.read_bytes().replace(b"\r\n", b"\n")
    digest = hashlib.sha256(raw_lf).hexdigest()
    return digest, (digest == EXPECTED_BRIEFS_V1_SHA256)


def _steps_to_sendable_enquiry(
    brief_parts_count: int,
    composition: Composition,
    method: MatchMethod,
) -> int | None:
    if not composition.selected_parts or composition.pending_input_parts:
        return None
    if method == MatchMethod.KEYWORD_BASELINE:
        # Static catalogue search: 1 search query per requested part + 1 variant/size check per
        # matched item + 1 enquiry action per merchant in scope.
        return brief_parts_count + len(composition.selected_parts) + len(composition.merchant_scope)
    # GOA flow: 1 brief description + 1 composed-look review + 1 authorized enquiry per merchant in scope.
    return 1 + 1 + len(composition.merchant_scope)


def _run_method(
    records: list[dict[str, Any]],
    catalogue: list[Product],
    *,
    evaluated_on: date,
    method: MatchMethod,
    now: datetime,
) -> tuple[dict[str, Any], list[DemandGap], list[Composition]]:
    cat_by_id = {p.product_id: p for p in catalogue}
    merchant_ids = sorted({p.merchant_id for p in catalogue})

    brief_outcomes: list[dict[str, Any]] = []
    all_gaps: list[DemandGap] = []
    compositions: list[Composition] = []

    total_selected_items = 0
    grounded_selected_items = 0
    complete_count = 0
    partial_count = 0
    empty_count = 0
    single_merchant_sendable_count = 0
    steps_list: list[int] = []

    for rec in records:
        brief = brief_from_eval_record(rec, now=now)
        comp, _, gaps = compose_outfit(
            brief,
            catalogue,
            evaluated_on=evaluated_on,
            method=method,
            composition_id=f"cmp_{rec['eval_id']}_{method.value.lower()}",
            gap_source_type=GapSourceType.SCRIPTED_EVALUATION,
            searched_merchant_ids=merchant_ids,
            now=now,
        )
        compositions.append(comp)
        all_gaps.extend(gaps)

        if comp.validation_status == CompositionStatus.VERIFIED_COMPLETE:
            complete_count += 1
        elif comp.validation_status == CompositionStatus.VERIFIED_PARTIAL:
            partial_count += 1
        else:
            empty_count += 1

        if comp.selected_parts and not comp.pending_input_parts and len(comp.merchant_scope) == 1:
            single_merchant_sendable_count += 1

        for sp in comp.selected_parts:
            total_selected_items += 1
            in_cat = sp.product_id in cat_by_id
            vr_ok = (
                sp.verification_result.exists_in_catalogue.state == CheckState.PASS
                and sp.verification_result.overall == CheckState.PASS
            )
            if in_cat and vr_ok:
                grounded_selected_items += 1

        steps = _steps_to_sendable_enquiry(len(brief.requested_parts), comp, method)
        if steps is not None:
            steps_list.append(steps)

        brief_outcomes.append(
            {
                "eval_id": rec["eval_id"],
                "brief_id": brief.brief_id,
                "validation_status": comp.validation_status.value,
                "requested_parts_count": len(brief.requested_parts),
                "selected_parts_count": len(comp.selected_parts),
                "unmet_parts_count": len(comp.unmet_parts),
                "pending_input_parts_count": len(comp.pending_input_parts),
                "total_price_cents": comp.total_price_cents,
                "budget_cents": comp.budget_cents,
                "merchant_scope": comp.merchant_scope,
                "steps_to_sendable_enquiry": steps,
                "selected_product_ids": [sp.product_id for sp in comp.selected_parts],
                "unmet_reasons": {u.part_id: [r.value for r in u.reasons] for u in comp.unmet_parts},
                "pending_input_reasons": {
                    p.part_id: [r.value for r in p.missing_inputs] for p in comp.pending_input_parts
                },
                "blind_human_fit_score_robyn": None,
                "blind_human_fit_score_busi": None,
            }
        )

    n = len(records)
    grounding_rate = 1.0 if total_selected_items == 0 else round(grounded_selected_items / total_selected_items, 4)
    avg_steps = round(sum(steps_list) / len(steps_list), 2) if steps_list else None
    aggregated_gaps = aggregate_demand_gaps(all_gaps, total_briefs=n)

    summary = {
        "match_method": method.value,
        "brief_count": n,
        "verified_complete_count": complete_count,
        "verified_partial_count": partial_count,
        "empty_count": empty_count,
        "valid_complete_composition_rate": round(complete_count / n, 4),
        "valid_partial_or_complete_rate": round((complete_count + partial_count) / n, 4),
        "single_merchant_sendable_count": single_merchant_sendable_count,
        "total_selected_items": total_selected_items,
        "grounded_selected_items": grounded_selected_items,
        "catalogue_grounding_rate": grounding_rate,
        "sendable_enquiry_brief_count": len(steps_list),
        "mean_steps_to_sendable_enquiry": avg_steps,
        "total_demand_gaps_logged": len(all_gaps),
        "aggregated_demand_gaps": aggregated_gaps,
        "blind_human_fit_scores_status": "PENDING_HUMAN_REVIEW_BY_ROBYN_AND_BUSI",
        "brief_outcomes": brief_outcomes,
    }
    return summary, all_gaps, compositions


def run_frozen_evaluation(
    catalogue: list[Product],
    *,
    briefs_path: Path | None = None,
    now: datetime | None = None,
) -> tuple[dict[str, Any], list[DemandGap]]:
    """Run both `TAG_OVERLAP` and `KEYWORD_BASELINE` on `briefs_v1.json`."""
    ts = now or datetime.now(timezone.utc)
    path = briefs_path or (DATA_DIR / "eval" / "briefs_v1.json")
    digest, hash_matches = verify_frozen_briefs_hash(path)
    if not hash_matches:
        raise ValueError(
            f"Frozen evaluation briefs SHA-256 mismatch: expected {EXPECTED_BRIEFS_V1_SHA256}, got {digest}"
        )

    payload = json.loads(path.read_text(encoding="utf-8"))
    evaluated_on = date.fromisoformat(payload["reference_date"])
    records = payload["briefs"]

    goa_summary, goa_gaps, _ = _run_method(
        records, catalogue, evaluated_on=evaluated_on, method=MatchMethod.TAG_OVERLAP, now=ts
    )
    baseline_summary, _, _ = _run_method(
        records, catalogue, evaluated_on=evaluated_on, method=MatchMethod.KEYWORD_BASELINE, now=ts
    )

    report = {
        "evaluation_set": payload["frozen_set"],
        "briefs_file": "data/eval/briefs_v1.json",
        "briefs_sha256_lf": digest,
        "briefs_hash_verified": hash_matches,
        "evaluated_on": evaluated_on.isoformat(),
        "generated_at": ts.isoformat(),
        "catalogue_product_count": len(catalogue),
        "goa_tag_overlap": goa_summary,
        "keyword_baseline": baseline_summary,
        "disclaimers": [
            "All merchants and products are fictional demo data.",
            "Match method run for GOA is TAG_OVERLAP (structured attribute/tag overlap), not neural embeddings.",
            "Blind human fit scores (1-5) are pending review by Robyn and Busi and are not fabricated here.",
            "No revenue, conversion or retention uplift is claimed.",
        ],
    }
    return report, goa_gaps
