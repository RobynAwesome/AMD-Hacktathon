"""Offline tests for provider routing, prize locks and request shapes. No network."""

from types import SimpleNamespace

import pytest

from goa import llm


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    from goa import usage

    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path / "llm")
    monkeypatch.setattr(usage, "CALLS_LOG", tmp_path / "calls.jsonl")
    monkeypatch.setattr(usage, "USAGE", usage.Usage())
    monkeypatch.delenv("GOA_CACHE_ONLY", raising=False)
    for k in ["GOA_PROVIDER", "GOA_MODE", "TOKEN_FACTORY_BASE_URL", "TOKEN_FACTORY_API_KEY", "RADEON_API_KEY", "GEMMA_MODEL"]:
        monkeypatch.delenv(k, raising=False)
    for s in llm.STEPS:
        monkeypatch.delenv(f"GOA_PROVIDER_{s.upper()}", raising=False)
        monkeypatch.delenv(f"GOA_MODEL_{s.upper()}", raising=False)


def test_default_is_token_factory_everywhere():
    assert {llm.route(s).provider for s in llm.STEPS} == {"token_factory"}
    assert llm.lock_problems() == []


def test_per_step_override(monkeypatch):
    monkeypatch.setenv("GOA_PROVIDER_IDEAS", "anthropic")
    monkeypatch.setenv("GOA_MODEL_BRIEF", "gemma-x")
    assert llm.route("ideas").provider == "anthropic"
    assert llm.route("ideas").model == "claude-opus-5-5"
    assert llm.route("brief").model == "gemma-x"
    assert llm.lock_problems() == []  # ideas is not prize-locked


def test_submission_mode_refuses_locked_step(monkeypatch):
    monkeypatch.setenv("GOA_MODE", "submission")
    monkeypatch.setenv("GOA_PROVIDER_BRIEF", "openrouter")
    with pytest.raises(llm.LLMConfigError, match="AMD"):
        llm.check_submission()


def test_dev_mode_warns(monkeypatch, capsys):
    monkeypatch.setenv("GOA_PROVIDER", "ai_studio")
    llm.check_submission()
    assert "warning: brief" in capsys.readouterr().err


def test_missing_key_is_clear():
    with pytest.raises(llm.LLMConfigError, match="TOKEN_FACTORY_API_KEY"):
        llm.chat("brief", [{"role": "user", "content": "hi"}])


def test_openai_compat_request_shape(monkeypatch):
    monkeypatch.setenv("TOKEN_FACTORY_BASE_URL", "https://tf.example.com/v1")
    monkeypatch.setenv("TOKEN_FACTORY_API_KEY", "k")
    sent = {}

    def fake_post(url, json, headers, timeout):
        sent.update(url=url, body=json, headers=headers)
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None, headers={},
                               json=lambda: {"choices": [{"message": {"content": "{}"}}],
                                             "usage": {"prompt_tokens": 12, "completion_tokens": 3}})

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    reply = llm.chat("vision", [{"role": "user", "content": "tag"}], images=[llm.Image(b"png", "image/png")])
    parts = sent["body"]["messages"][-1]["content"]
    assert sent["url"] == "https://tf.example.com/v1/chat/completions"
    assert sent["headers"]["Authorization"] == "Bearer k"
    assert parts[0] == {"type": "text", "text": "tag"}
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert reply.provider == "token_factory" and reply.step == "vision"
    assert sent["body"]["max_tokens"] == llm.MAX_TOKENS["vision"]


def test_anthropic_request_shape():
    r = llm.Route("vision", "anthropic", "anthropic", "claude-opus-5-5", "", "k")
    req = llm._anthropic_request(
        r, [{"role": "system", "content": "be brief"}, {"role": "user", "content": "tag"}], [llm.Image(b"png", "image/png")]
    )
    assert req["system"] == "be brief"
    assert all(m["role"] != "system" for m in req["messages"])
    blocks = req["messages"][-1]["content"]
    assert blocks[0]["type"] == "image" and blocks[0]["source"]["media_type"] == "image/png"
    assert blocks[-1] == {"type": "text", "text": "tag"}
    assert "temperature" not in req


def test_anthropic_adapter_reads_text_and_refusal():
    r = llm.Route("ideas", "anthropic", "anthropic", "claude-opus-5-5", "", "k")

    def client(stop):
        create = lambda **kw: SimpleNamespace(  # noqa: E731
            stop_reason=stop, content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text="ok")])
        return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))

    msgs = [{"role": "user", "content": "x"}]
    assert llm._anthropic(r, msgs, True, [], 10, client=client("end_turn"))[0] == "ok"
    with pytest.raises(RuntimeError):
        llm._anthropic(r, msgs, True, [], 10, client=client("refusal"))


