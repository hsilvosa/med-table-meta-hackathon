"""Caregiver app: photo of the packs -> verified packs -> the caregiver's medication sheet -> plan, calendar PDF, voice and .ics.

  .venv-app/Scripts/python.exe -m streamlit run app.py

Nothing is decided here: the code is read from the pack, the medicine comes from AEMPS CIMA, and every dose is typed or
picked by the caregiver and confirmed line by line. Photos stay on this machine; only CN lookups go to the public CIMA API.
"""

import sys
import tempfile
from datetime import date
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))

from medtable import identify, sheet_reader, synthetic, vlm, voice  # noqa: E402
from medtable.calendar_pdf import DISCLAIMER, render_pdf  # noqa: E402
from medtable.findings import NOT_AN_INTERACTION_CHECK, explain_problem  # noqa: E402
from medtable.pipeline import make_plan, manual_pack  # noqa: E402
from medtable.plan import DEFAULT_TIMES, SLOT_LABELS, to_ics  # noqa: E402
from medtable.resolve import Resolver  # noqa: E402
from medtable.schedule import SLOTS  # noqa: E402
from medtable.smpc import Smpc  # noqa: E402

DOSES = ["0", "1/4", "1/2", "3/4", "1", "1,5", "2", "3", "4"]
DEMO_ITEMS = [("654177", "281231"), ("662025", "270430"), ("715240", "250600"), ("677379", "280131"), ("656012", "271130"), ("100008", "281231")]
COLUMNS = ["medicamento", *SLOTS, "observaciones", "confirmado", "cn"]

st.set_page_config(page_title="Plan de medicación", layout="wide")


@st.cache_resource
def resolver() -> Resolver:
    return Resolver()


class CachedSmpc:
    """CIMA sections are cached on disk; this also remembers 'no such section' answers for the session."""

    def __init__(self) -> None:
        self.inner, self.missing = Smpc(), set()

    def section(self, nregistro: str, section: str):
        if (nregistro, section) in self.missing:
            return None
        result = self.inner.section(nregistro, section)
        if result is None:
            self.missing.add((nregistro, section))
        return result


@st.cache_resource
def smpc_source() -> CachedSmpc:
    return CachedSmpc()


def state_defaults() -> None:
    st.session_state.setdefault("readings", {})  # photo name -> list[Reading]
    st.session_state.setdefault("manual", [])
    st.session_state.setdefault("sheet", pd.DataFrame(columns=COLUMNS))
    st.session_state.setdefault("sheet_cns", set())


def add_photo(name: str, image: np.ndarray) -> None:
    with st.spinner(f"Leyendo códigos de {name}..."):
        st.session_state.readings[name] = identify.identify(image, resolver())


def sync_sheet(readings, manual) -> None:
    """Add one empty row per verified pack that is not yet on the sheet; the caregiver only has to fill in the doses."""
    rows = []
    medicines = [r.medicine for r in readings if r.status == "verified" and r.medicine] + [p.medicine for p in manual]
    for m in medicines:
        if m.cn not in st.session_state.sheet_cns:
            st.session_state.sheet_cns.add(m.cn)
            rows.append({"medicamento": m.name, **dict.fromkeys(SLOTS, "0"), "observaciones": "", "confirmado": False, "cn": m.cn})
    if rows:
        st.session_state.sheet = pd.concat([st.session_state.sheet, pd.DataFrame(rows)], ignore_index=True)


state_defaults()
st.title("Plan de medicación")
st.info(DISCLAIMER)

# 1. Packs -------------------------------------------------------------------------------------------------------------
st.header("1. Envases")
left, right = st.columns([3, 2])
with left:
    uploads = st.file_uploader("Fotos de los envases (la cara con el código Data Matrix, lo más cerca posible)", type=["jpg", "jpeg", "png"],
                               accept_multiple_files=True)
    for upload in uploads or []:
        if upload.name not in st.session_state.readings:
            add_photo(upload.name, cv2.imdecode(np.frombuffer(upload.getvalue(), np.uint8), cv2.IMREAD_COLOR))
