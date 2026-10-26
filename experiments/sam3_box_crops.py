"""SAM 3 'box' detections on the synthetic scenes -> crops, matched to the ground truth (IoU >= 0.5).

  .venv-sam3/Scripts/python.exe experiments/sam3_box_crops.py [--scenes data/scenes]

Writes experiments/out/crops/*.jpg and crops.json (input for vlm_eval.py) and prints recall.
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image
from sam3.model.sam3_image_processor import Sam3Processor
from sam3.model_builder import build_sam3_image_model


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


ap = argparse.ArgumentParser()
ap.add_argument("--scenes", type=Path, default=Path("data/scenes"))
args = ap.parse_args()
out_dir = Path("experiments/out/crops")
out_dir.mkdir(parents=True, exist_ok=True)

truth = json.load((args.scenes / "annotations.json").open(encoding="utf-8"))
proc = Sam3Processor(build_sam3_image_model())
torch.autocast("cuda", dtype=torch.bfloat16).__enter__()

rows, n_truth, n_found, n_matched = [], 0, 0, 0
for name in sorted(truth):
    img = Image.open(args.scenes / name).convert("RGB")
    bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    result = proc.set_text_prompt(state=proc.set_image(img), prompt="box")
    boxes, scores = result["boxes"].float().cpu().numpy(), result["scores"].float().cpu().numpy()
    gts = [(a, [a["bbox"][0], a["bbox"][1], a["bbox"][0] + a["bbox"][2], a["bbox"][1] + a["bbox"][3]])
           for a in truth[name] if a["kind"] == "box"]
    matched = set()
    for k, (box, score) in enumerate(zip(boxes, scores)):
        if score < 0.5:
            continue
        n_found += 1
        best = max(range(len(gts)), key=lambda j: iou(box, gts[j][1])) if gts else None
        gt = gts[best][0] if best is not None and iou(box, gts[best][1]) >= 0.5 else None
        if gt:
            matched.add(best)
        x0, y0, x1, y1 = (max(int(v), 0) for v in box)
        path = out_dir / f"{Path(name).stem}_{k}.jpg"
        cv2.imwrite(str(path), bgr[y0:y1, x0:x1])
        rows.append({"crop": str(path), "scene": name, "score": float(score),
                     "gt_nregistro": gt["nregistro"] if gt else None, "gt_nombre": gt["nombre"] if gt else None,
                     "visible_frac": gt["visible_frac"] if gt else None})
    n_truth += len(gts)
    n_matched += len(matched)
    print(f"{name}: ground-truth boxes {len(gts)}, detected {sum(1 for s in scores if s >= 0.5)}, matched {len(matched)}")

json.dump(rows, (out_dir / "crops.json").open("w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"TOTAL ground truth {n_truth}, detected {n_found}, matched {n_matched} (recall {n_matched / max(n_truth, 1):.0%}), "
      f"crops with ground truth {sum(r['gt_nregistro'] is not None for r in rows)}")
