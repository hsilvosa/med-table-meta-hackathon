# THIRD_PARTY

Hackathon rule: judges must be able to tell what was built during the event. This file separates what is new work in this repository from what is reused. All code and documents here were written on 2026-10-26 or later and the git history starts that day; no code from the author's earlier projects is included.

## Built in this repository (new work)
Everything tracked in git: `src/medtable/`, `scripts/`, `experiments/`, `PLAN.md` and the READMEs. See `git log`.

## Used but NOT written here (not committed, fetched or installed locally)

| Component | Source | License / terms | How it is used |
|---|---|---|---|
| SAM 3 / SAM 3.1 weights and code | Meta, `facebook/sam3`, `facebook/sam3.1`, github.com/facebookresearch/sam3 (gated, access requested) | SAM license (Meta) | Locates boxes in a photo. Cloned into `third_party/`, weights in the Hugging Face cache; not redistributed. |
| Qwen3.5-9B (GGUF by unsloth) | `Qwen/Qwen3.5-9B`, `unsloth/Qwen3.5-9B-GGUF` | Apache-2.0 | Local vision-language model (reads the medication sheet, proposes candidates). Weights in `models/`, not committed. |
| llama.cpp (`llama-server`) | github.com/ggml-org/llama.cpp | MIT | Serves the local VLM. |
| Meta Model API (Muse Spark `muse-spark-1.3`, standard tier) | https://api.meta.ai/v1, Meta | Meta Model API terms; standard tier (prompts not used for training) | Hosted vision-language model for reading labels and the medication sheet. Images sent to it leave the machine, so only public CIMA photos and fictional sheets are used. Spending is capped by `src/medtable/meta_api.py`. |
| zxing-cpp, pylibdmtx, OpenCV, NumPy, Pillow, PyTorch | PyPI | their own licenses | Barcode decoding, image processing, inference. |
| Streamlit, pandas, ReportLab, pytest, pypdfium2 | PyPI | their own licenses (Apache-2.0 / BSD; ReportLab BSD) | Caregiver web UI, tables, PDF generation, tests, PDF-to-PNG in the demo script. Pinned in `requirements*.txt`. |
| Windows speech engine (System.Speech, voice Microsoft Helena es-ES) | Installed with Windows | Windows license | Offline Spanish voice, called through PowerShell; audio is generated locally and not redistributed. |
| CIMA data and product photos | AEMPS, https://cima.aemps.es | AEMPS legal notice and Spanish public-sector reuse conditions (cite the source, state the date of last update, do not distort the meaning) | Medicine metadata, leaflets and official pack photos. The photos (about 5 GB) are downloaded locally by `scripts/download_cima_photos.py` and are NOT committed. |

## Not included
- No real patient data or prescriptions. Any medication sheet in this repository is fictional.
- No code, data or models from the author's earlier projects.
