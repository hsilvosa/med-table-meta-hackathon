"""Build a calendar PDF from REAL CIMA data already in the local cache (no model, no network if cached).

  .venv-app/Scripts/python.exe experiments/demo_real_plan.py   ->  experiments/out/real_plan.pdf and real_plan_p<n>.png

Medicines: Sintrom 1 mg, Paracetamol Cinfa 1 g, Gelocatil 1 g, Enalapril Cinfa 10 mg (CN 654177, 662025, 715240, 677379). The doses are
invented for the demo. Shows how the findings and the quotes from SmPC 4.5 / 4.2 look on paper.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, "src")
from medtable.calendar_pdf import render_pdf  # noqa: E402
from medtable.plan import build_plan  # noqa: E402
from medtable.resolve import Resolver  # noqa: E402
from medtable.rules import Pack, check_packs, meal_notes  # noqa: E402
from medtable.schedule import SLOTS, Line, reconcile  # noqa: E402
from medtable.smpc import Smpc  # noqa: E402

today = date(2026, 10, 26)
resolver, smpc = Resolver("data/cache/cima"), Smpc("data/cache/smpc")
packs = [Pack(resolver.by_cn(cn), "verified", date(2028, 1, 1)) for cn in ("654177", "662025", "715240", "677379")]


def line(text, remarks="", **doses):
    return Line(text, {**dict.fromkeys(SLOTS, "0"), **doses}, remarks, confirmed=True)


lines = [line("Sintrom 1 mg", "según pauta de hematología", cena="1/2"), line("Paracetamol Cinfa 1 g", "cada 8 h si dolor", desayuno="1", cena="1"),
         line("Enalapril 10 mg", desayuno="1")]
recon = reconcile(lines, packs)
plan = build_plan(lines, recon, check_packs(packs, smpc, today) + meal_notes(packs, smpc) + recon.findings, today)
out = render_pdf(plan, Path("experiments/out/real_plan.pdf"), "Paciente de ejemplo")
try:
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(out))
    for i in range(len(doc)):
        doc[i].render(scale=1.3).to_pil().save(Path("experiments/out") / f"real_plan_p{i + 1}.png")
except ImportError:
    pass
print(out)
