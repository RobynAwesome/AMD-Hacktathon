"""The eval harness runs offline on the frozen briefs."""

import json
from datetime import date

from eval import run_eval as R
from goa.catalogue import load
from goa.schemas import Brief


def test_briefs_are_frozen_and_valid():
    data = R.check_freeze()
    assert len(data["briefs"]) == 20
    for b in data["briefs"]:
        Brief.model_validate(b["reference_brief"])


def test_goa_is_grounded_and_baseline_is_measured():
    data = json.loads((R.EVAL / "briefs.json").read_text())
    cat, today = load(), date.fromisoformat(data["today_for_rules"])
    for b in data["briefs"][:5]:
        brief = Brief.model_validate(b["reference_brief"])
        g = R.run_goa(cat, brief, b, today)
        bl = R.run_baseline(cat, brief, b, today)
        assert g["shown_passing"] == g["shown"]  # grounding is 100% by construction
        assert bl["shown_passing"] <= bl["shown"]
        assert g["steps"] is None or g["steps"] <= 3


def test_known_gaps_are_captured():
    data = {b["id"]: b for b in json.loads((R.EVAL / "briefs.json").read_text())["briefs"]}
    cat, today = load(), date(2026, 10, 18)
    b = data["b01"]
    g = R.run_goa(cat, Brief.model_validate(b["reference_brief"]), b, today)
    assert any(x["slot"] == "outer_layer" for x in g["gaps"])
