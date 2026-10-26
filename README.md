# med-table (hackathon prototype)

A tool for caregivers of older adults on many medicines. Photograph the packs on the table; the system identifies each pack from its official code, checks it against Spain's AEMPS/CIMA database, and builds a verified inventory. The caregiver sets the schedule (from the active medication sheet), and the tool produces a printable pictogram calendar, a voice reading and a calendar file for phone reminders.

**What it is not.** It does not give medical advice, does not decide doses, and is not a medical device. The schedule always comes from the prescription, entered or confirmed line by line by the caregiver. Every flag shown cites an AEMPS source, with the quoted sentence checked against the original text; the section 4.5 excerpts are shown for the pharmacist to review, never as a verdict. When it cannot identify an item, it asks; it never guesses.

## Status
Working prototype, tested on synthetic data only. No real pack photos have been used yet, so no accuracy claim is made for real use.

| Part | State |
|---|---|
| Data Matrix decoding (zxing-cpp, tiled search, libdmtx fallback), GS1 parsing, Codigo Nacional check digit | done |
| CIMA resolver with local cache; a pack is `verified` only if the code decodes, the CN check digit is valid and CIMA knows the CN; expiry from the code | done |
| Rules: same active ingredient, same ATC class, expiry, strength vs sheet; verbatim quotes of SmPC sections 4.5 (mentions of another pack on the table) and 4.2 (meals) | done, checked on real CIMA texts |
| Medication sheet: reconciliation with the packs; a line enters the plan only if confirmed, verified, not expired, unambiguous and with a recognised dose | done |
| Sheet reader (Muse Spark or local Qwen; every row comes back unconfirmed) | done; 28/28 cells on one fictional sheet |
| Packs without a readable code: SAM 3 boxes, model-proposed CIMA candidates, caregiver confirms against the official photo | done; the true medicine was among the candidates in 3 of 12 small crops (weak by design: the model only proposes) |
| Output: printable PDF calendar, offline Spanish voice (Windows speech engine), `.ics` reminders | done |
| Streamlit app tying it together | done |
| Evaluation on real photos, real-sheet reading, adherence check with a reference image | not done |

Blender-rendered table scenes (`scripts/blender_scene.py`) decode in 98-100 % of cases from 50 cm or closer and about 90 % at 70 cm; perfect labels on flat boxes, so an upper bound. Details and caveats: `experiments/README.md`.

Run the app: `.venv-app/Scripts/python.exe -m streamlit run app.py --server.address 127.0.0.1` (photo or typed C.N. -> verified packs -> sheet with confirmation -> findings, PDF, voice, `.ics`). Dependencies: `requirements.txt` (`requirements-dev.txt` for tests). `experiments/demo_plan.py` builds a demo plan from invented medicines.

Tests: `.venv-app/Scripts/python.exe -m pytest` (86 tests; they render Data Matrix codes, use invented SmPC texts and a stored CIMA response, no network).

## Models
Vision-language model access goes through `src/medtable/vlm.py`, which has two interchangeable backends selected with `VLM_BACKEND` in `.env`:
- `meta` (default): Meta Model API, `muse-spark-1.3`, standard tier, with a hard spending cap (`META_BUDGET_USD`, every call logged in `data/meta_usage.jsonl`). Images leave the machine, so the app asks for explicit consent before each use and only public CIMA photos and fictional documents should be sent.
- `local`: Qwen3.5-9B (Q4_K_M GGUF) served by `llama-server`, fully offline and free. Start command and settings are in the docstring of `vlm.py`. It is an alternative path: it reads a fictional medication sheet well but is unreliable on small pack crops (`experiments/README.md`), which is why identification relies on the pack code and not on any model.

SAM 3 / 3.1 always run locally.

## Hackathon compliance
- All code and documents in this repository were written on 2026-10-26 or later, from scratch, and the git history starts that day. Earlier throw-away prototypes were discarded and rewritten.
- Third-party models, data and libraries, and what is not committed, are listed in `THIRD_PARTY.md`. The official CIMA photos were first downloaded on 2026-10-24; they are third-party data and are not in the repository.
- No real patient data. Medication sheets used for tests are fictional.

## Reproduce the data tools
```bash
python scripts/download_cima_photos.py manifest      # list of medicines with photos (standard library only)
python scripts/download_cima_photos.py images        # ~5 GB, resumable
python scripts/make_cutouts.py --n 50                # needs SAM 3 (gated weights) and a GPU
python scripts/compose_scenes.py --n 12              # synthetic desk scenes with labels
python experiments/blender_decode_eval.py            # Blender 4.5: decode rate by camera height
```
Models and photos are not in git: they are downloaded locally.

## License
Apache License 2.0 (see `LICENSE`). Copyright 2026 Hugo Silvosa Cuervo. Third-party models and data keep their own terms (see `THIRD_PARTY.md`).
