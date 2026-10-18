"""API tests with the offline sample brief (no model calls)."""

import pytest
from fastapi.testclient import TestClient

from goa import compose as C
from goa import narrate
from goa.brief import THANDI


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GOA_ALLOW_SAMPLE", "1")
    for k in ["TOKEN_FACTORY_API_KEY", "RADEON_API_KEY", "GOA_PROVIDER"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(C, "GAPS_LOG", tmp_path / "gaps.jsonl")
    monkeypatch.setattr(narrate, "ENQUIRIES_LOG", tmp_path / "enq.jsonl")
    import goa.gaps

    monkeypatch.setattr(goa.gaps, "GAPS_LOG", tmp_path / "gaps.jsonl")
    from app.main import app

    with TestClient(app) as c:
        yield c


def look(client, **kw):
    body = {"text": THANDI, "market": "ZA", "scope": "global", "size": "M", "shoe_size": "38", **kw}
    r = client.post("/api/look", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_config(client):
    d = client.get("/api/config").json()
    assert {m["code"] for m in d["markets"]} == {"ZA", "NG", "US", "GB", "EU", "CN"}
    assert any(m["name"] == "Imbali House" for m in d["merchants"])


def test_look_is_labelled_sample_and_logs_a_gap(client):
    d = look(client)
    assert d["sample"] is True
    assert d["calls"][0]["provider"].startswith("sample")
    assert any(p["status"] == "not_on_offer" for p in d["look"]["parts"])
    gaps = client.get("/api/gaps").json()
    assert gaps and "green" in gaps[0]["want"]


def test_swap_and_enquiry(client):
    d = look(client)
    idx = next(i for i, p in enumerate(d["look"]["parts"]) if len(p["options"]) > 1)
    s = client.post("/api/swap", json={"look_id": d["look_id"], "part": idx, "option": 1})
    assert s.status_code == 200
    if s.json()["look"]["budget_status"] == "over":
        r = client.post("/api/enquiry", json={"look_id": d["look_id"], "name": "Thandi"})
        assert r.status_code == 400 and "over budget" in r.json()["detail"]
        client.post("/api/swap", json={"look_id": d["look_id"], "part": idx, "option": 0})
    e = client.post("/api/enquiry", json={"look_id": d["look_id"], "name": "Thandi"})
    assert e.status_code == 200, e.text
    enq = e.json()["enquiries"]
    assert enq and all(q["to"].endswith("@example.com") for q in enq)
    assert client.get("/api/enquiries").json()


def test_enquiry_needs_size(client):
    d = look(client, size=None)
    r = client.post("/api/enquiry", json={"look_id": d["look_id"]})
    assert r.status_code == 400 and "size" in r.json()["detail"]


def test_unknown_text_without_model_is_a_clear_error(client):
    r = client.post("/api/look", json={"text": "something else entirely", "market": "ZA"})
    assert r.status_code == 503


def test_preread_is_instant_and_has_chips(client):
    d = client.post("/api/preread", json={"text": THANDI, "market": "ZA"}).json()
    keys = {c["key"] for c in d["chips"]}
    assert {"occasion", "event_date", "location", "budget", "colour"} <= keys
    assert len(d["first_glance"]) == 6 and d["needs_size"] is True


def brief_id(client):
    d = client.post("/api/brief", json={"text": THANDI, "market": "ZA"}).json()
    assert d["sample"] is True
    return d["brief_id"]


def test_compose_reruns_without_model_calls(client):
    bid = brief_id(client)
    body = {"brief_id": bid, "market": "ZA", "scope": "global", "size": "M", "shoe_size": "38"}
    a = client.post("/api/compose", json=body).json()
    assert a["look"]["receipt"]["checked"] > 0 and a["look"]["receipt"]["searched"] >= a["look"]["receipt"]["checked"]
    b = client.post("/api/compose", json={**body, "prefs": {"no_heels": True}}).json()
    for p in b["look"]["parts"]:
        if p["part"]["slot"] == "shoes":
            assert all("heel" not in o["name"].lower() for o in p["options"])


def test_chip_override_changes_the_rules(client):
    bid = brief_id(client)
    body = {"brief_id": bid, "market": "ZA", "scope": "global", "size": "M", "shoe_size": "38"}
    tight = client.post("/api/compose", json={**body, "overrides": {"budget": {"amount": 500, "currency": "ZAR"}}}).json()
    assert tight["look"]["budget_local"] == 500
    assert tight["brief"]["budget"]["amount"] == 500


def test_mirror_reads_the_brief_once(client):
    d = client.post("/api/mirror", json={"text": THANDI, "markets": ["ZA", "US", "CN"]}).json()
    assert len(d["shoppers"]) == 3
    assert [c["step"] for c in d["calls"]] == ["brief"]
    assert {s["brief"]["location"] for s in d["shoppers"]} == {"Cape Town", "New York", "Shenzhen"}


def test_why_on_tap(client):
    d = look(client)
    w = client.post(f"/api/why/{d['look_id']}").json()
    assert w["provider"] == "template" and w["why"]
