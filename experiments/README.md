# Experiments (spikes)

Throw-away scripts that de-risked the design. Run from the repository root. They read `data/` (CIMA photos, cut-outs, scenes) and write to `experiments/out/` (ignored by git). SAM scripts need `.venv-sam3`; the rest run with `.venv-app`. The VLM scripts need a local llama-server on port 8082 (command in `vlm_client.py`).

| Script | What it tests |
|---|---|
| `sam3_image_smoke.py` | SAM 3 image model with text prompts on synthetic scenes |
| `sam31_video_smoke.py` | SAM 3.1 multiplex checkpoint on a still image, with the Windows / consumer-GPU workarounds |
| `sam3_box_crops.py` | SAM 3 "box" crops of the scenes, matched to ground truth (IoU >= 0.5) |
| `vlm_read_packs.py` | Qwen3.5-9B reading CIMA pack photos; CN checked against check digit and CIMA |
| `vlm_eval.py` | Qwen3.5-9B on the SAM crops and on a fictional medication sheet |
| `make_fictional_sheet.py` | Renders the fictional medication sheet with phone-photo degradations |

## Results (2026-10-26; small samples, read them as indications, not metrics)

- **SAM 3 / 3.1 run on an RTX 3060 under Windows** (5.4 GB / 6.4 GB peak, 1-2 s per prompt). They need bf16 autocast; SAM 3.1 also needs `use_fa3=False` and a wrapper around an upstream `init_state` argument bug (see the script). On 12 synthetic scenes SAM 3 matched 71 of 72 ground-truth packs (IoU >= 0.5) and made 10 extra detections.
- **Cut-outs (`scripts/make_cutouts.py`)**: on 50 random medicines, 50 pack cut-outs and 51 dosage-form cut-outs passed the checks; by eye the packs are whole and the pills clean. 3 of 31 oral-solid medicines got no pill.
- **Qwen3.5-9B on full CIMA pack photos**: brand or ingredient matched in 7 of 8; 6 CN reads, 5 accepted (check digit valid and present in CIMA for that medicine), 1 rejected by the check digit.
- **Qwen3.5-9B on small crops from synthetic scenes (73 crops, about 300 px, rotated, partly occluded)**: by the crude name check 28 correct, 2 abstentions, 43 wrong; 15 CN reads, 8 with a valid check digit, 6 of those present in CIMA for the true medicine. Wrong answers include invented ingredients and look-alike confusions. The check is crude (it also counts as wrong correct ingredients given without the brand, e.g. Xelevia read as MSD/sitagliptin), but the conclusion holds: the model must not identify packs. Identification comes from the pack code; the model only proposes candidates that the user confirms, and a CN is accepted only if the check digit, CIMA membership and the other fields agree.
- **Qwen3.5-9B on the fictional medication sheet**: 7/7 rows, 28/28 schedule cells and all remarks exact, 15 s. One clean synthetic sheet; real sheets are untested, so every line still needs caregiver confirmation.
