# Plan

A tool for caregivers: photograph the medicine packs of an older relative, get a verified inventory checked against the active medication sheet, and a printable pictogram calendar plus a voice reading. Every flag cites an AEMPS/CIMA source. Research prototype; not a medical device; it gives no medical advice.

## Rules that shape the design (hackathon)
- Public repository; only work built during the event; third-party material listed in `THIRD_PARTY.md`.
- Anti-projects: AI giving medical advice, basic RAG apps, simple image analyzers, simple chatbots. So: the schedule always comes from the prescription (photographed or typed) and is confirmed line by line by the caregiver; no leaflet chatbot; no verdicts such as "safe" or "no interactions".
- No real patient data and no CIMA photos in git.

## What the tool claims, and what it does not
Claims: pack identified (not "pill identified"); same active ingredient in two packs; same ATC class (review); expired pack; prescribed but not found on the table; on the table but not prescribed; verbatim SmPC excerpts with their source ("the SmPC of A, section 4.5, mentions B or its class", for the pharmacist to review); food timing only when a sentence of the SmPC or leaflet says so, quoted.
Does not claim: a safe plan, absence of interactions ("no mention found in the sections checked; this is not an interaction check"), identification of loose pills, missed doses, adherence.

## Pipeline (deterministic first, models as fallback)
| Step | What | Type |
|---|---|---|
| 1 | Locate each pack in the photo (SAM 3 text prompt "box") | model |
| 2 | Decode the GS1 Datamatrix (zxing-cpp); read GTIN, expiry, lot | deterministic |
| 3 | Printed "C.N." via OCR/VLM, accepted only if the check digit validates (`src/medtable/cn.py`) | deterministic + model |
| 4 | Resolve the CN in CIMA: ingredients, ATC, form, SmPC sections, official photo | deterministic |
| 5 | If nothing decodes: a vision-language model proposes candidates; the user confirms next to the official photo; otherwise the item is Unverified | model + human |
| 6 | Medication sheet: the VLM reads it into rows, the caregiver confirms every line (or types them) | model + human |
| 7 | Rules: duplicates, ATC class overlap, expiry, prescribed/not found, found/not prescribed, cited SmPC 4.5 mentions | deterministic |
| 8 | Output: calendar PDF (official pack photo as pictogram), voice reading, `.ics` file for phone reminders; doses shown exactly as the caregiver confirmed them, never written by a model | deterministic |

Item states: Verified (code) / Confirmed by user / Unverified. Unverified items never enter the calendar; they are listed under "Not included". Quotes are string-matched against the source text and dropped if they do not match.

## Models and cost
- Whenever a model must be integrated, the default is a Meta model through the Meta Model API: `muse-spark-1.3`, standard tier only (the "-contributor" models let Meta train on the prompts, so they are never used), `reasoning_effort="minimal"`. SAM 3 / 3.1 run locally. Qwen3.5-9B (local) stays as an offline fallback and as the comparison baseline.
- Budget: hard cap of USD 100 for the whole project, enforced in code (`src/medtable/meta_api.py`: every call is logged to `data/meta_usage.jsonl`, and a call is refused when spent + worst case would pass 90% of `META_BUDGET_USD`). Measured: about USD 0.005 per image call (3,000 input tokens for a 1024x576 photo, about 200 output), i.e. roughly 20,000 image calls for USD 100.
- Privacy: whatever is sent to the API leaves the machine. Only public CIMA photos and fictional medication sheets are used in tests and in the demo; a real prescription is never sent.

## Evidence so far (`experiments/README.md`)
- SAM 3 and 3.1 run locally on an RTX 3060; SAM 3 found 71 of 72 boxes in 12 synthetic scenes.
- Qwen3.5-9B reads a fictional medication sheet exactly (28/28 schedule cells) but is unreliable at identifying small pack crops, so identification must come from the pack code.
- A CN is accepted only when check digit, CIMA membership and the other fields agree.
- Identification core implemented and tested (`src/medtable/{gs1,decode,resolve,identify}.py`, 16 tests): a pack is `verified` only if its Data Matrix decodes, parses as GS1, yields a CN whose check digit validates, and CIMA knows it. On rendered (perfect) codes decoding works from about 3 px per module (about 5 with blur), which at 12 MP means a field of view of 30 cm or less; the code-side close-up step stays in the design. Not yet measured on real packs.

## Work packages
1. Datamatrix + CN decoder and CIMA resolver with local cache; evaluation script (coverage, confident-wrong count).
2. Localization step and VLM fallback with candidate confirmation; confirmation screen (official photo beside each crop, numbered detections, "is anything missing?").
3. Medication sheet reader plus manual form; schedule editor; cross-check and rules with cited quotes.
4. Calendar PDF, English voice (test "0,5", "1/2", "every 8 hours"), `.ics`, disclaimers shown in context.
5. Evaluation on real photos (5 development, 15 test, test run once after the last code change), Clopper-Pearson intervals, confident-wrong count as the headline safety metric, results reported with their caveats.
6. README, demo video, buffer.

Synthetic scenes (and a time-boxed Blender variant) are for development and stress tests only; accuracy claims come from real photos.

