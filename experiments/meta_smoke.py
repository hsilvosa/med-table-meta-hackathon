"""Smoke test of the Meta Model API client: connectivity, one CIMA pack photo, the fictional medication sheet.

  .venv-app/Scripts/python.exe experiments/meta_smoke.py

Three calls, a few cents at most. Sends only public data (a CIMA photo) and a fictional sheet. Prints the
answers, token usage and cost per call, and the running total from the ledger.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
from medtable import meta_api  # noqa: E402

PACK_PROMPT = ('Esta es la foto de una caja de medicamento espanola. Lee SOLO lo que se ve impreso. '
               'Responde con JSON: {"marca": str|null, "principio_activo": str|null, "dosis": str|null, '
               '"forma": str|null, "codigo_nacional": str|null}. Usa null si no se lee con claridad. No adivines.')
SHEET_PROMPT = ('Esta es la foto de una hoja de plan de medicacion. Extrae TODAS las filas de la tabla como JSON: '
                '[{"medicamento": str, "desayuno": str, "comida": str, "cena": str, "acostarse": str, "observaciones": str}]. '
                'Copia los valores exactamente como estan escritos (por ejemplo "1", "0", "1/2"). Si una celda esta vacia usa "".')


def show(label: str, reply: meta_api.Reply) -> None:
    print(f"--- {label}: {reply.seconds:.1f}s, cost ${reply.cost_usd:.5f}, usage {json.dumps(reply.usage)}")
    print(reply.text.strip()[:700])


print(f"budget ${meta_api.budget_usd():.2f}, spent so far ${meta_api.spent_usd():.4f}")
show("ping", meta_api.chat([{"role": "user", "content": "Reply with the single word: ready"}], max_tokens=20, note="ping"))
# Spiriva Respimat (nregistro 77068 in the earlier sample): any CIMA pack photo works; take the first one on disk
pack = sorted(Path("data/cima/images/full/materialas").glob("*.jpg"))[0]
show(f"pack photo {pack.name}", meta_api.ask_image(pack, PACK_PROMPT, note="pack"))
sheet = Path("experiments/out/sheet.jpg")
if sheet.exists():
    show("fictional sheet", meta_api.ask_image(sheet, SHEET_PROMPT, max_tokens=1200, note="sheet"))
print(f"\nspent so far ${meta_api.spent_usd():.4f} of ${meta_api.budget_usd():.2f}")
