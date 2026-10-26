"""Smoke test: SAM 3 image model with text prompts on synthetic desk scenes (run from the repo root with .venv-sam3).

Reports detections per prompt, time and peak VRAM, and saves an overlay. Reconstructed from the original spike.
Findings: bf16 autocast is required (else a bf16/float dtype error); ~1 s/image, 5.4 GB peak on an RTX 3060.
"""
import json, time
import cv2, numpy as np, torch
from PIL import Image
from sam3.model_builder import build_sam3_image_model
from sam3.model.sam3_image_processor import Sam3Processor

SC = "data/scenes"
OUT = "experiments/out"
ann = json.load(open(f"{SC}/annotations.json", encoding="utf-8"))
model = build_sam3_image_model()          # loads sam3.pt (the image model), not the 3.1 video checkpoint
proc = Sam3Processor(model)
torch.autocast("cuda", dtype=torch.bfloat16).__enter__()

prompts = {"medicine box": (0, 200, 0), "pill": (0, 0, 255), "blister pack": (255, 0, 0)}
cells = []
for name in sorted(ann)[:3]:
    gt = {k: sum(a["kind"] == k for a in ann[name]) for k in ("box", "pill")}
    img = Image.open(f"{SC}/{name}").convert("RGB")
    vis = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    t = time.time()
    state = proc.set_image(img)
    found = {}
    for p, col in prompts.items():
        out = proc.set_text_prompt(state=state, prompt=p)
        keep = out["scores"].float().cpu().numpy() > 0.5
        found[p] = int(keep.sum())
        for b in out["boxes"].float().cpu().numpy()[keep]:
            cv2.rectangle(vis, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])), col, 3)
    print(name, "GT", gt, "found", found, f"{time.time() - t:.2f}s, peak VRAM {torch.cuda.max_memory_allocated() / 1e9:.2f} GB")
    cells.append(cv2.resize(vis, (640, 480)))
cv2.imwrite(f"{OUT}/sam3_overlay.jpg", np.hstack(cells))
