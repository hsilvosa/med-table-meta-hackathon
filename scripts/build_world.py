"""Build the data of the 3D room: which medicines are on which table, with their Data Matrix labels and the ground truth.

  .venv-app/Scripts/python.exe scripts/build_world.py [--seed 3] [--out web/world]

Needs data/cutouts (make_cutouts.py) and, for the featured medicines, data/cutouts_featured (see FEATURED below); the network the first time (CIMA lookups are cached in data/cache/cima).
Writes web/world/world.json and web/world/assets/*.png (cut-out boxes and pills from the official CIMA photos, generated
Data Matrix labels). Everything under web/world is generated and not committed: the photos belong to AEMPS.

The scene is deliberately a stage set: boxes are flat 2D cut-outs lying on the table with a sticker carrying a Data Matrix
that WE generate from the medicine's real Codigo Nacional. So reading the sticker back proves the optics and the pipeline,
not that real printed codes are readable. Cases built in on purpose (see "case" in world.json):
  expired, expires_soon  - the expiry inside the code is in the past / within 30 days
  unknown_cn             - a valid-looking CN that CIMA does not know (stays unverified)
  no_code                - a box with no sticker (goes through SAM + candidates + caregiver confirmation)
"""

import argparse
import json
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import cv2
from PIL import Image

sys.path.insert(0, "src")
import numpy as np  # noqa: E402
from medtable import cima, cn as cn_module  # noqa: E402
from medtable.decode import find_datamatrix  # noqa: E402
from medtable.resolve import Resolver  # noqa: E402
from medtable.synthetic import ntin_element_string, render_datamatrix  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--seed", type=int, default=3)
ap.add_argument("--out", type=Path, default=Path("web/world"))
ap.add_argument("--today", default=None, help="ISO date used to build expiries (default: today)")
args = ap.parse_args()
rng = random.Random(args.seed)
today = date.fromisoformat(args.today) if args.today else date.today()
assets = args.out / "assets"
assets.mkdir(parents=True, exist_ok=True)
resolver = Resolver("data/cache/cima")

BOX_WIDTH_M = 0.16      # width of the cut-out image on the table (a pack seen at 3/4 is about this wide)
LABEL_M = 0.015         # 12 mm code plus quiet zone
TABLES = [("mesa1", "Table 1", -2.6, -1.4, 6), ("mesa2", "Table 2", 0.0, -1.4, 6), ("mesa3", "Table 3", 2.6, -1.4, 5)]
TABLE_W, TABLE_D, TABLE_H = 1.2, 0.7, 0.75
# The first boxes are the medicines of an older patient on many drugs (enalapril, metformin, omeprazole, atorvastatin, lorazepam, furosemide,
# aspirin, amlodipine, levothyroxine, donepezil); the rest of the room is filled with random CIMA medicines. The fictional sheet on table 1
# (experiments/make_fictional_sheet.py) lists most of them, so the whole flow tells one story. Cut them out first with:
#   .venv-sam3/Scripts/python.exe scripts/make_cutouts.py --only <these nregistro> --out data/cutouts_featured
FEATURED = ["73300", "68167", "63983", "69536", "68477", "64140", "62825", "65460", "64014", "73152"]
CASES = {0: "expired", 7: "expires_soon", 12: "unknown_cn", 3: "no_code", 15: "no_code"}  # by box number over all tables


def trim(path: Path) -> Image.Image:
    img = Image.open(path).convert("RGBA")
    return img.crop(img.getchannel("A").getbbox())


