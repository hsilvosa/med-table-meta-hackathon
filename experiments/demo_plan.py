"""Build a demo calendar PDF from the invented medicines in tests/fixtures.py (no network, no real data).

  .venv-app/Scripts/python.exe experiments/demo_plan.py   ->  experiments/out/demo_plan.pdf (+ .ics, + .png if pypdfium2 is installed)
"""

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, "src")
sys.path.insert(0, "tests")
from fixtures import (ACENOCUMAROL, FakeSmpc, IBUPROFENO, LORAZEPAM, METFORMINA_850, OMEPRAZOL, TODAY, pack)  # noqa: E402
from medtable.calendar_pdf import render_pdf  # noqa: E402
from medtable.plan import build_plan, speech_text, to_ics  # noqa: E402
from medtable.rules import check_packs, meal_notes  # noqa: E402
from medtable.schedule import SLOTS, Line, reconcile  # noqa: E402


def line(text, remarks, **doses):
    return Line(text, {**dict.fromkeys(SLOTS, "0"), **doses}, remarks, confirmed=True)


lines = [line("Metformina 850 mg", "con las comidas", desayuno="1", cena="1"), line("Omeprazol 20 mg", "30 min antes del desayuno", desayuno="1"),
         line("Lorazepam 1 mg", "solo si insomnio", acostarse="1/2"), line("Atorvastatina 20 mg", "", cena="1")]
packs = [pack(METFORMINA_850), pack(OMEPRAZOL), pack(LORAZEPAM, TODAY - timedelta(days=5)), pack(IBUPROFENO), pack(ACENOCUMAROL)]
recon = reconcile(lines, packs)
plan = build_plan(lines, recon, check_packs(packs, FakeSmpc(), TODAY) + meal_notes(packs, FakeSmpc()) + recon.findings, TODAY)
out = Path("experiments/out")
pdf = render_pdf(plan, out / "demo_plan.pdf", "Paciente de ejemplo")
(out / "demo_plan.ics").write_text(to_ics(plan, days=30), encoding="utf-8", newline="")
print(pdf, "\n" + speech_text(plan, "desayuno"))
try:
    import pypdfium2 as pdfium
    pdfium.PdfDocument(str(pdf))[0].render(scale=1.3).to_pil().save(out / "demo_plan.png")
except ImportError:
    pass
