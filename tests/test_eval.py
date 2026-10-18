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


def test_freeze_survives_windows_line_endings(tmp_path, monkeypatch):
    raw = (R.EVAL / "briefs.json").read_bytes()
    (tmp_path / "briefs.json").write_bytes(raw.replace(b"\n", b"\r\n"))
    (tmp_path / "briefs.freeze.json").write_bytes((R.EVAL / "briefs.freeze.json").read_bytes())
    monkeypatch.setattr(R, "EVAL", tmp_path)
    assert len(R.check_freeze()["briefs"]) == 20


def test_freeze_survives_bom_and_doubled_carriage_returns(tmp_path, monkeypatch):
    raw = (R.EVAL / "briefs.json").read_bytes()
    (tmp_path / "briefs.json").write_bytes(b"\xef\xbb\xbf" + raw.replace(b"\n", b"\r\r\n"))
    (tmp_path / "briefs.freeze.json").write_bytes((R.EVAL / "briefs.freeze.json").read_bytes())
    monkeypatch.setattr(R, "EVAL", tmp_path)
    assert len(R.check_freeze()["briefs"]) == 20


def test_freeze_survives_reformatting_but_not_edits(tmp_path, monkeypatch):
    data = json.loads((R.EVAL / "briefs.json").read_text(encoding="utf-8"))
    (tmp_path / "briefs.freeze.json").write_bytes((R.EVAL / "briefs.freeze.json").read_bytes())
    monkeypatch.setattr(R, "EVAL", tmp_path)
    (tmp_path / "briefs.json").write_text(json.dumps(data, indent=4), encoding="utf-8")
    assert len(R.check_freeze()["briefs"]) == 20
    data["briefs"][0]["text"] += " edited"
    (tmp_path / "briefs.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    import pytest

    with pytest.raises(SystemExit):
        R.check_freeze()
