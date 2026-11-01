# Demo script (about 3 minutes)

Run `.venv-app/Scripts/python.exe scripts/start_demo.py`: it opens the 3D room (http://127.0.0.1:8600) with the planner app in its right-hand panel. Use only the synthetic demo photo, invented doses and public CIMA data. Never show a real prescription or a real patient name.

| Time | Do | Say (the point to land) |
|---|---|---|
| 0:00 | Open the room: the left panel always shows the three steps and the keys. Point at the blue notice in the planner (Tab shows it) | It supports the caregiver and does not replace the doctor or the pharmacist. It schedules; it does not advise. |
| 0:20 | In the room, left panel: "Table 1", "Raise the phone over Table 1" (90 cm above it, the whole table in view; the distance dot turns green; after a moment green boxes appear on the codes it can read, amber if a code is read but not verified: a preview to help aim), "Take photo" (the 48 MP camera takes about 6 s; Space does the same) | The packs are identified by the code printed on them, nothing else. The photo reaches the planner by itself and is read in a few seconds. |
| 0:50 | Step 1 lists the medicines found: expiry read from the code, one expired pack (enalapril); each card has a bin button ("Remove this medicine") for a wrong or unwanted box. Open "A box with no readable code?" and run it for the atorvastatin box | A model only suggests; the caregiver confirms against the official picture. Nothing enters the plan on its own. |
| 1:10 | Step 2: type a name; open "Have a photo of the doctor's schedule?", upload `experiments/out/sheet.jpg`, tick the consent, "Read the schedule"; check a few lines against the paper and tick "Yes, this matches the doctor's schedule" | The doses are the caregiver's. The computer copied the paper, the caregiver confirms line by line; nothing is ticked for them. Unticked lines stay out. |
| 1:40 | Step 3: the plan, the "Left out" cards (each says what to do) and "To ask your pharmacist" | Anything unverified, expired, unconfirmed, ambiguous or with a strength that does not match is listed with the reason. Quotes from the AEMPS leaflet (4.5 and 4.2) are verbatim, with the source. |
| 2:10 | Step 4: add a note for the whole plan, look at the preview, download the PDF | Page 1 is for the fridge: pictograms, times, large print, official pack photo, notes. Page 2 is for the pharmacist: what was left out, the quotes and the sources. |
| 2:30 | "Read the plan aloud"; play one slot | Offline voice (English, or Spanish with Settings > Language); the text never leaves the machine. The same screen has the weekly pill organiser sheet. |
| 2:45 | Show the `.ics` file import (optional) | Daily reminders on the phone. |
| 2:55 | Close | Measured on synthetic data only, so no accuracy claim for real use yet; real photos are the next step. |

## What the 3D room is
A stage set: flat cut-outs of the official CIMA photos with a Data Matrix sticker that this repository generates from each medicine's real Codigo Nacional. Say so. It shows the flow and measures the optics (read rate by distance), not how real printed codes behave. Built-in cases to point at: an expired pack, one expiring within a month, a code CIMA does not know (stays unverified), packs with no visible code (SAM + candidates, the caregiver decides), loose pills (never identified), and the fictional medication sheet on table 1, which lists most of the boxes of tables 1 and 2 plus one medicine that has no box (bisoprolol); amlodipine has a box and no line on the sheet.

## Reading distance
Hold the virtual phone 90 cm above the table: one photo shows the whole table. The code on a box is 1 cm wide, so at that distance it is only 1.5 to 3.5 pixels per module; the reader enlarges and sharpens small windows to recover it. Say the numbers as measured: about 95 % of the readable codes with a 12 MP camera and 98 % with a 48 MP camera, on synthetic stickers, 0 wrong. Beyond about 1 m it does not work (the lens blur smears the modules), so do not raise the phone higher during the demo. The few that are missed are listed as "not recognised" and the caregiver takes a closer photo or types the code.

## Live scan (preview)
With the phone held still, the room sends a frame to the local server every couple of seconds. It runs the same decoder and the same three checks as the planner (readable code, valid national code, known to CIMA). While it scans, a green bar sweeps the view and each box appears the moment its code is found (the server answers after the plain read and after each zoom pass), with a short pop. Green box: verified. Amber: read but not verified. No box: not read. The boxes disappear when you move and come back when you hold still. They are a preview to help aim: only the photo goes to the planner, and a box that is missing in the preview can still be read in the 48 MP photo (the preview uses a 12 MP frame and the two faster scan passes). The tick box "Live scan" turns it off.

## Boxes with no code read
If the preview sees a pack but reads no code from it, it draws an amber dashed box on it: "No code read: move closer or add it by hand". The button "Close-up of the box with no code" in the left panel puts the phone 35 cm above that pack; hold still and the code usually reads (green box), then take the photo. A pack with no printed code at all (atorvastatin in the room) stays amber and has to be added by hand in the planner. The planner also shows a card for each such pack ("A box where I could not read a code") with a crop and the same advice; "Done" removes the card. The finder only works on a table of a middle tone: do not demo it on a white table. An amber box is a hint, not a diagnosis, and a missing one proves nothing.

## Camera demo (a separate demo)
`.venv-app/Scripts/python.exe scripts/start_camera.py`, then http://127.0.0.1:8700/camera.html. "Start the camera" (the browser asks for permission), hold the device still over the boxes: the preview works exactly as in the room (green boxes, amber boxes, the dashed amber box for a pack with no code read) and "Take the photo" (or Space) sends the full-size photo to the planner in the side panel. Without a camera, "Use a photo as the camera" shows the same flow with any picture.
- **Resolution decides the distance.** A frame 4000 px wide needs the camera about 90 cm above the boxes; a 1920 px (1080p) webcam about 45 cm; a 1280 px one about 30 cm (the page says it). This is scaled from the room: 2000 px wide frames read 100 % of the codes closer than 0.5 m and 62 % at 0.5-0.75 m (`experiments/live_scan_probe.py`). A phone browser usually gives video of 1080p or 4K and, on Android Chrome, a full-resolution still for the photo; on iPhone Safari the photo has the resolution of the video.
- **Bad light, shake, distance.** The page does not guess: a line under the picture tells what to do (closer, more light, hold steady, turn the boxes) and, if asked, says it aloud; "Zoom +" and "Light" appear on cameras that have them. Simulated conditions are in `experiments/README.md` ("Conditions"): a dark or grainy view is read much better from four frames averaged than from one.
- **Not measured on a real camera.** No physical webcam or phone was available while this was built. It was tested with a simulated camera stream (a picture played as video, to exercise the video path, the motion detection and the shutter) and with the stand-in photo. Real lenses focus, blur and move differently from the room's simulated phone: do a trial run on the day, with the boxes you will show. Autofocus lag and glare on glossy cartons are the likely problems.
- **Phone:** `start_camera.py --lan --https`. A phone browser only opens the camera on a secure page, hence the self-signed certificate (a warning, once). The servers then listen on the local network: use it at home and stop it afterwards. The planner has no https, so on a phone it opens in a second tab and loads each new photo by itself; this phone path has not been tried on a phone.

## What not to claim
- No "safe plan", "no interactions" or "verified plan in seconds".
- No accuracy figure for real packs (none has been measured). The Blender numbers (98-100 % read at 50 cm or closer) are for perfect labels.
- The candidate flow for packs without a readable code is weak by design (true medicine among the candidates in 3 of 12 small synthetic crops); say that the caregiver always decides.
- Meta API calls send images off the machine; the app asks for consent each time. Show it with a fictional sheet only.

## If the camera fails live
Use "Use a photo as the camera" with a photo of the boxes, or type the codes in the planner. If the camera is blocked, allow it with the icon in the address bar.

## If something fails live
- CIMA down: packs already seen are served from the local cache; a typed C.N. of an unseen pack needs the network.
- No GPU: SAM 3 step reports an error and typing the C.N. still works.
- No Windows voice in the chosen language: the voice button is hidden; PDF and `.ics` still work.
