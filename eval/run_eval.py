"""Run the 20 frozen briefs through GOA and the keyword baseline. Writes eval/results_<mode>.md and .json,
plus a blind rating sheet.

Modes:
  --offline   hand-written reference briefs, no model calls. Tests matching and rules only; labelled as such.
  (default)   live: each brief text is parsed by Gemma on AMD Token Factory (GOA_MODE=submission enforced).
              Prints the expected number of calls first and needs --yes to spend them.

Usage: python eval/run_eval.py --offline
       python eval/run_eval.py --yes
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.baseline import search  # noqa: E402
from goa import compose as C  # noqa: E402
from goa import llm, rules, usage  # noqa: E402
from goa.brief import CACHE_DIR as BRIEF_CACHE, _cache_path, parse_brief  # noqa: E402
from goa.catalogue import load  # noqa: E402
from goa.match import Candidate  # noqa: E402
from goa.schemas import Brief  # noqa: E402

EVAL = ROOT / "eval"
SIZE_IN_TEXT = re.compile(r"\b(size|xxs|xs|xl|xxl|uk \d+|us \d+|eu \d+)\b", re.I)


def check_freeze() -> dict:
    data = json.loads((EVAL / "briefs.json").read_text())
    want = json.loads((EVAL / "briefs.freeze.json").read_text())["sha256"]
    got = hashlib.sha256((EVAL / "briefs.json").read_bytes()).hexdigest()
    if got != want:
        sys.exit(f"eval/briefs.json changed after it was frozen (sha256 {got[:12]} != {want[:12]}). Refusing to run.")
    return data


def run_goa(cat, brief: Brief, b: dict, today: date) -> dict:
    look = C.compose(cat, brief, market=b["market"], scope=b["scope"], size=b["size"], shoe_size=b["shoe_size"],
                     today=today, log_gaps=False)
    problems = C.validate_look(cat, look, brief, today)
    shown = [o for p in look.parts for o in p.options[:1]]  # what the shopper sees first per part
    filled = [p for p in look.parts if p.status == "available"]
    sendable = bool(filled) and look.budget_status != "over"
    steps = 1 + (0 if SIZE_IN_TEXT.search(b["text"]) else 1) + 1 if sendable else None  # describe, sizes, send
    return {
        "complete_valid": len(filled) == len(look.parts) and look.budget_status in ("within", "no_budget") and not problems,
        "parts": len(look.parts), "filled": len(filled), "shown": len(shown),
        "shown_passing": len(shown) if not problems else len(shown) - len(problems),
        "budget_status": look.budget_status, "total": look.total_local, "currency": look.currency,
        "sendable": sendable, "steps": steps,
        "gaps": [{"slot": p.part["slot"], "want": p.part["description"], "reason": p.reason}
                 for p in look.parts if p.status == "not_on_offer"],
        "abroad_cards": len(look.abroad),
        "items": [C.chosen_offers(look)[i].name for i in range(len(C.chosen_offers(look)))],
    }


def run_baseline(cat, brief: Brief, b: dict, today: date) -> dict:
    """A diligent shopper on a static store: search each part, open results in order, check stock, size and
    delivery by hand until one works. One message per merchant at the end."""
    mk = cat.markets[b["market"]]
    clothing = rules.clothing_size(b["size"], mk.size_system)
    shoes = rules.shoe_size(b["shoe_size"], mk.size_system)
    steps, picked, shown_top, shown_passing, missing = 0, [], 0, 0, 0
    for part in brief.parts:
        hits = search(cat, part, b["market"], b["scope"])
        steps += 1  # the search
        if hits:
            top = hits[0].item
            shown_top += 1
            if rules.check_item(cat, top, b["market"], rules.size_for(top, clothing, shoes), brief.event_date, today) is None:
                shown_passing += 1
        found = None
        for h in hits:
            steps += 1  # open the item and check size, stock and delivery by hand
            sz = rules.size_for(h.item, clothing, shoes)
            if rules.check_item(cat, h.item, b["market"], sz, brief.event_date, today) is None:
                found = C._offer(cat, Candidate(h.item, float(h.score), True), b["market"], sz, today)
                break
        if found:
            picked.append(found)
        else:
            missing += 1
    budget = C._budget_local(cat, brief, b["market"])
    total = C.offers_total(picked)
    status = rules.budget_status(total, budget)
    sendable = bool(picked) and status != "over"
    merchants = len({o.merchant_id for o in picked})
    return {
        "complete_valid": missing == 0 and status in ("within", "no_budget"),
        "parts": len(brief.parts), "filled": len(picked), "shown": shown_top, "shown_passing": shown_passing,
        "budget_status": status, "total": total, "currency": mk.currency, "sendable": sendable,
        "steps": steps + merchants if sendable else None,
        "gaps": [], "items": [o.name for o in picked],
    }


def steps_text(r: dict) -> str:
    return f"{r['steps']} steps" if r["steps"] else "not sendable"


def pct(n, d):
    return f"{100 * n / d:.0f}%" if d else "n/a"


def write_results(mode: str, rows: list[dict], meta: dict) -> Path:
    n = len(rows)
    out = []
    for system in ("goa", "baseline"):
        rs = [r[system] for r in rows]
        steps = [r["steps"] for r in rs if r["steps"] is not None]
        out.append({
            "system": system,
            "valid_composition_rate": pct(sum(r["complete_valid"] for r in rs), n),
            "grounding": pct(sum(r["shown_passing"] for r in rs), sum(r["shown"] for r in rs)),
            "parts_filled": pct(sum(r["filled"] for r in rs), sum(r["parts"] for r in rs)),
            "sendable_enquiry": pct(sum(r["sendable"] for r in rs), n),
            "median_steps_to_enquiry": sorted(steps)[len(steps) // 2] if steps else "n/a",
            "gaps_captured": sum(len(r["gaps"]) for r in rs),
        })
    lines = [
        f"# GOA evaluation ({mode})", "",
        f"{n} frozen briefs (`eval/briefs.json`, sha256 `{meta['sha256'][:16]}`), rules evaluated as of {meta['today']}.",
        "",
        ("**Offline run:** briefs come from hand-written reference parses, not from Gemma. This measures matching and rules only."
         if mode == "offline" else
         f"**Live run:** every brief text was parsed by {meta.get('model')} on AMD Token Factory ({meta.get('live_calls', 0)} live calls, {meta.get('cached_calls', 0)} from cache)."),
        "",
        "| Measure | GOA | Keyword search |", "| --- | --- | --- |",
    ]
    labels = [("valid_composition_rate", "Valid composition rate (every part filled, every rule passes, within budget)"),
              ("grounding", "Grounding (first item shown per part exists and passes stock, size and delivery)"),
              ("parts_filled", "Parts filled with a verified item"),
              ("sendable_enquiry", "Briefs that reach a sendable enquiry"),
              ("median_steps_to_enquiry", "Median steps to a sendable enquiry"),
              ("gaps_captured", "Unmet parts captured as demand")]
    for key, label in labels:
        lines.append(f"| {label} | {out[0][key]} | {out[1][key]} |")
    lines += ["", "## How steps are counted", "",
              "- GOA: describe (1), enter sizes if the text does not state them (1), send (1).",
              "- Keyword search: one search per part, one step per product opened to check size, stock and delivery, "
              "one message per merchant.", "",
              "## Per brief", "", "| Brief | Market, scope | GOA | Baseline | GOA gaps |", "| --- | --- | --- | --- | --- |"]
    for r in rows:
        g, bl = r["goa"], r["baseline"]
        gaps = "; ".join(f"{x['slot']}: {x['reason']}" for x in g["gaps"]) or "-"
        lines.append(f"| {r['id']} | {r['market']}, {r['scope']} | {g['filled']}/{g['parts']} parts, {g['budget_status']}, "
                     f"{steps_text(g)} | {bl['filled']}/{bl['parts']} parts, {bl['budget_status']}, {steps_text(bl)} | {gaps} |")
    reasons = Counter(x["reason"] for r in rows for x in r["goa"]["gaps"])
    lines += ["", "## Gaps captured", "", ", ".join(f"{k}: {v}" for k, v in reasons.items()) or "none",
              "", "Manual check: open `eval/blind/` for the fit rating sheet (systems hidden, order shuffled).",
              "", "No revenue, conversion or retention claims: those need real users."]
    path = EVAL / f"results_{mode}.md"
    path.write_text("\n".join(lines) + "\n")
    (EVAL / f"results_{mode}.json").write_text(json.dumps({"meta": meta, "summary": out, "rows": rows}, indent=2))
    return path


def write_blind(mode: str, rows: list[dict]) -> None:
    blind = EVAL / "blind"
    blind.mkdir(exist_ok=True)
    entries = []
    for r in rows:
        for system in ("goa", "baseline"):
            entries.append({"brief": r["id"], "text": r["text"], "system": system,
                            "look": " + ".join(r[system]["items"]) or "(nothing found)"})
    random.Random(7).shuffle(entries)
    with (blind / f"{mode}_sheet.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["row", "brief", "what they asked for", "look shown", "fit 1 to 5 (rater A)", "fit 1 to 5 (rater B)"])
        for i, e in enumerate(entries, 1):
            w.writerow([i, e["brief"], e["text"], e["look"], "", ""])
    (blind / f"{mode}_key.json").write_text(json.dumps({i: e["system"] for i, e in enumerate(entries, 1)}, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--yes", action="store_true", help="allow live Token Factory calls")
    args = ap.parse_args()
    data = check_freeze()
    today = date.fromisoformat(data["today_for_rules"])
    cat = load()
    meta = {"sha256": json.loads((EVAL / "briefs.freeze.json").read_text())["sha256"], "today": str(today)}
    mode = "offline" if args.offline else "live"

    if mode == "live":
        os.environ["GOA_MODE"] = "submission"
        llm.check_submission()
        need = [b for b in data["briefs"] if not _cache_path(b["text"], b["market"]).exists()]
        llm.refresh_usage()
        frac = usage.USAGE.fraction_remaining()
        print(f"Live run: {len(need)} brief(s) need a Token Factory call ({len(data['briefs']) - len(need)} cached). "
              f"Quota left: {'unknown' if frac is None else f'{frac:.0%}'}. Guard: {usage.guard_level()}.")
        if need and not args.yes:
            print("Add --yes to spend these calls.")
            return 1
        if need and usage.guard_level() != "normal":
            print("Usage guard is not normal: refusing to spend quota on the eval.")
            return 1

    rows = []
    live_calls = cached = 0
    for b in data["briefs"]:
        if mode == "offline":
            brief = Brief.model_validate(b["reference_brief"])
        else:
            res = parse_brief(b["text"], market=b["market"], today=today)
            brief = res.brief
            meta["model"] = res.model
            cached += res.cached
            live_calls += 0 if res.cached else res.attempts
        rows.append({"id": b["id"], "text": b["text"], "market": b["market"], "scope": b["scope"],
                     "goa": run_goa(cat, brief, b, today), "baseline": run_baseline(cat, brief, b, today)})
    meta.update(live_calls=live_calls, cached_calls=cached)
    path = write_results(mode, rows, meta)
    write_blind(mode, rows)
    print(path.read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
