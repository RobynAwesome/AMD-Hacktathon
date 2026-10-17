"""Offline tests for brief parsing. A stub stands in for Gemma and returns replies we wrote."""

import json
from datetime import date

import pytest

from goa.brief import BriefError, parse_brief
from goa.llm import LLMReply

TODAY = date(2026, 10, 17)

GOOD = {
    "occasion": "graduation",
    "event_date": "2026-12-12",
    "location": "Cape Town",
    "market": "ZA",
    "setting": "outdoor",
    "weather": "warm",
    "budget": {"amount": 2500, "currency": "ZAR", "soft": False},
    "size": None,
    "shoe_size": None,
    "colours": ["green"],
    "formality": "smart_casual",
    "style_notes": ["elegant but not formal", "rewearable"],
    "constraints": [],
    "parts": [
        {"slot": "garment", "description": "green midi dress", "colours": ["green"], "materials": []},
        {"slot": "shoes", "description": "block heels for grass", "colours": [], "materials": []},
    ],
}


def stub(*replies):
    calls = []

    def chat(messages):
        calls.append(messages)
        return LLMReply(text=replies[len(calls) - 1], latency_ms=10, model="stub", base_url="stub")

    chat.calls = calls
    return chat


def run(chat):
    return parse_brief("anything", market="ZA", today=TODAY, chat_fn=chat, use_cache=False)


def test_valid_first_attempt():
    res = run(stub(json.dumps(GOOD)))
    assert res.attempts == 1
    assert res.brief.budget.amount == 2500


def test_retry_recovers_and_sends_error_back():
    chat = stub("not json at all", "```json\n" + json.dumps(GOOD) + "\n```")
    res = run(chat)
    assert res.attempts == 2
    assert "failed validation" in chat.calls[1][-1]["content"]


def test_two_failures_raise():
    with pytest.raises(BriefError):
        run(stub("{}", "{}"))


def test_missing_size_stays_null():
    res = run(stub(json.dumps(GOOD)))
    assert res.brief.size is None and res.brief.shoe_size is None


def test_past_date_rejected():
    bad = dict(GOOD, event_date="2025-12-12")
    with pytest.raises(BriefError):
        run(stub(json.dumps(bad), json.dumps(bad)))


def test_two_garments_rejected():
    bad = dict(GOOD, parts=GOOD["parts"] + [{"slot": "garment", "description": "suit"}])
    with pytest.raises(BriefError):
        run(stub(json.dumps(bad), json.dumps(bad)))


def test_no_garment_allowed():
    ok = dict(GOOD, parts=[GOOD["parts"][1]])
    assert run(stub(json.dumps(ok))).attempts == 1
