"""How often is the true medicine among the candidates for a pack crop without a readable code?

  .venv-app/Scripts/python.exe experiments/candidates_eval.py [N=12] [meta|local]

Takes crops with known ground truth from experiments/out/crops/crops.json (made by sam3_box_crops.py), asks the model what is
printed, searches CIMA and reports whether the true medicine is the first candidate or within the first four.
The crops are cut from the official CIMA photos composed into synthetic scenes, so this says how well the text reading plus
CIMA search work, not how real photos behave. The caregiver still confirms every pick.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
from medtable import candidates  # noqa: E402
from medtable.resolve import Resolver  # noqa: E402

n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
backend = sys.argv[2] if len(sys.argv) > 2 else None
rows = [r for r in json.loads(Path("experiments/out/crops/crops.json").read_text(encoding="utf-8")) if r["gt_nregistro"] and (r["visible_frac"] or 0) >= 0.6]
step = max(len(rows) // n, 1)
sample = rows[::step][:n]
resolver = Resolver("data/cache/cima")
top1 = top4 = empty = 0
for r in sample:
    try:
        proposal = candidates.propose(Path(r["crop"]), resolver, backend, consent=True)   # public CIMA photo crops only
    except Exception as exc:  # noqa: BLE001
        print("ERR", Path(r["crop"]).name, str(exc)[:120])
        continue
    ids = [c.medicine.nregistro for c in proposal.candidates]
    hit1, hit4 = bool(ids) and ids[0] == r["gt_nregistro"], r["gt_nregistro"] in ids
    top1 += hit1
    top4 += hit4
    empty += not ids
    brand = (proposal.read or {}).get("marca")
    print(f"{r['gt_nombre'][:38]:38} read={str(brand)[:22]:22} cn_checked={proposal.cn_checked} top1={hit1} top4={hit4} n={len(ids)}")
print(f"crops {len(sample)}: truth first {top1}, in first four {top4}, no candidates {empty}")
