"""Locate packs ("box") in a photo with SAM 3 and write one crop per detection. Runs in .venv-sam3 (GPU).

  .venv-sam3/Scripts/python.exe scripts/segment_boxes.py PHOTO OUT_DIR [--min-score 0.5]

Writes OUT_DIR/box_<k>.jpg and OUT_DIR/boxes.json: [{"crop": ..., "bbox": [x0, y0, x1, y1], "score": ...}].
SAM only localizes: it says where a pack is, never which medicine it is.
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

ap = argparse.ArgumentParser()
ap.add_argument("photo", type=Path)
ap.add_argument("out_dir", type=Path)
ap.add_argument("--min-score", type=float, default=0.5)
args = ap.parse_args()
args.out_dir.mkdir(parents=True, exist_ok=True)

img = Image.open(args.photo).convert("RGB")
bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
proc = Sam3Processor(build_sam3_image_model())
torch.autocast("cuda", dtype=torch.bfloat16).__enter__()
result = proc.set_text_prompt(state=proc.set_image(img), prompt="box")
boxes, scores = result["boxes"].float().cpu().numpy(), result["scores"].float().cpu().numpy()

found = []
for k, (box, score) in enumerate(zip(boxes, scores)):
    if score < args.min_score:
        continue
    x0, y0, x1, y1 = (max(int(v), 0) for v in box)
    crop = args.out_dir / f"box_{k}.jpg"
    cv2.imwrite(str(crop), bgr[y0:y1, x0:x1])
    found.append({"crop": crop.name, "bbox": [x0, y0, x1, y1], "score": float(score)})
(args.out_dir / "boxes.json").write_text(json.dumps(found, indent=1), encoding="utf-8")
print(f"{len(found)} boxes")
