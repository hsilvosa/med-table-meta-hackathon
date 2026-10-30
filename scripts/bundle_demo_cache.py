"""Build `demo_cache/`: the AEMPS CIMA data the demo photo needs, so the planner's demo works with no internet connection.

  .venv-app/Scripts/python.exe scripts/bundle_demo_cache.py

For each medicine of the demo photo (app.DEMO_ITEMS) it copies, from the local caches (fetching from CIMA once if they are missing):
the CIMA record, SmPC sections 4.2 and 4.5, and the official pack and dosage-form photos reduced to 480 px wide. It writes
`demo_cache/SOURCE.md` with the source and the date of the information, as the AEMPS reuse conditions ask.
The app reads its own cache first (`data/cache`), then `demo_cache/`, then CIMA.
"""

import json
import re
import shutil
import sys
import urllib.request
from datetime import date
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from medtable.resolve import Resolver  # noqa: E402
from medtable.smpc import Smpc  # noqa: E402

OUT = ROOT / "demo_cache"
PHOTOS = ROOT / "data/cima/images/full"
WIDTH = 480


def demo_cns() -> list[str]:
    """The national codes of the demo photo, read from app.py (importing it would start Streamlit)."""
    text = (ROOT / "app.py").read_text(encoding="utf-8")
    line = next(l for l in text.splitlines() if l.startswith("DEMO_ITEMS"))
    return re.findall(r'\("(\d{6})"', line)


def small_photo(source: bytes, target: Path) -> None:
    image = cv2.imdecode(np.frombuffer(source, np.uint8), cv2.IMREAD_COLOR)
    scale = WIDTH / image.shape[1]
    if scale < 1:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    target.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(target), image, [cv2.IMWRITE_JPEG_QUALITY, 82])


def main() -> None:
    shutil.rmtree(OUT, ignore_errors=True)
    resolver, smpc = Resolver(ROOT / "data/cache/cima"), Smpc(ROOT / "data/cache/smpc")
    rows, unknown = [], []
    for cn in demo_cns():
        medicine = resolver.by_cn(cn)
        if medicine is None:
            unknown.append(cn)
            rows.append(f"| {cn} | CIMA has no medicine with this code (the demo's unknown code) | {date.today().isoformat()} | - | - |")
            continue
        (OUT / "cima").mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / "data/cache/cima" / f"{cn}.json", OUT / "cima" / f"{cn}.json")
        sections = []
        for section in ("4.2", "4.5"):
            if smpc.section(medicine.nregistro, section):
                (OUT / "smpc").mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / "data/cache/smpc" / f"{medicine.nregistro}_{section}.json", OUT / "smpc" / f"{medicine.nregistro}_{section}.json")
                sections.append(section)
        photos = []
        for kind in ("materialas", "formafarmac"):
            local = PHOTOS / kind / f"{medicine.nregistro}.jpg"
            if local.exists():
                data = local.read_bytes()
            elif medicine.photos.get(kind):
                with urllib.request.urlopen(medicine.photos[kind], timeout=30) as reply:
                    data = reply.read()
            else:
                continue
            small_photo(data, OUT / "photos" / kind / f"{medicine.nregistro}.jpg")
            photos.append(kind)
        rows.append(f"| {cn} | {medicine.name} | {medicine.fetched} | {', '.join(sections) or '-'} | {', '.join(photos) or '-'} |")
    (OUT / "cima").mkdir(parents=True, exist_ok=True)
    (OUT / "cima" / "unknown.json").write_text(json.dumps({"checked": date.today().isoformat(), "cns": unknown}), encoding="utf-8")
    (OUT / "SOURCE.md").write_text(
        "# Source of the files in this folder\n\n"
        "Information from **AEMPS CIMA** (Agencia Española de Medicamentos y Productos Sanitarios, Centro de Información de Medicamentos), "
        "https://cima.aemps.es, reused under the AEMPS legal notice (cite the source, state the date, do not distort the meaning). "
        "The records and SmPC texts are copied unchanged; the photos are the official CIMA photos reduced to "
        f"{WIDTH} px wide. Not written by this project. Bundled on {date.today().isoformat()} by `scripts/bundle_demo_cache.py` "
        "so that the demo works without an internet connection.\n\n"
        "| CN | Medicine | Date of the CIMA information | SmPC sections | Photos |\n|---|---|---|---|---|\n" + "\n".join(rows) + "\n",
        encoding="utf-8")
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    print(f"demo_cache: {sum(1 for f in OUT.rglob('*') if f.is_file())} files, {size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