def _fake_tf(monkeypatch, calls, headers=None, content="{}"):
    monkeypatch.setenv("TOKEN_FACTORY_API_KEY", "k")

    def fake_post(url, json, headers_, timeout):  # noqa: ARG001
        calls.append(json)
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None, headers=headers or {},
                               json=lambda: {"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(llm.httpx, "post", lambda url, json, headers, timeout: fake_post(url, json, headers, timeout))


def test_cache_hit_makes_no_network_call(monkeypatch):
    calls = []
    _fake_tf(monkeypatch, calls)
    msgs = [{"role": "user", "content": "ideas please"}]
    first = llm.chat("ideas", msgs)
    second = llm.chat("ideas", msgs)
    assert len(calls) == 1 and not first.cached and second.cached


def test_unparseable_json_is_not_cached(monkeypatch):
    calls = []
    _fake_tf(monkeypatch, calls, content="not json")
    msgs = [{"role": "user", "content": "x"}]
    llm.chat("ideas", msgs)
    llm.chat("ideas", msgs)
    assert len(calls) == 2


def test_guard_levels_from_headers(monkeypatch):
    from goa import usage

    calls = []
    _fake_tf(monkeypatch, calls, headers={"X-RateLimit-Limit-Spend": "10", "X-RateLimit-Remaining-Spend": "2"})
    llm.chat("brief", [{"role": "user", "content": "a"}], use_cache=False)  # sees 20% remaining
    assert usage.guard_level() == "essential"
    with pytest.raises(llm.LLMUnavailable):
        llm.chat("explain", [{"role": "user", "content": "b"}])
    llm.chat("enquiry", [{"role": "user", "content": "c"}], json_mode=False)  # essential still runs
    usage.USAGE.remaining = 0.5  # 5% remaining
    assert usage.guard_level() == "cache_only"
    with pytest.raises(llm.LLMUnavailable):
        llm.chat("brief", [{"role": "user", "content": "d"}], use_cache=False)


def test_cache_only_env_blocks_live_calls(monkeypatch):
    calls = []
    _fake_tf(monkeypatch, calls)
    monkeypatch.setenv("GOA_CACHE_ONLY", "1")
    with pytest.raises(llm.LLMUnavailable):
        llm.chat("ideas", [{"role": "user", "content": "x"}])
    assert calls == []


def test_usage_endpoint_parsing():
    from goa import usage

    u = usage.Usage()
    u.update_from_usage({"data": {"total_quota": 5.0, "used": 4.0, "reset_at": "2026-10-19T00:00:00Z", "rpm_limit": 30}})
    assert u.fraction_remaining() == pytest.approx(0.2) and u.rpm == "30"


def test_rate_limiter_never_exceeds_per_minute():
    from goa.usage import RateLimiter

    t = [0.0]
    lim = RateLimiter(15, 4, clock=lambda: t[0], sleep=lambda s: t.__setitem__(0, t[0] + s))
    starts = []
    for _ in range(40):
        lim.acquire()
        starts.append(t[0])
        lim.release()
    for i, s in enumerate(starts):
        assert sum(1 for x in starts if s <= x < s + 60) <= 15


def test_token_factory_usage_fields():
    """Field names exactly as Token Factory's GET /v1/usage returned them on the first live run."""
    from goa import usage

    u = usage.Usage()
    before = usage.LIMITER.per_minute
    u.update_from_usage({"daily_cost_limit_usd": 5.0, "daily_cost_used_usd": 1.0, "daily_cost_remaining_usd": 4.0,
                         "daily_reset_at": "2026-10-19T00:00:00+08:00", "daily_reset_timezone": "Asia/Shanghai",
                         "rpm_limit": 20, "today": {"requests": 3}})
    assert u.fraction_remaining() == pytest.approx(0.8)
    assert "Asia/Shanghai" in u.reset and u.rpm == "20"
    assert usage.LIMITER.per_minute <= 15
    usage.LIMITER.per_minute = before


def test_timeout_is_retried_once_then_clear(monkeypatch):
    monkeypatch.setenv("TOKEN_FACTORY_API_KEY", "k")
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    tries = []

    def slow(url, json, headers, timeout):
        tries.append(1)
        raise llm.httpx.ReadTimeout("slow")

    monkeypatch.setattr(llm.httpx, "post", slow)
    with pytest.raises(llm.LLMTimeout, match="did not answer"):
        llm.chat("brief", [{"role": "user", "content": "x"}], use_cache=False)
    assert len(tries) == 2


def test_json_mode_can_be_switched_off(monkeypatch):
    calls = []
    _fake_tf(monkeypatch, calls)
    monkeypatch.setenv("GOA_JSON_MODE", "0")
    llm.chat("ideas", [{"role": "user", "content": "x"}], use_cache=False)
    assert "response_format" not in calls[0]
