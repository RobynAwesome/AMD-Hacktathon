"""Offline tests for provider routing, prize locks and request shapes. No network."""

from types import SimpleNamespace

import pytest

from goa import llm


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ["GOA_PROVIDER", "GOA_MODE", "TOKEN_FACTORY_BASE_URL", "TOKEN_FACTORY_API_KEY", "GEMMA_MODEL"]:
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
    with pytest.raises(llm.LLMConfigError, match="base URL"):
        llm.chat("brief", [{"role": "user", "content": "hi"}])


def test_openai_compat_request_shape(monkeypatch):
    monkeypatch.setenv("TOKEN_FACTORY_BASE_URL", "https://tf.example.com/v1")
    monkeypatch.setenv("TOKEN_FACTORY_API_KEY", "k")
    sent = {}

    def fake_post(url, json, headers, timeout):
        sent.update(url=url, body=json, headers=headers)
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None,
                               json=lambda: {"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    reply = llm.chat("vision", [{"role": "user", "content": "tag"}], images=[llm.Image(b"png", "image/png")])
    parts = sent["body"]["messages"][-1]["content"]
    assert sent["url"] == "https://tf.example.com/v1/chat/completions"
    assert sent["headers"]["Authorization"] == "Bearer k"
    assert parts[0] == {"type": "text", "text": "tag"}
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert reply.provider == "token_factory" and reply.step == "vision"


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
    assert llm._anthropic(r, msgs, True, [], 10, client=client("end_turn")) == "ok"
    with pytest.raises(RuntimeError):
        llm._anthropic(r, msgs, True, [], 10, client=client("refusal"))
