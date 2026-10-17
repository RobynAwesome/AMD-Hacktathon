"""Demand-gap capture and aggregation for GOA Creative Commerce.

Only genuine supply-side unmet parts (`Composition.unmet_parts`) become `DemandGap`
records. Missing customer inputs (`Composition.pending_input_parts`) are never
logged as demand gaps. All merchant dashboard counts are computed from stored
`DemandGap` records, never hardcoded.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable

from goa.schemas import (
    CUSTOMER_INPUT_REASONS,
    Composition,
    DemandGap,
    DesiredAttributes,
    GapSourceType,
    PartType,
)


def describe_desired_item(part_type: PartType, attrs: DesiredAttributes) -> str:
    """Build a concise human-readable label from a part's desired attributes."""
    tokens: list[str] = []
    if attrs.colours:
        tokens.append("/".join(dict.fromkeys(c.lower() for c in attrs.colours)))
    if attrs.materials:
        tokens.append("/".join(dict.fromkeys(m.lower() for m in attrs.materials)))
    if attrs.garment_keywords:
        tokens.append("/".join(dict.fromkeys(k.lower() for k in attrs.garment_keywords)))
    else:
        default_noun = {
            PartType.DRESS_OR_SUIT: "dress or suit",
            PartType.SHOES: "shoes",
            PartType.OUTER_LAYER: "outer layer",
            PartType.ACCESSORY: "accessory",
        }[part_type]
        tokens.append(default_noun)
    return " ".join(tokens)


def build_demand_gaps_for_composition(
    composition: Composition,
    *,
    searched_merchant_ids: list[str],
    source_type: GapSourceType,
    now: datetime | None = None,
) -> list[DemandGap]:
    """Create validated `DemandGap` records for each supply-side `UnmetPart`.

    `composition.pending_input_parts` are intentionally ignored so missing customer
    sizes/dates/budgets never pollute merchant demand signals.
    """
    ts = now or datetime.now(timezone.utc)
    gaps: list[DemandGap] = []
    for idx, unmet in enumerate(composition.unmet_parts, start=1):
        primary_reason = unmet.reasons[0]
        if primary_reason in CUSTOMER_INPUT_REASONS:
            continue
        gap_id = f"gap_{composition.brief_id[4:]}_{unmet.part_id[4:]}_{idx}"
        gaps.append(
            DemandGap(
                gap_id=gap_id,
                brief_id=composition.brief_id,
                part_type=unmet.part_type,
                desired_attributes=unmet.desired_attributes,
                reason=primary_reason,
                merchant_scope=list(searched_merchant_ids),
                source_type=source_type,
                created_at=ts,
            )
        )
    return gaps


def aggregate_demand_gaps(
    gaps: Iterable[DemandGap],
    *,
    total_briefs: int | None = None,
    source_filter: GapSourceType | None = None,
) -> list[dict[str, object]]:
    """Aggregate `DemandGap` records by normalized requested item signature."""
    filtered = [
        g for g in gaps if (source_filter is None or g.source_type == source_filter)
    ]
    buckets: dict[tuple[str, str], list[DemandGap]] = defaultdict(list)
    for gap in filtered:
        label = describe_desired_item(gap.part_type, gap.desired_attributes)
        buckets[(gap.part_type.value, label)].append(gap)

    rows: list[dict[str, object]] = []
    for (part_type_val, label), bucket in buckets.items():
        brief_ids = sorted({g.brief_id for g in bucket})
        reasons = sorted({g.reason.value for g in bucket})
        count = len(brief_ids)
        if total_briefs is not None and total_briefs > 0:
            summary = (
                f"{count} of {total_briefs} briefs requested a {label} "
                f"that was not available ({', '.join(reasons)})."
            )
        else:
            summary = f"{count} brief(s) requested a {label} that was not available ({', '.join(reasons)})."
        rows.append(
            {
                "part_type": part_type_val,
                "requested_item_label": label,
                "brief_count": count,
                "occurrence_count": len(bucket),
                "total_briefs_in_scope": total_briefs,
                "brief_ids": brief_ids,
                "reasons": reasons,
                "source_types": sorted({g.source_type.value for g in bucket}),
                "summary": summary,
                "disclaimer": "Derived from stored GOA demo/scripted evaluation briefs. Not live market demand.",
            }
        )

    rows.sort(key=lambda r: (-int(r["brief_count"]), str(r["requested_item_label"])))
    return rows
