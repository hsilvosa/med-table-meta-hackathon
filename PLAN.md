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
| 2 | Decode the GS1 Datamatrix (zxing-cpp, then pylibdmtx); read GTIN, expiry, lot | deterministic |
| 3 | Printed "C.N." via OCR/VLM, accepted only if the check digit validates (`src/medtable/cn.py`) | deterministic + model |
| 4 | Resolve the CN in CIMA: ingredients, ATC, form, SmPC sections, official photo | deterministic |
| 5 | If nothing decodes: the local VLM (Qwen3.5-9B) proposes candidates; the user confirms next to the official photo; otherwise the item is Unverified | model + human |
| 6 | Medication sheet: the VLM reads it into rows, the caregiver confirms every line (or types them) | model + human |
| 7 | Rules: duplicates, ATC class overlap, expiry, prescribed/not found, found/not prescribed, cited SmPC 4.5 mentions | deterministic |
| 8 | Output: calendar PDF (official pack photo as pictogram), voice reading, `.ics` file for phone reminders; doses shown exactly as the caregiver confirmed them, never written by a model | deterministic |

Item states: Verified (code) / Confirmed by user / Unverified. Unverified items never enter the calendar; they are listed under "Not included". Quotes are string-matched against the source text and dropped if they do not match.

## Evidence so far (`experiments/README.md`)
- SAM 3 and 3.1 run locally on an RTX 3060; SAM 3 found 71 of 72 boxes in 12 synthetic scenes.
- Qwen3.5-9B reads a fictional medication sheet exactly (28/28 schedule cells) but is unreliable at identifying small pack crops, so identification must come from the pack code.
- A CN is accepted only when check digit, CIMA membership and the other fields agree.

## Work packages
1. Datamatrix + CN decoder and CIMA resolver with local cache; evaluation script (coverage, confident-wrong count).
2. Localization step and VLM fallback with candidate confirmation; confirmation screen (official photo beside each crop, numbered detections, "is anything missing?").
3. Medication sheet reader plus manual form; schedule editor; cross-check and rules with cited quotes.
4. Calendar PDF, Spanish voice (test "0,5", "1/2", "cada 8 horas"), `.ics`, disclaimers shown in context.
5. Evaluation on real photos (5 development, 15 test, test run once after the last code change), Clopper-Pearson intervals, confident-wrong count as the headline safety metric, results reported with their caveats.
6. README, demo video, buffer.

Synthetic scenes (and a time-boxed Blender variant) are for development and stress tests only; accuracy claims come from real photos.

## Open items
- Real photos of tables with the Codigo Nacional annotated per pack (to be provided by the author).
- License for the repository.
- Whether the Datamatrix is readable from the overview photo or needs a "show the code side" step; decided by the first decode-rate measurement.
