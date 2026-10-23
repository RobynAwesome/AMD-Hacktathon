"""Release failure boundaries. No credentials or live inference needed."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from goa import deadline, gaps, llm, narrate, usage
from goa.brief import THANDI
from app import main


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("GOA_CACHE_ONLY", "1")
    monkeypatch.setenv("GOA_MODE", "submission")
    monkeypatch.setenv("GOA_ALLOW_SAMPLE", "1")
    monkeypatch.delenv("VERCEL", raising=False)
    for key in ["TOKEN_FACTORY_API_KEY", "RADEON_API_KEY", "TOKEN_FACTORY_BASE_URL", "GEMMA_MODEL", "GOA_PROVIDER"]:
        monkeypatch.delenv(key, raising=False)
    for step in llm.STEPS:
        monkeypatch.delenv(f"GOA_PROVIDER_{step.upper()}", raising=False)
        monkeypatch.delenv(f"GOA_MODEL_{step.upper()}", raising=False)
    monkeypatch.setattr(narrate, "ENQUIRIES_LOG", tmp_path / "enquiries.jsonl")
    monkeypatch.setattr(gaps, "GAPS_LOG", tmp_path / "gaps.jsonl")
    monkeypatch.setattr(main.C, "GAPS_LOG", tmp_path / "gaps.jsonl")
    monkeypatch.setattr(main, "BRIEFS", {})
    monkeypatch.setattr(main, "LOOKS", {})
    with TestClient(main.app) as c:
        yield c


def build(client):
    b = client.post("/api/brief", json={"text": THANDI, "market": "ZA"}).json()
    cd = {"brief_id": b["brief_id"], "brief": b["brief"], "sample": b["sample"],
          "market": "ZA", "scope": "global", "size": "M", "shoe_size": "38"}
    main.BRIEFS.clear()  # Another function instance has no brief-id memory.
    response = client.post("/api/compose", json=cd)
    assert response.status_code == 200
    c = response.json()
    assert c["sample"] == b["sample"]
    main.LOOKS.clear()  # Enquiry must reconstruct the look without process memory.
    return {"look_id": c["look_id"], "brief": c["brief"], "compose": cd,
            "chosen": c["look"]["chosen"], "name": "Alice synthetic release test"}


def test_cold_post_journey_has_explicit_transient_outcome(client):
    payload = build(client)
    response = client.post("/api/enquiry", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["delivered"] is False and data["persistence"] == "transient_instance"
    assert data["enquiries"] and all("temporary demo inbox" in q["status"] for q in data["enquiries"])
    assert all(q["message_source"] == "template" for q in data["enquiries"])
    assert all(q["model_error"] == "quota_or_cache_only" for q in data["enquiries"])
    assert client.get("/api/enquiries").json()
    assert response.headers["X-GOA-Persistence"] == "transient-instance"


def test_failed_inbox_write_is_not_reported_as_sent(client, monkeypatch, tmp_path):
    payload = build(client)
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("x")
    monkeypatch.setattr(narrate, "ENQUIRIES_LOG", blocked / "enquiries.jsonl")
    response = client.post("/api/enquiry", json=payload)
    assert response.status_code == 503
    assert "Nothing was delivered" in response.json()["detail"]
    assert "enquiries" not in response.json()


def test_seed_gaps_are_labelled_separately(client, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    rows = client.get("/api/gaps").json()
    assert len(rows) == 12
    assert {r["source"] for r in rows} == {"synthetic_seed"}
    # A logged demo gap replaces the seed fallback on this instance.
    gaps.GAPS_LOG.write_text(gaps.SEED_GAPS.read_text().splitlines()[0] + "\n")
    rows = client.get("/api/gaps").json()
    assert rows and {r["source"] for r in rows} == {"transient_demo"}


def test_vercel_does_not_enable_heuristics_without_opt_in(client, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("GOA_ALLOW_SAMPLE")
    response = client.post("/api/brief", json={"text": "An uncached synthetic interview outfit in blue."})
    assert response.status_code == 503
    monkeypatch.setenv("GOA_ALLOW_SAMPLE", "1")
    data = client.post("/api/brief", json={"text": "An uncached synthetic interview outfit in blue."}).json()
    assert data["sample"] and data["calls"][0]["provider"].startswith("heuristic")
    assert data["calls"][0]["error"] == "quota_or_cache_only"


@pytest.mark.parametrize("key,value", [
    ("GOA_MODEL_BRIEF", "not-gemma"),
    ("TOKEN_FACTORY_BASE_URL", "https://example.com/v1"),
    ("GOA_PROVIDER_ENQUIRY", "openrouter"),
])
def test_submission_rejects_provider_model_and_endpoint(client, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(llm.LLMConfigError):
        llm.check_submission()
    # Even a seeded cache or enabled fallback must not mask a broken submission route.
    response = client.post("/api/brief", json={"text": THANDI})
    assert response.status_code == 503


def test_failure_metadata_does_not_echo_provider_secrets(client, monkeypatch):
    monkeypatch.setattr(main, "parse_brief", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("secret-key-and-provider-body")))
    response = client.post("/api/brief", json={"text": THANDI})
    assert response.status_code == 200
    assert "secret-key-and-provider-body" not in response.text
    assert response.json()["calls"][0]["error"] == "provider_or_parse_failure"


def test_provider_http_error_is_distinct_from_live_success(client, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("GOA_CACHE_ONLY", "0")
    monkeypatch.setenv("TOKEN_FACTORY_API_KEY", "synthetic-test-key")

    async def rejected(url, body, headers, timeout):
        return llm.httpx.Response(401, request=llm.httpx.Request("POST", url),
                                  text="secret provider response")

    monkeypatch.setattr(llm, "_bounded_post", rejected)
    response = client.post("/api/brief", json={"text": "Uncached synthetic blue interview look release HTTP test."})
    assert response.status_code == 200
    assert response.json()["sample"] is True
    assert response.json()["calls"][0]["error"] == "provider_http_401"
    assert "synthetic-test-key" not in response.text
    assert "secret provider response" not in response.text


def test_async_transport_is_cancelled_at_shared_deadline(monkeypatch):
    cancelled = []

    class Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, *args, **kwargs):
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.append(True)

    monkeypatch.setattr(llm.httpx, "AsyncClient", Client)
    with deadline.budget(0.02), pytest.raises(llm.LLMTimeout):
        asyncio.run(llm._bounded_post("https://example.com", {}, {}, 180))
    assert cancelled == [True]


def test_retry_after_cannot_outlive_request_budget(monkeypatch):
    calls = []

    async def throttled(*args):
        calls.append(True)
        return SimpleNamespace(status_code=429, headers={"retry-after": "120"})

    monkeypatch.setattr(llm, "_bounded_post", throttled)
    with deadline.budget(0.1), pytest.raises(llm.LLMTimeout):
        llm._post_with_backoff("https://example.com", {}, {}, 180)
    assert len(calls) == 1


def test_limiter_timeout_releases_slot():
    limiter = usage.RateLimiter(1, 1)
    limiter.acquire()
    limiter.release()
    with pytest.raises(TimeoutError):
        limiter.acquire(timeout=0.01)
    limiter.starts.clear()
    limiter.acquire(timeout=0.01)
    limiter.release()


def test_limiter_budget_includes_time_waiting_for_a_slot():
    clock = [0.0]
    limiter = usage.RateLimiter(1, 1, clock=lambda: clock[0])
    limiter.starts.append(0)

    class Slot:
        def acquire(self, timeout):
            clock[0] += 30  # Slot contention consumed most of the 40s budget.
            return True

        def release(self):
            pass

    limiter.slots = Slot()
    with pytest.raises(TimeoutError):
        limiter.acquire(timeout=40)


def test_budget_is_shared_across_model_steps():
    with deadline.budget(1):
        first = deadline.remaining()
        assert deadline.remaining(180) <= first
    assert deadline.remaining() is None