with right:
    if st.button("Cargar foto de ejemplo (sintética, no son envases reales)"):
        add_photo("ejemplo", synthetic.demo_photo(DEMO_ITEMS))
    typed = st.text_input("O escriba el código nacional impreso en el envase (C.N.)", placeholder="848226.9")
    if st.button("Añadir envase por código nacional") and typed:
        pack, problem = manual_pack(typed, resolver())
        if problem:
            st.error(problem)
        elif pack.medicine.cn not in {p.medicine.cn for p in st.session_state.manual}:
            st.session_state.manual.append(pack)
    if st.button("Empezar de nuevo"):
        for key in ("readings", "manual", "sheet", "sheet_cns"):
            st.session_state.pop(key, None)
        st.rerun()

readings = [r for rs in st.session_state.readings.values() for r in rs]
if not readings and not st.session_state.manual:
    st.caption("Todavía no hay envases. Suba una foto o escriba un código nacional.")
rows = []
for r in readings:
    rows.append({"Estado": "Verificado" if r.status == "verified" else "NO verificado", "Medicamento": r.medicine.name if r.medicine else "-",
                 "C.N.": r.cn or "-", "Caducidad": r.expiry.isoformat() if r.expiry else "-",
                 "Caducado": "SÍ" if r.expired else ("no" if r.expired is not None else "-"), "Motivo": "; ".join(explain_problem(p) for p in r.problems)})
for p in st.session_state.manual:
    rows.append({"Estado": "Indicado por el cuidador (C.N. válido)", "Medicamento": p.medicine.name, "C.N.": p.medicine.cn, "Caducidad": "-", "Caducado": "-", "Motivo": ""})
if rows:
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption("Solo el código del envase identifica un medicamento. Lo que no se pueda verificar no entra en el calendario.")
    shown = [r.medicine for r in readings if r.status == "verified" and r.medicine][:6]
    for col, m in zip(st.columns(max(len(shown), 1)), shown):
        url = m.photos.get("materialas") or m.photos.get("formafarmac")
        if url:
            col.image(url, caption=f"{m.name[:34]} (foto oficial AEMPS)", width=140)
sync_sheet(readings, st.session_state.manual)

# 2. Sheet ---------------------------------------------------------------------------------------------------------------
st.header("2. Hoja de medicación")
st.write("Copie aquí la pauta de la hoja del médico: elija la dosis de cada momento del día y marque **Confirmado** cuando haya comprobado la línea. "
         "La herramienta no propone ni cambia dosis.")
with st.expander("Leer la hoja desde una foto (opcional)"):
    backend = vlm.backend_name()
    if backend == "meta":
        st.warning("Con el modelo de Meta la imagen SALE de este equipo hacia la API de Meta. Úselo solo con hojas sin datos personales "
                   "(sin nombre, DNI ni dirección) o configure el modelo local (`VLM_BACKEND=local`).")
    else:
        st.caption("Modelo local: la imagen no sale de este equipo.")
    sheet_photo = st.file_uploader("Foto de la hoja de medicación", type=["jpg", "jpeg", "png"], key="sheet_photo")
    consent = st.checkbox("Entiendo adónde se envía la imagen y quiero leerla con el modelo", key="sheet_consent") if backend == "meta" else True
    if st.button("Leer la hoja", disabled=not (sheet_photo and consent)):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / sheet_photo.name
            path.write_bytes(sheet_photo.getvalue())
            try:
                with st.spinner("Leyendo la hoja..."):
                    read = sheet_reader.read_sheet(path)
            except Exception as exc:  # network, budget cap, server not running: tell the caregiver, keep manual entry available
                st.error(f"No se pudo leer la hoja ({exc}). Puede escribir la pauta a mano.")
            else:
                known = set(st.session_state.sheet["medicamento"])
                new = [r for r in read.rows if r["medicamento"] not in known]
                st.session_state.sheet = pd.concat([st.session_state.sheet, pd.DataFrame(new, columns=COLUMNS)], ignore_index=True)
                st.session_state.sheet_notes = read.problems + ["Revise cada fila contra la hoja: la lectura puede tener errores."]
    for note in st.session_state.get("sheet_notes", []):
        st.warning(note)