def erase_printed_codes(img: Image.Image) -> tuple[Image.Image, int]:
    """Some official CIMA studio photos show a real printed Data Matrix on the box. A second code (our sticker) on the same box would be read
    as a second medicine, so those printed codes are painted over with their surroundings. Returns the image and how many were erased."""
    rgba = np.array(img)
    white = np.full(rgba.shape[:2] + (3,), 255, np.uint8)
    alpha = rgba[..., 3:4].astype(np.float32) / 255
    bgr = (rgba[..., 2::-1] * alpha + white * (1 - alpha)).astype(np.uint8)
    found = find_datamatrix(bgr, tiles=True, libdmtx=True)
    if not found:
        return img, 0
    mask = np.zeros(bgr.shape[:2], np.uint8)
    for d in found:
        x0, y0, x1, y1 = d.bbox
        pad = int(0.35 * max(x1 - x0, y1 - y0))
        mask[max(y0 - pad, 0):y1 + pad, max(x0 - pad, 0):x1 + pad] = 255
    painted = cv2.inpaint(np.ascontiguousarray(rgba[..., 2::-1]), mask, 7, cv2.INPAINT_TELEA)
    out = rgba.copy()
    out[..., :3] = painted[..., ::-1]
    return Image.fromarray(out), len(found)


def sticker_spot(img: Image.Image) -> tuple[float, float]:
    """Where to stick the label: the centroid of the opaque pixels in the lower-right part of the cut-out (fractions of
    width and height), so it covers a corner of the pack and not the product name."""
    alpha = img.getchannel("A").resize((64, 64))
    pts = [(x, y) for x in range(64) for y in range(64) if alpha.getpixel((x, y)) > 200 and x >= 36 and y >= 38]
    if len(pts) < 20:  # odd silhouettes: fall back to the whole opaque area
        pts = [(x, y) for x in range(64) for y in range(64) if alpha.getpixel((x, y)) > 200]
    return sum(p[0] for p in pts) / len(pts) / 64, sum(p[1] for p in pts) / len(pts) / 64


def expiry_for(case: str | None) -> str:
    if case == "expired":
        d = today - timedelta(days=rng.randint(40, 400))
    elif case == "expires_soon":
        d = today + timedelta(days=rng.randint(8, 25))
    else:
        d = today + timedelta(days=rng.randint(200, 1000))
    return d.strftime("%y%m00")  # day 00 = last day of the month, as printed on packs


def place(taken: list[tuple[float, float, float]], radius: float) -> tuple[float, float]:
    for _ in range(300):
        x = rng.uniform(-TABLE_W / 2 + radius, TABLE_W / 2 - radius)
        z = rng.uniform(-TABLE_D / 2 + radius, TABLE_D / 2 - radius)
        if all(math.hypot(x - tx, z - tz) > radius + tr for tx, tz, tr in taken):
            return x, z
    return rng.uniform(-0.3, 0.3), rng.uniform(-0.2, 0.2)


def presentation_cn(nregistro: str) -> str | None:
    for p in cima.medicine_by_nregistro(nregistro).get("presentaciones", []):
        if p.get("cn") and p.get("comerc", True):
            return p["cn"]
    return None


def load_index(folder: str) -> list[dict]:
    path = Path(folder) / "index.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []
    return [{**r, "dir": folder} for r in rows]


index = load_index("data/cutouts")
featured = {r["nregistro"]: r for r in load_index("data/cutouts_featured") if r["boxes"]}
candidates = [r for r in index if r["boxes"] and r["nregistro"] not in featured]
rng.shuffle(candidates)
candidates = [featured[n] for n in FEATURED if n in featured] + candidates          # featured medicines first, in order
index += list(featured.values())
need = sum(t[4] for t in TABLES)
picked = []
for row in candidates:
    if len(picked) == need:
        break
    try:
        code = presentation_cn(row["nregistro"])
        medicine = resolver.by_cn(code) if code else None
    except Exception as exc:  # noqa: BLE001
        print("skip", row["nregistro"], str(exc)[:80])
        continue
    if medicine:
        picked.append((row, medicine))
print(f"{len(picked)} medicines resolved in CIMA")
if len(picked) < need:
    raise SystemExit(f"only {len(picked)} of {need} medicines could be resolved")

