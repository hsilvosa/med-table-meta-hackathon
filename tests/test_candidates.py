"""Candidates for packs without a readable code: SAM boxes, model reading as a query, CIMA search, ranking."""


from fixtures import METFORMINA_850, OMEPRAZOL
from medtable import cima, cn, vlm
from medtable.candidates import propose
from medtable.meta_api import Reply
from medtable.resolve import Resolver


def fake_world(monkeypatch, reply_text, results):
    monkeypatch.setattr(vlm, "ask_image", lambda *a, **k: Reply(reply_text, {}, 0.0, 0.0))
    monkeypatch.setattr(cima, "get_json", lambda endpoint, **p: {"resultados": results})
    by_nreg = {m.nregistro: m for m in (METFORMINA_850, OMEPRAZOL)}
    monkeypatch.setattr(cima, "medicine_by_nregistro", lambda n: {"presentaciones": [{"cn": by_nreg[n].cn}]})
    monkeypatch.setattr(Resolver, "by_cn", lambda self, c: next((m for m in by_nreg.values() if m.cn == c[:6]), None))


def test_propose_ranks_cima_results_and_never_picks_for_the_user(monkeypatch, tmp_path):
    fake_world(monkeypatch, '{"marca": "Metformina Delta", "principio_activo": "metformina", "dosis": "850 mg", "codigo_nacional": null}',
               [{"nregistro": OMEPRAZOL.nregistro}, {"nregistro": METFORMINA_850.nregistro}])
    proposal = propose(tmp_path / "crop.jpg", Resolver(tmp_path))
    assert [c.medicine.cn for c in proposal.candidates][0] == "680001"
    assert proposal.cn_checked is None and len(proposal.candidates) == 2


def test_a_cn_read_from_the_box_is_used_only_when_check_digit_and_cima_agree(monkeypatch, tmp_path):
    right = cn.check_digit("680001")
    wrong = (right + 1) % 10
    reply = '{{"marca": null, "principio_activo": null, "dosis": null, "codigo_nacional": "680001.{}"}}'
    fake_world(monkeypatch, reply.format(right), [])
    proposal = propose(tmp_path / "crop.jpg", Resolver(tmp_path))
    assert proposal.cn_checked == f"680001{right}" and proposal.candidates[0].medicine.cn == "680001"
    fake_world(monkeypatch, reply.format(wrong), [])
    rejected = propose(tmp_path / "crop.jpg", Resolver(tmp_path))
    assert rejected.cn_checked is None and rejected.candidates == []
