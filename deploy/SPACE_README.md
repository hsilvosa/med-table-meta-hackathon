---
title: med-table
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
short_description: Verified medication plan from a photo of the boxes
---

# med-table: online demo

Photograph the medicine boxes on the table, get a medication plan you can trust. Each box is identified from the official code printed
on it and checked against Spain's medicines database (AEMPS CIMA); the caregiver confirms every dose; the plan becomes a large-print
calendar, a weekly pill organiser guide and phone reminders. Built with Meta's Muse Spark and SAM 3.

**Not medical advice.** A planning aid for caregivers; it never decides a dose and is not a medical device.

**A shared public demo.** Use the demo photo or the 3D room; do not upload photos of real prescriptions or of anything showing personal
data. In this online version the voice, the reading of the doctor's schedule with Muse Spark and SAM 3 are turned off, and so is the
camera page; they run in the local installation.

Source code and full documentation: https://github.com/hsilvosa/med-table-meta-hackathon. Medicine information and photos: AEMPS CIMA,
https://cima.aemps.es (source and date in `demo_cache/SOURCE.md` and `web/world_demo/SOURCE.md`).
