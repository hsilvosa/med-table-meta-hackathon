"""The models: Meta only with consent, under the spending cap, standard tier, no token in the logs; a model only proposes, never identifies."""

import io
import json

import pytest
from fixtures import METFORMINA_850, OMEPRAZOL

from medtable import candidates, cima, cn, meta_api, sheet_reader, vlm
from medtable.resolve import Resolver

SECRET = "tok-SECRET-123456"
MESSAGES = [{"role": "user", "content": "hola"}]


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

    def fake_urlopen(request, timeout=0):
        sent.append(request)
        return FakeResponse(json.dumps({"choices": [{"message": {"content": "hola"}}], "usage": {"prompt_tokens": 1000, "completion_tokens": 100}}).encode())
    monkeypatch.setattr(meta_api.urllib.request, "urlopen", fake_urlopen)
    return sent, tmp_path / "ledger.jsonl"


def test_a_call_is_logged_with_its_cost_and_the_token_never_reaches_the_log(api):
    sent, ledger = api
    reply = meta_api.chat(MESSAGES, note="test")
    assert reply.cost_usd == pytest.approx((1000 * 1.25 + 100 * 4.25) / 1e6)
    assert SECRET not in ledger.read_text(encoding="utf-8") and sent[0].headers["Authorization"] == f"Bearer {SECRET}"


def test_over_the_cap_or_on_a_training_tier_nothing_is_sent(api):
    sent, ledger = api
    with pytest.raises(ValueError):
        meta_api.chat(MESSAGES, model="muse-spark-1.3-contributor")
    ledger.write_text(json.dumps({"cost_usd": 89.999}) + "\n", encoding="utf-8")
    with pytest.raises(meta_api.BudgetExceeded):
        meta_api.chat(MESSAGES, max_tokens=4000)
    assert sent == []


def test_an_image_is_never_sent_to_meta_without_consent_whoever_calls(monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(meta_api, "ask_image", lambda *a, **k: sent.append(a) or meta_api.Reply("{}", {}, 0.0, 0.0))
    (tmp_path / "x.jpg").write_bytes(b"not sent")
    for call in (lambda: sheet_reader.read_sheet(tmp_path / "x.jpg", backend="meta"),
                 lambda: candidates.propose(tmp_path / "x.jpg", Resolver(tmp_path), backend="meta"),
                 lambda: vlm.ask_image(tmp_path / "x.jpg", "read", backend="meta", consent="yes")):     # only True counts
        with pytest.raises(vlm.ConsentRequired):
            call()
    assert sent == []
    vlm.ask_image(tmp_path / "x.jpg", "read", backend="meta", consent=True)
    assert len(sent) == 1


def test_a_model_only_proposes_and_its_national_code_counts_only_if_check_digit_and_cima_agree(monkeypatch, tmp_path):
    def world(reply, results):
        monkeypatch.setattr(vlm, "ask_image", lambda *a, **k: meta_api.Reply(reply, {}, 0.0, 0.0))
        monkeypatch.setattr(cima, "get_json", lambda endpoint, **p: {"resultados": results})
        by_nreg = {m.nregistro: m for m in (METFORMINA_850, OMEPRAZOL)}
        monkeypatch.setattr(cima, "medicine_by_nregistro", lambda n: {"presentaciones": [{"cn": by_nreg[n].cn}]})
        monkeypatch.setattr(Resolver, "by_cn", lambda self, c: next((m for m in by_nreg.values() if m.cn == c[:6]), None))
        return candidates.propose(tmp_path / "crop.jpg", Resolver(tmp_path))
    proposal = world('{"marca": "Metformina Delta", "principio_activo": "metformina", "dosis": "850 mg", "codigo_nacional": null}',
                     [{"nregistro": OMEPRAZOL.nregistro}, {"nregistro": METFORMINA_850.nregistro}])
    assert [c.medicine.cn for c in proposal.candidates] == ["680001", "690001"] and proposal.cn_checked is None      # a ranked list for the caregiver
    right = cn.check_digit("680001")
    code = '{{"marca": null, "principio_activo": null, "dosis": null, "codigo_nacional": "680001.{}"}}'
    assert world(code.format(right), []).cn_checked == f"680001{right}"
    wrong = world(code.format((right + 1) % 10), [])
    assert wrong.cn_checked is None and wrong.candidates == []
