"""Candidates for packs without a readable code: SAM boxes, model reading as a query, CIMA search, ranking."""

from pathlib import Path

from fixtures import METFORMINA_850, OMEPRAZOL, med, strength
from medtable import candidates, cima, cn, vlm
from medtable.candidates import Box, boxes_without_code, propose
from medtable.decode import Detection
from medtable.meta_api import Reply
from medtable.resolve import Resolver


def test_boxes_with_a_decoded_code_inside_are_not_reported():
    boxes = [Box(Path("a.jpg"), (0, 0, 100, 100), 0.9), Box(Path("b.jpg"), (200, 0, 300, 100), 0.9)]
    detections = [Detection("(01)...", (40, 40, 60, 60), "zxing")]
    assert [b.crop.name for b in boxes_without_code(boxes, detections)] == ["b.jpg"]
    assert len(boxes_without_code(boxes, [])) == 2


def test_scoring_uses_brand_ingredient_and_dose():
    read = {"marca": "Metformina Delta", "principio_activo": "metformina", "dosis": "850 mg"}
    best = candidates.score_candidate(METFORMINA_850, read)
    assert best.score == 5 and len(best.why) == 3
    assert candidates.score_candidate(OMEPRAZOL, read).score == 0


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


def test_a_cn_read_by_the_model_does_not_outrank_a_name_match_and_is_labelled_as_a_model_reading(monkeypatch, tmp_path):
    omeprazol_cn7 = f"690001{cn.check_digit('690001')}"
    reply = ('{"marca": "Metformina Delta", "principio_activo": "metformina", "dosis": "850 mg", "codigo_nacional": "%s"}' % omeprazol_cn7)
    fake_world(monkeypatch, reply, [{"nregistro": METFORMINA_850.nregistro}])
    proposal = propose(tmp_path / "crop.jpg", Resolver(tmp_path))
    assert [c.medicine.cn for c in proposal.candidates] == ["680001", "690001"]  # brand + ingredient + dose beat a model-read code
    assert "lo ha leído un modelo" in proposal.candidates[1].why[0] and "verificado" not in proposal.candidates[1].why[0]


def test_unreadable_reply_and_no_results(monkeypatch, tmp_path):
    fake_world(monkeypatch, "no veo nada", [])
    assert propose(tmp_path / "c.jpg", Resolver(tmp_path)).note.startswith("El modelo no pudo")
    fake_world(monkeypatch, '{"marca": "Inventado", "principio_activo": null, "dosis": null, "codigo_nacional": null}', [])
    assert propose(tmp_path / "c.jpg", Resolver(tmp_path)).note.startswith("No hay candidatos")