extra_doses = sorted({str(v) for slot in SLOTS for v in st.session_state.sheet[slot].dropna()} - set(DOSES))  # misread cells stay visible
dose_col = lambda label: st.column_config.SelectboxColumn(label, options=DOSES + extra_doses, default="0", required=True, width="small")
edited = st.data_editor(
    st.session_state.sheet, num_rows="dynamic", hide_index=True, width="stretch", key="sheet_editor",
    column_config={"medicamento": st.column_config.TextColumn("Medicamento (como en la hoja)", required=True, width="large"),
                   **{s: dose_col(SLOT_LABELS[s]) for s in SLOTS},
                   "observaciones": st.column_config.TextColumn("Observaciones (p. ej. «con las comidas»)", width="medium"),
                   "confirmado": st.column_config.CheckboxColumn("Confirmado", default=False),
                   "cn": st.column_config.TextColumn("C.N.", disabled=True, width="small")})
records = [{k: ("" if pd.isna(v) else v) for k, v in row.items()} for row in edited.to_dict("records")]
for record in records:
    record["cn"] = record.get("cn") or None
    record["confirmado"] = bool(record.get("confirmado"))

# 3. Plan ----------------------------------------------------------------------------------------------------------------
st.header("3. Plan")
use_smpc = st.checkbox("Consultar las fichas técnicas de AEMPS CIMA (secciones 4.2 y 4.5) para citar menciones", value=True)
with st.spinner("Preparando el plan..."):
    result = make_plan(readings, st.session_state.manual, records, smpc_source() if use_smpc else None, date.today())
plan = result.plan

review = [f for f in plan.findings if f.kind not in ("unverified_item",) and f.severity == "review"]
info = [f for f in plan.findings if f.kind not in ("unverified_item",) and f.severity == "info"]
if review:
    st.subheader("Para revisar con su farmacéutico")
    for f in review:
        st.warning(f.text("es"))
        if f.source:
            st.caption(f"Fuente: {f.source}")
if info:
    with st.expander(f"Información adicional ({len(info)})"):
        for f in info:
            st.write(f.text("es"))
            if f.source:
                st.caption(f"Fuente: {f.source}")
st.caption("Se han revisado: principio activo duplicado, mismo grupo ATC, caducidad, coincidencia con la hoja y citas literales de las secciones 4.2 y 4.5. "
           + NOT_AN_INTERACTION_CHECK["es"].replace("No se encontró ninguna mención en las secciones revisadas. ", "")
           + " La ausencia de avisos no significa que el plan sea seguro.")

if plan.entries:
    table = {SLOT_LABELS[s]: ["; ".join(f"{e.written()} de {e.name}" for e in plan.slot_entries(s)) or "-"] for s in SLOTS}
    st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch")
else:
    st.caption("El plan está vacío: confirme al menos una línea de la hoja que coincida con un envase verificado.")
if plan.not_included:
    st.subheader("No incluido en el calendario")
    for what, why in plan.not_included:
        st.error(f"{what}: {why}")

patient = st.text_input("Nombre del paciente (opcional, solo para el papel)")
with st.expander("Horas de los recordatorios (.ics)"):
    times = {s: st.time_input(SLOT_LABELS[s], value=pd.to_datetime(DEFAULT_TIMES[s]).time(), key=f"t_{s}").strftime("%H:%M") for s in SLOTS}
if plan.entries:
    with tempfile.TemporaryDirectory() as tmp:
        pdf_bytes = render_pdf(plan, Path(tmp) / "plan.pdf", patient).read_bytes()
    c1, c2 = st.columns(2)
    c1.download_button("Descargar calendario (PDF)", pdf_bytes, "plan_medicacion.pdf", "application/pdf")
    c2.download_button("Descargar recordatorios (.ics)", to_ics(plan, times).encode("utf-8"), "plan_medicacion.ics", "text/calendar")
    if voice.available():
        if st.button("Generar versión en voz"):
            with tempfile.TemporaryDirectory() as tmp:
                for slot, path in voice.render_voice(plan, Path(tmp)).items():
                    st.write(SLOT_LABELS[slot])
                    st.audio(path.read_bytes(), format="audio/wav")
    else:
        st.caption("La voz sin conexión necesita una voz en español de Windows; no está disponible en este equipo.")
