"""Render a FICTIONAL active-medication sheet (Spanish) and degrade it like a phone photo.

  python experiments/make_fictional_sheet.py        # writes experiments/out/sheet.jpg and sheet_truth.json

The table has the kinds of cells that are easy to misread: "1/2", "0,5", free-text remarks, empty remarks.
Nothing here is a real prescription.
"""

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

OUT = Path("experiments/out")
OUT.mkdir(parents=True, exist_ok=True)
FONTS = Path("C:/Windows/Fonts")
font = lambda name, size: ImageFont.truetype(str(FONTS / name), size)  # noqa: E731

COLUMNS = [("Medicamento", 40), ("Desay.", 560), ("Comida", 670), ("Cena", 780), ("Acost.", 890), ("Observaciones", 1000)]
ROWS = [  # medicine text, breakfast, lunch, dinner, bedtime, remarks
    ("Repaglinida 0,5 mg comprimidos", "1", "1", "1", "0", "15 min antes de comer"),
    ("Valsartan/Hidroclorotiazida 160/12,5 mg", "1", "0", "0", "0", "por la manana"),
    ("Metformina 850 mg comprimidos", "1", "0", "1", "0", "con las comidas"),
    ("Lorazepam 1 mg comprimidos", "0", "0", "0", "1/2", "solo si insomnio"),
    ("Omeprazol 20 mg capsulas", "1", "0", "0", "0", "en ayunas"),
    ("Paracetamol 1 g comprimidos", "1", "0", "1", "0", "cada 8 horas si dolor"),
    ("Atorvastatina 20 mg comprimidos", "0", "0", "0", "1", ""),
]
W, H = 1260, 1000

page = Image.new("RGB", (W, H), (252, 252, 250))
draw = ImageDraw.Draw(page)
draw.text((40, 30), "PLAN DE MEDICACION ACTIVO - DOCUMENTO FICTICIO (PRUEBA)", font=font("arialbd.ttf", 28), fill=(20, 20, 20))
draw.text((40, 75), "Paciente: PACIENTE DE PRUEBA    Fecha: 26/10/2026    Medico: Dr. Ejemplo", font=font("arial.ttf", 22), fill=(30, 30, 30))
y = 130
for title, x in COLUMNS:
    draw.text((x, y), title, font=font("arialbd.ttf", 22), fill=(0, 0, 0))
draw.line((30, y + 34, W - 30, y + 34), fill=(0, 0, 0), width=2)
y += 50
for row in ROWS:
    for (_, x), text in zip(COLUMNS, row):
        draw.text((x, y), text, font=font("arial.ttf", 22), fill=(15, 15, 15))
    draw.line((30, y + 38, W - 30, y + 38), fill=(190, 190, 190), width=1)
    y += 62
draw.text((40, y + 20), "Revise esta pauta con su farmaceutico o medico. Documento sin validez real.", font=font("ariali.ttf", 20), fill=(60, 60, 60))

# phone-photo degradations: slight rotation and perspective, uneven light, blur, sensor noise
img = cv2.cvtColor(np.array(page), cv2.COLOR_RGB2BGR)
img = cv2.warpAffine(img, cv2.getRotationMatrix2D((W / 2, H / 2), 2.2, 0.96), (W, H), borderValue=(120, 125, 130))
corners = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
tilted = np.float32([[18, 10], [W - 5, 0], [W - 25, H - 8], [0, H - 20]])
img = cv2.warpPerspective(img, cv2.getPerspectiveTransform(corners, tilted), (W, H), borderValue=(120, 125, 130))
light = 0.82 + 0.25 * np.tile(np.linspace(0, 1, W), (H, 1))
img = cv2.GaussianBlur(img * light[..., None], (0, 0), 0.9) + np.random.default_rng(3).normal(0, 4, img.shape)
cv2.imwrite(str(OUT / "sheet.jpg"), img.clip(0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 85])
json.dump([{"medicamento": r[0], "pauta": list(r[1:5]), "observaciones": r[5]} for r in ROWS],
          (OUT / "sheet_truth.json").open("w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("wrote", OUT / "sheet.jpg", "with", len(ROWS), "rows")
