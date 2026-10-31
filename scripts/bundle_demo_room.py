"""Build `web/world_demo/`: a small copy of the 3D room that is committed, so the room works from a fresh clone with one command.

  .venv-app/Scripts/python.exe scripts/bundle_demo_room.py [--src web/world]

The full room (`web/world`, about 10 MB, ignored by git) is built by scripts/build_world.py from the bulk CIMA photo download and the
SAM 3 cut-outs, which a clone does not have. This script takes that built room and keeps the same scene with lighter pictures: the
cut-out boxes and pills (official AEMPS CIMA photos) reduced and stored as WebP, the fictional medication sheet as a smaller JPEG.
The Data Matrix labels are our own generated images and are copied unchanged, so reading them is exactly as in the full room.
`scripts/serve_world.py` serves this folder when `web/world` does not exist. Run `scripts/bundle_demo_cache.py` afterwards: it also
bundles the CIMA records of the room's medicines, so the room works offline too.
"""

import argparse
import json
import shutil
from datetime import date
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "world_demo"
BOX_PX, PILL_PX, SHEET_PX = 1000, 160, 1100     # longest side. Boxes keep their own resolution (at most 1000 px): smaller ones look blurred in
                                                 # the phone frame, and the live advice then reports a blurry picture


def shrink(source: Path, target: Path, longest: int, **params) -> None:
    image = cv2.imread(str(source), cv2.IMREAD_UNCHANGED)
    scale = longest / max(image.shape[:2])
    if scale < 1:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    flags = [cv2.IMWRITE_WEBP_QUALITY, 82] if target.suffix == ".webp" else [cv2.IMWRITE_JPEG_QUALITY, 82]
    assert cv2.imwrite(str(target), image, flags), target


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=ROOT / "web" / "world")
    args = ap.parse_args()
    world = json.loads((args.src / "world.json").read_text(encoding="utf-8"))
    shutil.rmtree(OUT, ignore_errors=True)
    (OUT / "assets").mkdir(parents=True)
    medicines = {}
    for table in world["tables"]:
        for item in table["items"]:
            source = args.src / item["tex"]
            if item["kind"] == "sheet":
                target = OUT / "assets" / "sheet.jpg"
                shrink(source, target, SHEET_PX)
            else:
                target = OUT / "assets" / (Path(item["tex"]).stem + ".webp")
                shrink(source, target, BOX_PX if item["kind"] == "box" else PILL_PX)
            item["tex"] = f"assets/{target.name}"
            if item.get("label"):
                shutil.copy(args.src / item["label"]["tex"], OUT / item["label"]["tex"])
            if item["kind"] == "box":
                medicines[item["nregistro"]] = item
    (OUT / "world.json").write_text(json.dumps(world, indent=1), encoding="utf-8")
    rows = "\n".join(f"| {m['nregistro']} | {m['name']} | {m['cn']} |" for m in medicines.values())
    (OUT / "SOURCE.md").write_text(
        "# Source of the pictures in this folder\n\n"
        "The box and pill pictures (`assets/box_*.webp`, `assets/pill_*.webp`) are cut out of the official medicine photos of **AEMPS CIMA** "
        "(Agencia Española de Medicamentos y Productos Sanitarios, https://cima.aemps.es), reused under the AEMPS legal notice (cite the "
        "source, state the date, do not distort the meaning). They were reduced in size and, where the photo showed a printed Data Matrix, "
        "that code was painted over so it is not read as a second pack (scripts/build_world.py). Not made by this project.\n\n"
        "Made by this project: the Data Matrix labels (`assets/dm_*.png`, generated from each medicine's national code), the fictional "
        f"medication sheet (`assets/sheet.jpg`, no real patient) and the scene layout (`world.json`). Room built on {world['today']}; "
        f"bundled on {date.today().isoformat()} by `scripts/bundle_demo_room.py`. Expiry dates in the labels are relative to the build day.\n\n"
        "| Registration number | Medicine | CN |\n|---|---|---|\n" + rows + "\n", encoding="utf-8")
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    print(f"{OUT}: {sum(1 for f in OUT.rglob('*') if f.is_file())} files, {size / 1024:.0f} KB ({len(medicines)} medicines)")


if __name__ == "__main__":
    main()
