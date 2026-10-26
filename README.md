# med-table (hackathon prototype)

A tool for caregivers of older adults on many medicines. Photograph the packs on the table; the system identifies each pack from its official code, checks it against Spain's AEMPS/CIMA database, and builds a verified inventory. The caregiver sets the schedule (from the active medication sheet), and the tool produces a printable pictogram calendar, a voice reading and a calendar file for phone reminders.

**What it is not.** It does not give medical advice, does not decide doses, and is not a medical device. The schedule always comes from the prescription, entered or confirmed line by line by the caregiver. Every flag shown cites an AEMPS source, with the quoted sentence checked against the original text; the section 4.5 excerpts are shown for the pharmacist to review, never as a verdict. When it cannot identify an item, it asks; it never guesses.

## Status
Early. Built so far: CIMA client and photo downloader, cut-out and synthetic-scene tools, and the identification core: GS1 Data Matrix decoding, Codigo Nacional validation, CIMA resolver with local cache, and per-pack readings (`verified` only when the code decodes, the CN check digit validates and CIMA knows the CN; expiry comes from the code). Smoke tests of SAM 3 / 3.1 and a local Qwen3.5-9B model are in `experiments/` (results in `experiments/README.md`). On top of it (branch `feat/rules`): rules (same active ingredient, same ATC class, expiry, verbatim SmPC 4.5 quotations that name another pack on the table), reconciliation of the caregiver's medication sheet against the verified packs, a plan that only contains confirmed lines with verified, unexpired packs, a printable PDF calendar, Spanish speech text and an `.ics` file (`experiments/demo_plan.py` builds a demo from invented medicines). Not done yet: confirmation UI, sheet reader, text-to-speech audio, alert engine for real SmPC text, real-photo evaluation; see `PLAN.md`.

Run the app: `.venv-app/Scripts/python.exe -m streamlit run app.py --server.address 127.0.0.1` (photo or typed C.N. -> verified packs -> sheet with confirmation -> findings, PDF, voice, `.ics`). Dependencies: `requirements.txt` (`requirements-dev.txt` for tests).

Tests: `.venv-app/Scripts/python.exe -m pytest` (52 tests; they render real GS1 Data Matrix codes and use a stored CIMA response, no network).

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
```
Models and photos are not in git: they are downloaded locally.

## License
Apache License 2.0 (see `LICENSE`). Copyright 2026 Hugo Silvosa Cuervo. Third-party models and data keep their own terms (see `THIRD_PARTY.md`).
