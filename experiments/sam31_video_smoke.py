"""Smoke test: SAM 3.1 (multiplex video checkpoint) used on a still image as a 2-frame 'video' (run from the repo root with .venv-sam3).

Reconstructed from the original spike. Workarounds needed on Windows / consumer GPUs:
  - use_fa3=False: FlashAttention 3 only exists for Hopper GPUs.
  - run under torch.autocast("cuda", dtype=torch.bfloat16).
  - upstream bug: the base predictor passes `offload_state_to_cpu` to init_state, which the multiplex model rejects; drop it.
  - the load log reports 64 missing `freqs_cis` keys (rotary tables built at init); output looked fine, not rigorously verified.
Measured: ~1-2 s per text prompt, 6.5 GB peak VRAM (RTX 3060).
"""
import os, shutil, time
import cv2, numpy as np, torch
from sam3.model_builder import build_sam3_multiplex_video_predictor

SCENE = "data/scenes/scene_0000.jpg"
FRAMES = "experiments/out/frames1"
shutil.rmtree(FRAMES, ignore_errors=True)
os.makedirs(FRAMES)
img = cv2.imread(SCENE)
cv2.imwrite(f"{FRAMES}/0.jpg", img)
cv2.imwrite(f"{FRAMES}/1.jpg", img)       # two identical frames in case a single frame is not allowed

pred = build_sam3_multiplex_video_predictor(use_fa3=False)
_init = pred.model.init_state
pred.model.init_state = lambda **kw: _init(**{k: v for k, v in kw.items() if k != "offload_state_to_cpu"})

with torch.autocast("cuda", dtype=torch.bfloat16):
    sid = pred.handle_request(dict(type="start_session", resource_path=FRAMES))["session_id"]
    for text in ("medicine box", "pill"):
        pred.handle_request(dict(type="reset_session", session_id=sid))   # required between text prompts
        t = time.time()
        out = pred.handle_request(dict(type="add_prompt", session_id=sid, frame_index=0, text=text))["outputs"]
        probs = np.asarray(out["out_probs"])
        print(text, f"{time.time() - t:.2f}s", "objects:", len(probs), "score>0.5:", int((probs > 0.5).sum()))
print("peak VRAM GB", torch.cuda.max_memory_allocated() / 1e9)