world = {"room": {"w": 9.0, "d": 6.5, "h": 2.7}, "today": today.isoformat(), "start": {"x": 0.0, "z": 2.2, "yaw": 0.0}, "tables": []}
slot = labels = 0
for table_id, table_name, tx, tz, count in TABLES:
    taken: list[tuple[float, float, float]] = []
    items = []
    if table_id == "mesa1":
        taken.append((TABLE_W / 2 - 0.17, 0.0, 0.18))  # room for the medication sheet, placed after the boxes
    for _ in range(count):
        row, medicine = picked[slot]
        case = CASES.get(slot)
        slot += 1
        box, erased = erase_printed_codes(trim(Path(row["dir"]) / "box" / row["boxes"][0]))
        if erased:
            print(f"  painted over {erased} printed code(s) on the official photo of {medicine.name[:40]}")
            leftover = find_datamatrix(cv2.cvtColor(np.array(box.convert("RGB")), cv2.COLOR_RGB2BGR))
            assert not leftover, "a printed code survived the inpainting"
        tex = f"box_{row['nregistro']}.png"
        box.save(assets / tex)
        x, z = place(taken, BOX_WIDTH_M * 0.55)
        taken.append((x, z, BOX_WIDTH_M * 0.55))
        item = {"kind": "box", "tex": f"assets/{tex}", "x": x, "z": z, "rot": rng.uniform(0, 2 * math.pi), "w": BOX_WIDTH_M,
                "h": BOX_WIDTH_M * box.height / box.width, "nregistro": row["nregistro"], "name": medicine.name, "cn": medicine.cn, "case": case, "label": None}
        if case != "no_code":
            shown = "100008" if case == "unknown_cn" else medicine.cn
            text = ntin_element_string(shown, expiry_for(case), lot=f"L{rng.randint(100, 999)}", serial=f"SN{rng.randrange(10**6):06d}")
            label_name = f"dm_{labels:03d}.png"
            labels += 1
            cv2.imwrite(str(assets / label_name), render_datamatrix(text, module_px=16, quiet=2))
            u, v = sticker_spot(box)
            item["label"] = {"tex": f"assets/{label_name}", "u": u, "v": v, "size": LABEL_M, "text": text}
            item["cn7"] = f"{shown}{cn_module.check_digit(shown)}"
        items.append(item)
    for pill_row in rng.sample([r for r in index if r["pills"]], 3):  # loose pills: distractors, never identified
        pill = trim(Path(pill_row["dir"]) / "pill" / pill_row["pills"][0])
        size = rng.uniform(0.010, 0.016)
        x, z = place(taken, size)
        taken.append((x, z, size))
        name = f"pill_{pill_row['nregistro']}.png"
        pill.save(assets / name)
        items.append({"kind": "pill", "tex": f"assets/{name}", "x": x, "z": z, "rot": rng.uniform(0, 2 * math.pi), "w": size, "h": size * pill.height / pill.width})
    if table_id == "mesa1" and Path("experiments/out/sheet.jpg").exists():
        sheet = Image.open("experiments/out/sheet.jpg").convert("RGB")
        sheet.thumbnail((1400, 1400))
        sheet.save(assets / "sheet.jpg", quality=90)
        items.append({"kind": "sheet", "tex": "assets/sheet.jpg", "x": TABLE_W / 2 - 0.17, "z": 0.0, "rot": math.pi / 2 + 0.05, "w": 0.21, "h": 0.21 * sheet.height / sheet.width})
    world["tables"].append({"id": table_id, "name": table_name, "x": tx, "z": tz, "w": TABLE_W, "d": TABLE_D, "h": TABLE_H, "items": items})

(args.out / "world.json").write_text(json.dumps(world, indent=1), encoding="utf-8")
boxes = [i for t in world["tables"] for i in t["items"] if i["kind"] == "box"]
print(f"{args.out / 'world.json'}: {len(boxes)} boxes, {sum(i['kind'] == 'pill' for t in world['tables'] for i in t['items'])} loose pills")
for b in boxes:
    if b["case"]:
        print("  case", b["case"], b["name"][:40])
