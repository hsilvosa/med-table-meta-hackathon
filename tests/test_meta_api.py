"""Meta client: spending cap, model allow-list, ledger and secrecy. No network: urlopen is replaced."""

import io
import json

import pytest

from medtable import meta_api

SECRET = "tok-SECRET-123456"


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(meta_api, "LEDGER", tmp_path / "ledger.jsonl")
    monkeypatch.setenv("META_TOKEN", SECRET)
    monkeypatch.setenv("META_BUDGET_USD", "100")
    sent = []

    def respond(usage):
        def fake_urlopen(request, timeout=0):
            sent.append(request)
            return FakeResponse(json.dumps({"choices": [{"message": {"content": "hola"}}], **({"usage": usage} if usage is not None else {})}).encode())
        monkeypatch.setattr(meta_api.urllib.request, "urlopen", fake_urlopen)
    return respond, sent, tmp_path / "ledger.jsonl"


MESSAGES = [{"role": "user", "content": "hola"}]


def test_a_call_is_logged_with_its_cost_and_never_contains_the_token(api):
    respond, sent, ledger = api
    respond({"prompt_tokens": 1000, "completion_tokens": 100})
    reply = meta_api.chat(MESSAGES, note="test")
    assert reply.text == "hola" and reply.cost_usd == pytest.approx((1000 * 1.25 + 100 * 4.25) / 1e6)
    assert SECRET not in ledger.read_text(encoding="utf-8")
    assert sent[0].headers["Authorization"] == f"Bearer {SECRET}"  # only in the header


def test_a_reply_without_usage_is_not_recorded_as_free(api):
    respond, _, ledger = api
    respond(None)
    reply = meta_api.chat(MESSAGES)
    assert reply.cost_usd == meta_api.UNKNOWN_USAGE_COST_USD > 0
    assert meta_api.spent_usd(ledger) == meta_api.UNKNOWN_USAGE_COST_USD


def test_calls_are_refused_when_they_could_pass_the_cap(api, monkeypatch):
    respond, sent, ledger = api
    respond({"prompt_tokens": 10, "completion_tokens": 1})
    ledger.write_text(json.dumps({"cost_usd": 89.999}) + "\n", encoding="utf-8")
    with pytest.raises(meta_api.BudgetExceeded):
        meta_api.chat(MESSAGES, max_tokens=4000)
    assert sent == []  # refused before any request left the machine


def test_contributor_models_are_refused(api):
    respond, sent, _ = api
    respond({})
    with pytest.raises(ValueError):
        meta_api.chat(MESSAGES, model="muse-spark-1.3-contributor")
    assert sent == []


def test_a_missing_token_error_does_not_leak_anything(monkeypatch):
    monkeypatch.delenv("META_TOKEN", raising=False)
    monkeypatch.setattr(meta_api, "load_env", lambda *a, **k: None)
    with pytest.raises(meta_api.MetaAPIError) as error:
        meta_api._token()
    assert "META_TOKEN is empty" in str(error.value)
