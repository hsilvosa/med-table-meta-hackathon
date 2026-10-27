# Demo script (about 3 minutes)

Run `.venv-app/Scripts/python.exe scripts/start_demo.py`: it opens the 3D room (http://127.0.0.1:8600) with the planner app in its right-hand panel. Use only the synthetic demo photo, invented doses and public CIMA data. Never show a real prescription or a real patient name.

| Time | Do | Say (the point to land) |
|---|---|---|
| 0:00 | Open the room: the left panel always shows the three steps and the keys. Point at the blue notice in the planner (Tab shows it) | It supports the caregiver and does not replace the doctor or the pharmacist. It schedules; it does not advise. |
| 0:20 | In the room, left panel: "Table 1", "Phone over the table" (90 cm above it, the whole table in view; the bar turns green), "Take photo" (the 48 MP camera takes about 6 s; Space does the same) | The packs are identified by the code printed on them, nothing else. The photo reaches the planner by itself and is read in a few seconds. |
| 0:50 | Step 1 lists the medicines found: expiry read from the code, one expired pack (enalapril); each card has "Remove this medicine" for a wrong or unwanted box. Open "A box has no code I can read?" and run it for the atorvastatin box | A model only suggests; the caregiver confirms against the official picture. Nothing enters the plan on its own. |
| 1:10 | Step 2: type a name; open "Have a photo of the doctor's schedule?", upload `experiments/out/sheet.jpg`, tick the consent, "Read the schedule"; check a few lines against the paper and tick "Yes, this matches the doctor's schedule" | The doses are the caregiver's. The computer copied the paper, the caregiver confirms line by line; nothing is ticked for them. Unticked lines stay out. |
| 1:40 | Step 3: the plan, the "Left out" cards (each says what to do) and "To ask your pharmacist" | Anything unverified, expired, unconfirmed, ambiguous or with a strength that does not match is listed with the reason. Quotes from the AEMPS leaflet (4.5 and 4.2) are verbatim, with the source. |
| 2:10 | Step 4: add a note for the whole plan, look at the preview, download the PDF | Page 1 is for the fridge: pictograms, times, large print, official pack photo, notes. Page 2 is for the pharmacist: what was left out, the quotes and the sources. |
| 2:30 | "Read the plan aloud"; play one slot | Offline English voice; the text never leaves the machine. |
| 2:45 | Show the `.ics` file import (optional) | Daily reminders on the phone. |
| 2:55 | Close | Measured on synthetic data only, so no accuracy claim for real use yet; real photos are the next step. |

## What the 3D room is
A stage set: flat cut-outs of the official CIMA photos with a Data Matrix sticker that this repository generates from each medicine's real Codigo Nacional. Say so. It shows the flow and measures the optics (read rate by distance), not how real printed codes behave. Built-in cases to point at: an expired pack, one expiring within a month, a code CIMA does not know (stays unverified), packs with no visible code (SAM + candidates, the caregiver decides), loose pills (never identified), and the fictional medication sheet on table 1, which lists most of the boxes of tables 1 and 2 plus one medicine that has no box (bisoprolol); amlodipine has a box and no line on the sheet.

## Reading distance
Hold the virtual phone 90 cm above the table: one photo shows the whole table. The code on a box is 1 cm wide, so at that distance it is only 1.5 to 3.5 pixels per module; the reader enlarges and sharpens small windows to recover it. Say the numbers as measured: about 95 % of the readable codes with a 12 MP camera and 98 % with a 48 MP camera, on synthetic stickers, 0 wrong. Beyond about 1 m it does not work (the lens blur smears the modules), so do not raise the phone higher during the demo. The few that are missed are listed as "not recognised" and the caregiver takes a closer photo or types the code.

## What not to claim
- No "safe plan", "no interactions" or "verified plan in seconds".
- No accuracy figure for real packs (none has been measured). The Blender numbers (98-100 % read at 50 cm or closer) are for perfect labels.
- The candidate flow for packs without a readable code is weak by design (true medicine among the candidates in 3 of 12 small synthetic crops); say that the caregiver always decides.
- Meta API calls send images off the machine; the app asks for consent each time. Show it with a fictional sheet only.

## If something fails live
- CIMA down: packs already seen are served from the local cache; a typed C.N. of an unseen pack needs the network.
- No GPU: SAM 3 step reports an error and typing the C.N. still works.
- No English Windows voice: the voice button is hidden; PDF and `.ics` still work.
