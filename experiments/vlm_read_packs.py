"""Qwen3.5-9B (local llama-server) reading CIMA pack photos, checked against CIMA.

  .venv-app/Scripts/python.exe experiments/vlm_read_packs.py [--n 8 --seed 7]

For each random pack photo: ask for brand, active ingredient, strength, form and Codigo Nacional; compare with the
CIMA record and test whether the CN passes the check digit AND belongs to that medicine's presentations.
"""

import argparse
import json
import re
import random
import sys
from pathlib import Path

sys.path.insert(0, "src")
from medtable import cima, cn  # noqa: E402
from vlm_client import ask, norm, parse_json  # noqa: E402

PROMPT = ('Esta es la foto de una caja de medicamento espanola. Lee SOLO lo que se ve impreso. '
          'Responde con JSON: {"marca": str|null, "principio_activo": str|null, "dosis": str|null, '
          '"forma": str|null, "codigo_nacional": str|null}. Usa null si no se lee con claridad. No adivines.')

ap = argparse.ArgumentParser()
ap.add_argument("--n", type=int, default=8)
ap.add_argument("--seed", type=int, default=7)
args = ap.parse_args()

meds = [json.loads(line) for line in open("data/cima/manifest.jsonl", encoding="utf-8")]
meds = [m for m in meds if any(f["tipo"] == "materialas" for f in m["fotos"])]
random.Random(args.seed).shuffle(meds)

name_ok = cn_read = cn_good = 0
for med in meds[: args.n]:
    text, secs = ask(Path(f"data/cima/images/full/materialas/{med['nregistro']}.jpg"), PROMPT)
    read = parse_json(text) or {}
    first_word = next(iter(re.findall(r"[a-z]{4,}", norm(med["nombre"]))), "")
    hit = first_word in norm(f"{read.get('marca')} {read.get('principio_activo')}")
    name_ok += hit
    found = cn.find_cn(str(read.get("codigo_nacional") or ""))
    verdict = "no CN read"
    if found:
        cn_read += 1
        known = [p["cn"] for p in cima.medicine_by_nregistro(med["nregistro"]).get("presentaciones", [])]
        if cn.is_valid(found) and found[:6] in known:
            cn_good += 1
            verdict = "CN valid and in CIMA for this medicine"
        else:
            verdict = f"CN REJECTED (check digit ok: {cn.is_valid(found)}, in CIMA: {found[:6] in known})"
    print(f"{med['nombre'][:55]:55} brand/ingredient match={hit}  {verdict}  ({secs:.1f}s)")
print(f"\nname match {name_ok}/{args.n}; CN read {cn_read}, accepted {cn_good}")
