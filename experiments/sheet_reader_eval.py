"""Score `sheet_reader.read_sheet` on the fictional sheet (experiments/out/sheet.jpg, truth in sheet_truth.json).

  .venv-app/Scripts/python.exe experiments/sheet_reader_eval.py [meta|local]

One clean synthetic sheet only: an indication, not a metric. The sheet is fictional, so sending it to the Meta API is fine.
"""

import json
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, "src")
from medtable import sheet_reader  # noqa: E402

OUT = Path("experiments/out")


def norm(text) -> str:
    folded = unicodedata.normalize("NFD", str(text or "").lower())
    return " ".join("".join(c for c in folded if unicodedata.category(c) != "Mn").split())


backend = sys.argv[1] if len(sys.argv) > 1 else None
truth = json.loads((OUT / "sheet_truth.json").read_text(encoding="utf-8"))
reading = sheet_reader.read_sheet(OUT / "sheet.jpg", backend)
print(f"backend={reading.backend} cost=USD {reading.cost_usd:.4f} rows read {len(reading.rows)} of {len(truth)}; problems: {reading.problems}")
wrong_cells = wrong_remarks = missing = 0
for want in truth:
    key = norm(want["medicamento"]).split()[0]
    got = next((r for r in reading.rows if key in norm(r["medicine"])), None)
    if not got:
        missing += 1
        print("  MISSING", want["medicamento"])
        continue
    cells = [got[s] for s in ("breakfast", "lunch", "dinner", "bedtime")]
    bad = sum(a != b for a, b in zip(cells, want["pauta"]))
    wrong_cells += bad
    wrong_remarks += norm(got["remarks"]) != norm(want["observaciones"])
    print(f"  {want['medicamento'][:42]:42} cells {'OK' if not bad else f'{bad} WRONG {cells} vs {want['pauta']}'}; remarks {'OK' if norm(got['remarks']) == norm(want['observaciones']) else repr(got['remarks']) + ' vs ' + repr(want['observaciones'])}")
print(f"missing rows {missing}, wrong schedule cells {wrong_cells}/{4 * len(truth)}, remarks different {wrong_remarks}")