## Status of the work packages (end of 2026-10-26)
1. Decoder, CN validation, resolver with cache: done (66 tests in the whole repository). The evaluation script exists (`experiments/eval_photos.py`: verified-correct, unverified, missed and confident-wrong with exact intervals); it still needs the real photos and their truth file (`photo name -> list of Codigo Nacional`).
2. Localization with SAM 3 as a subprocess and VLM candidates with caregiver confirmation: done in the app (`src/medtable/candidates.py`, `scripts/segment_boxes.py`). Weak by design: the true medicine was among the candidates in 3 of 12 small crops; the app never picks for the user.
3. Sheet reader, editable sheet, reconciliation, rules with verbatim SmPC 4.5 and 4.2 quotes: done.
4. PDF calendar, offline English voice, `.ics`: done. The voice was not listened to by the author of the code, only checked for non-empty audio; the spoken text was reviewed in text form.
5. Evaluation on real photos: NOT done (no real photos yet). Every accuracy figure in the repository comes from synthetic or Blender data and is labelled as an upper bound.
6. README is up to date; demo video and a stretch adherence check (reference image of the pill, not blind identification) are not done.

Decision recorded: the code side must be photographed from 50 cm or closer (Blender scenes: 98-100 % read at 50 cm or closer, about 90 % at 70 cm, 33 % at 90 cm; perfect labels, so an upper bound).

Bugs found by testing against real services and fixed (worth remembering): CIMA answers an unknown CN with an empty body, not a 404; the same strength is listed per container for liquids, so strengths are only compared for solid forms; pylibdmtx needs `distutils` on Python 3.12 and its fallback had silently been off; zxing-cpp writes rectangular GS1 symbols that real packs do not use.

## Adversarial review (2026-10-26, subagent, read-only) and what was done
A reviewer tried to break the design invariants; every high and medium finding was reproduced or confirmed in code and fixed with a regression test (`tests/test_review_fixes.py`, `tests/test_meta_api.py`): a pack on two sheet lines (doubled dose), all-zero confirmed lines vanishing, unknown or unreadable expiry passing silently, empty or missing sheet cells silently becoming 0, missing SmPC sections or a disabled SmPC check reading as a clean check, a model-read CN ranked first with verification wording, a CIMA answer without the scanned CN among its presentations, NTIN and (712) disagreeing, negated sentences hiding warnings, salts hiding mentions, markup in PDF text (crash and layout injection), two doses overwritten in one PDF cell, ICS lone CR and line folding, removed uploads staying in the plan, and the budget cap reading a different ledger than the one written. Still open, by decision: two physical packs with identical code text count as one. (Closed on 2026-10-30: consent for the Meta API is now checked in `vlm.ask_image` itself, so no caller can send an image without it; an unusually large daily amount is flagged for a second look, and still not blocked, since the caregiver copies the doctor's paper; several boxes of one medicine are one medicine, and the plan uses the one that has not expired.)

## 3D room (2026-10-27)
A first-person room (three.js, `web/`) with three tables of CIMA medicine cut-outs and generated Data Matrix stickers, a virtual 12 MP phone, a local photo server (`scripts/serve_world.py`) and a one-command launcher (`scripts/start_demo.py`). Photos are saved with ground truth; the app loads the latest one. It doubles as a test bench (`experiments/eval_world.py`): 0 confident-wrong in 187 verified, 97 % or more of the codes read at every height up to 90 cm (second version of the room, with the zoomed scan; before it, 9 % above 75 cm). Not built: blister packs, stacked boxes that occlude each other on purpose, depth of field and motion blur, curved cardboard, glossy varnish. The earlier plan for a richer Blender variant was replaced by this room; the Blender scenes remain as a second, physically based check (glare, roughness).

The second version of the room places the medicines of an older patient on many drugs first (`FEATURED` in `scripts/build_world.py`, cut out with `make_cutouts.py --only`) and the fictional sheet on table 1 lists most of them (`experiments/make_fictional_sheet.py`): the demo reads the sheet, matches it to the boxes, and shows the cases on purpose (one expired box, one expiring soon, one code CIMA does not know, two boxes without a code, a medicine on the sheet with no box, a box with no line on the sheet).

Reading distance: the requirement is 90 cm with a 12 MP phone, so that one photo covers a whole table. A plain read fails there (1.6 px/module); the zoomed scan in `decode.py` reads 94.5 % of the readable codes at 12 MP and 98 % at 48 MP (`experiments/README.md`). The room's phone is 48 MP by default (untick "48 MP camera" for 12 MP). Misses are never silent: the app lists the boxes it could not read and asks for a closer photo or the typed code.

## Open items
- Real photos of tables with the Codigo Nacional annotated per pack (to be provided by the author).
- License for the repository.
- Whether the Datamatrix is readable from the overview photo: answered on synthetic data (50 cm or closer; see the status section); still to be confirmed on real packs.
- A box that carries two different codes (an official photo with a printed code plus a sticker) is reported as two packs, because identity is the code text. Real packs carry one Data Matrix, but outer and inner packaging can differ; not handled.
