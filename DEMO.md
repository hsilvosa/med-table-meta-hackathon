# Demo script (about 3 minutes)

Run `.venv-app/Scripts/python.exe scripts/start_demo.py`: it opens the 3D room (http://127.0.0.1:8600) and the app (http://127.0.0.1:8501). Use only the synthetic demo photo, invented doses and public CIMA data. Never show a real prescription or a real patient name.

| Time | Do | Say (the point to land) |
|---|---|---|
| 0:00 | Open the app; point at the blue notice | It supports the caregiver and does not replace the doctor or the pharmacist. It schedules; it does not advise. |
| 0:20 | In the 3D room: walk to a table (WASD and mouse, click to capture the mouse), press Shift+1 to hold the virtual phone 50 cm above it, Space to take the photo. In the app: "Usar la ultima foto de la sala 3D" (or "Cargar foto de ejemplo" without the room) | Each pack is identified only by its own Data Matrix code, resolved in AEMPS CIMA. Five packs are verified with the official photo beside them; the sixth code is unknown to CIMA and is marked NOT verified. |
| 0:50 | Show the table: expiry read from the code, one expired pack | Expiry comes from the code, not from a model. |
| 1:10 | In the sheet, type doses for three medicines, tick "Confirmado" | The doses are the caregiver's. The tool never proposes or changes a dose. Unticked lines stay out. |
| 1:40 | Show the plan, the "No incluido" list and the review notes | Anything unverified, expired, unconfirmed, ambiguous or with a strength that does not match is listed with the reason. Quotes from the AEMPS leaflet (section 4.5 and 4.2) are verbatim, with source and date, and are for the pharmacist: never a verdict. The page says plainly that no warning does not mean safe. |
| 2:10 | Download the PDF; open it | Large print, official pack photo, one row per medicine, the "not included" block and the sources. |
| 2:30 | Click "Generar versión en voz"; play one slot | Offline Spanish voice; the text never leaves the machine. |
| 2:45 | Show the `.ics` file import (optional) | Daily reminders on the phone. |
| 2:55 | Close | Measured on synthetic data only, so no accuracy claim for real use yet; real photos are the next step. |

## What the 3D room is
A stage set: flat cut-outs of the official CIMA photos with a Data Matrix sticker that this repository generates from each medicine's real Codigo Nacional. Say so. It shows the flow and measures the optics (read rate by distance), not how real printed codes behave. Built-in cases to point at: an expired pack, one expiring within a month, a code CIMA does not know (stays unverified), packs with no visible code (SAM + candidates, the caregiver decides), loose pills (never identified) and the fictional medication sheet on table 1.

## What not to claim
- No "safe plan", "no interactions" or "verified plan in seconds".
- No accuracy figure for real packs (none has been measured). The Blender numbers (98-100 % read at 50 cm or closer) are for perfect labels.
- The candidate flow for packs without a readable code is weak by design (true medicine among the candidates in 3 of 12 small synthetic crops); say that the caregiver always decides.
- Meta API calls send images off the machine; the app asks for consent each time. Show it with a fictional sheet only.

## If something fails live
- CIMA down: packs already seen are served from the local cache; a typed C.N. of an unseen pack needs the network.
- No GPU: SAM 3 step reports an error and typing the C.N. still works.
- No Spanish Windows voice: the voice button is hidden; PDF and `.ics` still work.
