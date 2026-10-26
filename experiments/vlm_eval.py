"""Qwen3.5-9B on (a) SAM crops of the synthetic scenes and (b) the fictional medication sheet.

  .venv-app/Scripts/python.exe experiments/vlm_eval.py crops     # needs experiments/out/crops/crops.json
  .venv-app/Scripts/python.exe experiments/vlm_eval.py sheet     # needs experiments/out/sheet.jpg

Small samples: read the numbers as indications, not metrics. The name check is crude: a hit means the first word of
the CIMA name appears in the brand or active ingredient the model returned.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "src")
from medtable import cima, cn  # noqa: E402
from vlm_client import ask, norm, parse_json  # noqa: E402

OUT = Path("experiments/out")
CROP_PROMPT = ('Esta es la foto recortada de una caja de medicamento espanola. Lee SOLO lo que se ve impreso. '
               'Responde con JSON: {"marca": str|null, "principio_activo": str|null, "dosis": str|null, '
               '"forma": str|null, "codigo_nacional": str|null}. Usa null si no se lee con claridad. No adivines.')
SHEET_PROMPT = ('Esta es la foto de una hoja de plan de medicacion. Extrae TODAS las filas de la tabla como JSON: '
                '[{"medicamento": str, "desayuno": str, "comida": str, "cena": str, "acostarse": str, "observaciones": str}]. '
                'Copia los valores exactamente como estan escritos (por ejemplo "1", "0", "1/2"). Si una celda esta vacia usa "".')


def crops() -> None:
    rows = [r for r in json.load((OUT / "crops/crops.json").open(encoding="utf-8")) if r["gt_nregistro"]]
    cima_cns: dict[str, list[str]] = {}
    tally = {"ok": 0, "abstain": 0, "wrong": 0, "dose": 0, "cn_read": 0, "cn_valid": 0, "cn_in_cima": 0}
    for r in rows:
        text, secs = ask(r["crop"], CROP_PROMPT)
        read = parse_json(text) or {}
        said = norm(f"{read.get('marca')} {read.get('principio_activo')}").replace("none", "").strip()
        first_word = next(iter(re.findall(r"[a-z]{4,}", norm(r["gt_nombre"]))), "")
        numbers = re.findall(r"\d+(?:,\d+)?", r["gt_nombre"])
        status = "ok" if first_word in said else ("abstain" if not said else "wrong")
        dose = bool(numbers) and numbers[0].replace(",", ".") in norm(read.get("dosis")).replace(",", ".")
        tally[status] += 1
        tally["dose"] += dose
        found = cn.find_cn(str(read.get("codigo_nacional") or ""))
        if found:
            tally["cn_read"] += 1
            if cn.is_valid(found):
                tally["cn_valid"] += 1
                if r["gt_nregistro"] not in cima_cns:
                    cima_cns[r["gt_nregistro"]] = [p["cn"] for p in cima.medicine_by_nregistro(r["gt_nregistro"]).get("presentaciones", [])]
                tally["cn_in_cima"] += found[:6] in cima_cns[r["gt_nregistro"]]
        print(f"{status:8} visible={r['visible_frac']:.2f} truth={r['gt_nombre'][:40]:40} | brand={read.get('marca')} "
              f"ingredient={read.get('principio_activo')} dose={read.get('dosis')} cn={read.get('codigo_nacional')} ({secs:.1f}s)")
    print(f"\nCROPS n={len(rows)}: {tally}")


def sheet() -> None:
    truth = json.load((OUT / "sheet_truth.json").open(encoding="utf-8"))
    text, secs = ask(OUT / "sheet.jpg", SHEET_PROMPT, max_tokens=1500)
    got = parse_json(text) or []
    print(f"SHEET ({secs:.1f}s): rows read {len(got)} of {len(truth)}")
    wrong = cells = 0
    for row in truth:
        key = norm(row["medicamento"]).split()[0]
        match = next((g for g in got if key in norm(g.get("medicamento"))), None)
        if not match:
            print("  MISSING row:", row["medicamento"])
            wrong += 4
            cells += 4
            continue
        pauta = [str(match.get(k, "")).strip() for k in ("desayuno", "comida", "cena", "acostarse")]
        bad = sum(a != b for a, b in zip(pauta, row["pauta"]))
        wrong += bad
        cells += 4
        remarks_ok = norm(match.get("observaciones")) == norm(row["observaciones"])
        print(f"  {row['medicamento'][:40]:40} truth={row['pauta']} got={pauta} remarks_exact={remarks_ok}{'  <-- MISMATCH' if bad else ''}")
    print(f"schedule cells wrong: {wrong}/{cells}")


if __name__ == "__main__":
    {"crops": crops, "sheet": sheet}[sys.argv[1]]()
