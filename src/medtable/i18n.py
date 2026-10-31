"""Interface language: English (the default, and the language of the code) or Spanish.

The English text is the key: `tr("Expires on {x0}", x0=day)` returns the Spanish text when the session language is Spanish and the
English text otherwise. Medicine names, SmPC quotes and anything that comes from CIMA are never translated: they are shown as AEMPS
wrote them. Internal reasons (the strings the code compares) stay English; they are translated only when shown, with `tr_reason`.
The language is per thread: Streamlit runs each session's script in its own thread, and app.py sets it at the start of every run.
"""

from __future__ import annotations

import re
import threading
from datetime import date

LANGUAGES = {"en": "English", "es": "Español"}
VOICE_CULTURE = {"en": "en-US", "es": "es-ES"}
_state = threading.local()


def set_language(code: str) -> None:
    _state.code = code if code in LANGUAGES else "en"


def language() -> str:
    return getattr(_state, "code", "en")


def tr(text: str, **values) -> str:
    out = ES.get(text, text) if language() == "es" else text
    return out.format(**values) if values else out


MONTHS_ES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def date_text(day: date) -> str:
    """'26 Oct 2026' / '26 oct 2026'."""
    return f"{day.day} {MONTHS_ES[day.month - 1]} {day.year}" if language() == "es" else day.strftime("%d %b %Y")


REASONS_ES = (      # reasons built with a value inside (plan.build_plan, findings.explain_problem)
    (r"the pack expired on (.+)", r"la caja caducó el \1"),
    (r"unrecognised dose: (.+)", r"cantidad no reconocida: \1"),
)


def tr_reason(text: str) -> str:
    if language() != "es":
        return text
    if text in ES:
        return ES[text]
    for pattern, spanish in REASONS_ES:
        if re.fullmatch(pattern, text):
            return re.sub(pattern, spanish, text)
    return text


ES = {
    # ---- app.py and shared parts -------------------------------------------------------------------------------------------
    "Medication planner": "Planificador de medicación",
    "Settings": "Ajustes",
    "Public online demo": "Demo pública en línea",
    "Try it with the demo photo or the 3D room. Do not upload photos of real prescriptions or of anything showing a name, address or ID number: pictures are processed on a shared server (photos from the 3D room are deleted after an hour). This is a planning aid, not medical advice. In this online version the voice, reading the doctor's schedule with Muse Spark and SAM 3 are turned off; they run in the local installation (<a href=\"https://github.com/hsilvosa/med-table-meta-hackathon\" target=\"_blank\">source code</a>).":
        "Pruébela con la foto de prueba o con la sala 3D. No suba fotos de recetas reales ni de nada que muestre un nombre, una dirección o un DNI: las imágenes se procesan en un servidor compartido (las fotos de la sala 3D se borran al cabo de una hora). Es una ayuda para organizarse, no consejo médico. En esta versión en línea están desactivados la voz, la lectura de la pauta con Muse Spark y SAM 3; funcionan en la instalación local (<a href=\"https://github.com/hsilvosa/med-table-meta-hackathon\" target=\"_blank\">código fuente</a>).",
    "Language": "Idioma",
    "Larger text": "Letra más grande",
    "Quote the official leaflets (AEMPS) in the notes": "Citar las fichas técnicas oficiales (AEMPS) en las notas",
    "When off, only the checks that need no leaflet text run, and the plan says so.":
        "Si se desactiva, solo se hacen las comprobaciones que no necesitan la ficha técnica, y el plan lo indica.",
    "Start over": "Empezar de nuevo",
    "Start over?": "¿Empezar de nuevo?",
    "This deletes the medicines, the doses and the notes of this plan. It cannot be undone.":
        "Se borran los medicamentos, las dosis y las notas de este plan. No se puede deshacer.",
    "No, keep my work": "No, conservar mi trabajo",
    "Yes, delete everything": "Sí, borrar todo",
    "Medicines": "Medicamentos", "Doses": "Dosis", "Check": "Revisar", "Print and listen": "Imprimir y escuchar",
    "morning": "mañana", "midday": "mediodía", "evening": "tarde-noche", "before sleep": "antes de dormir",
    "Breakfast": "Desayuno", "Lunch": "Comida", "Dinner": "Cena", "Bedtime": "Al acostarse",
    "Mon": "Lun", "Tue": "Mar", "Wed": "Mié", "Thu": "Jue", "Fri": "Vie", "Sat": "Sáb", "Sun": "Dom",
    "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles", "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo",
    "None": "Nada", "Other": "Otra",
    "With food": "Con comida", "Before meals": "Antes de las comidas", "On an empty stomach": "En ayunas", "Only if needed": "Solo si hace falta",
    "Swallow whole": "Tragar entero",
    "tablet": "comprimido", "tablets": "comprimidos", "capsule": "cápsula", "capsules": "cápsulas", "suppository": "supositorio",
    "suppositories": "supositorios", "sachet": "sobre", "sachets": "sobres", "patch": "parche", "patches": "parches", "dose": "dosis", "doses": "dosis",
    "medicine": "medicamento", "medicines": "medicamentos", "box": "caja", "boxes": "cajas", "code": "código", "codes": "códigos",
    "Back": "Atrás",
    "the box I could not recognise": "la caja que no pude reconocer",
    "the medicine": "el medicamento",
    "Plan opened": "Plan abierto",
    "Saved on {x0}. Every box was checked again with the official database. Check that the doses still match the doctor's paper, and add a photo of any new box.":
        "Guardado el {x0}. Todas las cajas se han vuelto a comprobar con la base de datos oficial. Compruebe que las dosis siguen coincidiendo con el papel del médico y añada una foto de cada caja nueva.",
    "The plan could not be opened": "No se pudo abrir el plan",
    "Who is this plan for? (optional)": "¿Para quién es este plan? (opcional)",
    "For example: Maria Lopez": "Por ejemplo: María López",
    "Printed at the top of the calendar. Leave it empty to write the name by hand.":
        "Se imprime arriba del calendario. Déjelo vacío para escribir el nombre a mano.",
    '<div class="mt-pic none">No picture</div>': '<div class="mt-pic none">Sin foto</div>',
    "Go back to Medicines and add a photo that shows this box, or type the code printed on it.":
        "Vuelva a Medicamentos y añada una foto en la que se vea esta caja, o escriba el código impreso en ella.",
    "Do not use it. Ask a pharmacist for a new pack.": "No la use. Pida una caja nueva en la farmacia.",
    "Go back to Doses and keep one line for this medicine.": "Vuelva a Dosis y deje una sola línea para este medicamento.",
    "Go back to Doses and write the name of the medicine the way it appears on the box.":
        "Vuelva a Dosis y escriba el nombre del medicamento tal como aparece en la caja.",
    "Compare the strength on the box with the doctor's paper and correct the line.":
        "Compare la dosis que pone en la caja con el papel del médico y corrija la línea.",
    "Go back to Doses and choose the amount with the buttons.": "Vuelva a Dosis y elija la cantidad con los botones.",
    '{x0}. <a href="{x1}" target="_blank">Open the official page</a>': '{x0}. <a href="{x1}" target="_blank">Abrir la página oficial</a>',
    "Expiry date unknown": "Caducidad desconocida",
    "Expired on {x0}": "Caducó el {x0}",
    "Expires on {x0}": "Caduca el {x0}",
    "no day chosen": "ningún día elegido",
    " only": " solamente",
    "Reading the codes in {name} (a few seconds)...": "Leyendo los códigos de {name} (unos segundos)...",
    "No connection to the official database": "Sin conexión con la base de datos oficial",
    "I read {x0} but could not check {x1} with AEMPS CIMA. Check the internet connection, then press <b>Try again</b> below.":
        "He leído {x0}, pero no he podido comprobarlos con AEMPS CIMA. Revise la conexión a internet y pulse <b>Reintentar</b> abajo.",
    "it": "lo", "them": "los",
    "I could not read any code in this photo": "No he podido leer ningún código en esta foto",
    "Put the boxes with the printed code facing up, use good light, and take the photo closer (about 30 to 90 cm above the boxes).":
        "Ponga las cajas con el código impreso hacia arriba, con buena luz, y haga la foto más cerca (entre 30 y 90 cm por encima de las cajas).",
    " On a white table I cannot point out boxes without a code: check by eye that every box is in the list.":
        " En una mesa blanca no puedo señalar las cajas sin código: compruebe a simple vista que todas están en la lista.",
    "Photo read": "Foto leída",
    ". The list below shows them.": ". Aparecen en la lista de abajo.",
    " recognised": " reconocido(s)",
    " I could not recognise": " que no pude reconocer",
    " where I could not read a code": " en las que no pude leer el código",
    # ---- what changed since a saved plan -----------------------------------------------------------------------------------
    "<li><b>New:</b> {x0}</li>": "<li><b>Nuevo:</b> {x0}</li>",
    "<li><b>Not seen in the new photos:</b> {x0}. Is it still taken? If not, remove it.</li>":
        "<li><b>No aparece en las fotos nuevas:</b> {x0}. ¿Lo sigue tomando? Si no, quítelo.</li>",
    "What changed since the plan saved on {x0}": "Qué ha cambiado desde el plan guardado el {x0}",
    '<ul style="margin:.3rem 0 0 1.1rem;padding:0">{x0}</ul><div class="mt-meta">Check each change against the doctor\'s paper.</div>':
        '<ul style="margin:.3rem 0 0 1.1rem;padding:0">{x0}</ul><div class="mt-meta">Compruebe cada cambio con el papel del médico.</div>',
    "every day": "todos los días", "no day": "ningún día",
    "Days: {x0} -> {x1}": "Días: {x0} -> {x1}",
    # ---- medicine cards ----------------------------------------------------------------------------------------------------
    '<div class="mt-meta">Active ingredient: {x0}</div>': '<div class="mt-meta">Principio activo: {x0}</div>',
    '<div class="mt-alert">This box has expired. Do not use it: it will be left out of the plan.</div>':
        '<div class="mt-alert">Esta caja está caducada. No la use: quedará fuera del plan.</div>',
    '<div class="mt-alert">{x0} of {x1} boxes have expired. Do not use the expired one.</div>':
        '<div class="mt-alert">{x0} de {x1} cajas están caducadas. No use la caducada.</div>',
    '<div class="mt-heads">Same active ingredient as: {x0}. The plan lists it for the pharmacist.</div>':
        '<div class="mt-heads">Mismo principio activo que: {x0}. El plan lo indica para el farmacéutico.</div>',
    # ---- screen 1 ----------------------------------------------------------------------------------------------------------
    "Show me the medicines": "Enséñeme los medicamentos",
    "Take a photo of the medicine boxes on the table. I read the code printed on each box.":
        "Haga una foto de las cajas de medicamentos sobre la mesa. Leo el código impreso en cada caja.",
    "This is a helper for planning. It gives no medical advice and does not replace the doctor or the pharmacist.":
        "Esto es una ayuda para organizarse. No da consejo médico y no sustituye al médico ni al farmacéutico.",
    '<p class="mt-title" style="font-size:1.35rem;margin-top:1.2rem">Medicines found: {x0}</p>':
        '<p class="mt-title" style="font-size:1.35rem;margin-top:1.2rem">Medicamentos encontrados: {x0}</p>',
    "Next: choose the doses": "Siguiente: elegir las dosis",
    "Add a medicine another way": "Añadir un medicamento de otra forma",
    "For a good photo": "Para una buena foto",
    "Put the boxes on a table with the printed codes facing up, and hold the phone about 90 cm (3 feet) above them or closer.":
        "Ponga las cajas sobre una mesa con los códigos impresos hacia arriba y sujete el móvil a unos 90 cm por encima, o más cerca.",
    "Removed: {x0}": "Quitado: {x0}",
    "Removed by mistake? Press the button to put it back.": "¿Lo quitó por error? Pulse el botón para volver a ponerlo.",
    "Undo: put it back": "Deshacer: volver a ponerlo",
    "Nothing yet": "Todavía nada",
    "Add a photo or type a code above. The medicines I recognise will appear here.":
        "Añada una foto o escriba un código arriba. Los medicamentos que reconozca aparecerán aquí.",
    "Is a box missing? Take another photo that shows it close up with its code facing up, or type its code. Wrong box? Remove it.":
        "¿Falta una caja? Haga otra foto de cerca con el código hacia arriba, o escriba su código. ¿Una caja equivocada? Quítela.",
    "A box has no code I can read? Find it in the photo and choose it from the database":
        "¿Una caja sin código legible? Búsquela en la foto y elíjala en la base de datos",
    "The computer looks for boxes in the photo that have no readable code and suggests possible medicines from the official database. **Nothing enters the plan until you choose one and confirm it against the official picture.**":
        "El ordenador busca en la foto cajas sin código legible y propone posibles medicamentos de la base de datos oficial. **Nada entra en el plan hasta que usted elija uno y lo confirme con la foto oficial.**",
    "Look for boxes without a code": "Buscar cajas sin código",
    "Add at least one medicine to continue.": "Añada al menos un medicamento para continuar.",
    "Take the photo with the camera": "Haga la foto con la cámara",
    "Point the camera at the boxes and press the red <b>Take photo</b> button. The photo appears here by itself in a few seconds.":
        "Apunte la cámara a las cajas y pulse el botón rojo <b>Take photo</b>. La foto aparece aquí sola en unos segundos.",
    "Take the photo in the room": "Haga la foto en la sala",
    "Press the red <b>Take photo</b> button on the left of the room. The photo appears here by itself in a few seconds.":
        "Pulse el botón rojo <b>Take photo</b> a la izquierda de la sala. La foto aparece aquí sola en unos segundos.",
    "Upload a photo": "Subir una foto", "Type a code": "Escribir un código", "Open a saved plan": "Abrir un plan guardado", "Demo photos": "Fotos de prueba",
    "A plan saved before with **Save this plan** (on the last screen). The boxes are checked again with the official database.":
        "Un plan guardado antes con **Guardar este plan** (en la última pantalla). Las cajas se vuelven a comprobar con la base de datos oficial.",
    "Choose the saved plan (a .json file)": "Elija el plan guardado (un archivo .json)",
    "Photos made for trying the tool. They contain no real medication or patient.":
        "Fotos hechas para probar la herramienta. No contienen medicación ni pacientes reales.",
    "Load a demo photo": "Cargar una foto de prueba",
    "room": "sala", "camera": "cámara",
    "Load the latest {x0} photo": "Cargar la última foto ({x0})",
    "The latest {x0} photo could not be opened.": "No se pudo abrir la última foto ({x0}).",
    "Choose a photo of the boxes (JPG or PNG)": "Elija una foto de las cajas (JPG o PNG)",
    "{x0} could not be opened as a picture. Use a JPG or PNG file (iPhone HEIC photos must be converted first).":
        "{x0} no se pudo abrir como imagen. Use un archivo JPG o PNG (las fotos HEIC del iPhone hay que convertirlas antes).",
    "Every box has a national code (C.N.) printed on it: six or seven digits, for example 848226.9.":
        "Cada caja lleva impreso un código nacional (C.N.): seis o siete cifras, por ejemplo 848226.9.",
    "The code on the box": "El código de la caja",
    "Add this medicine": "Añadir este medicamento",
    "{x0} is already in the list.": "{x0} ya está en la lista.",
    "Added": "Añadido",
    ". It is in the list below.": ". Está en la lista de abajo.",
    "Photos used so far ({x0})": "Fotos usadas hasta ahora ({x0})",
    "Remove": "Quitar",
    "Recognised from its code": "Reconocido por su código",
    "{x0} boxes": "{x0} cajas",
    "Remove this medicine": "Quitar este medicamento",
    "Added by you": "Añadido por usted",
    '<div class="mt-name">A box I could not recognise</div>{x0}<div class="mt-meta">{x1}</div>':
        '<div class="mt-name">Una caja que no pude reconocer</div>{x0}<div class="mt-meta">{x1}</div>',
    "Not in the plan": "Fuera del plan",
    "reason unknown": "motivo desconocido",
    "Try again": "Reintentar",
    "Dismiss": "Descartar",
    '<div class="mt-name">A box where I could not read a code</div>{x0}<div class="mt-meta">Take a close-up photo of this box (about 30 cm above it, the printed code facing up), or type the code printed on it. ':
        '<div class="mt-name">Una caja en la que no pude leer el código</div>{x0}<div class="mt-meta">Haga una foto de cerca de esta caja (a unos 30 cm, con el código impreso hacia arriba), o escriba el código impreso en ella. ',
    "Not in the plan yet": "Todavía fuera del plan",
    "Bring the camera closer to this box, then press <b>Take photo</b>. ": "Acerque la cámara a esta caja y pulse <b>Take photo</b>. ",
    "In the room, press <b>Close-up of the box with no code</b> on the left, then <b>Take photo</b>. ":
        "En la sala, pulse <b>Close-up of the box with no code</b> a la izquierda y luego <b>Take photo</b>. ",
    "I may be wrong: it can also be something that is not a medicine.</div>": "Puedo equivocarme: puede ser algo que no es un medicamento.</div>",
    "Done: I added it or it is not a medicine": "Hecho: lo añadí o no es un medicamento",
    "Looking for boxes in {name} (about 30 seconds)...": "Buscando cajas en {name} (unos 30 segundos)...",
    "This step could not run ({exc}). You can type the code on the box instead.": "Este paso no se pudo hacer ({exc}). Puede escribir el código de la caja.",
    "Box {x0}": "Caja {x0}",
    "I understand this small picture is sent to the Meta API (only do this if it shows no personal data)":
        "Entiendo que esta pequeña imagen se envía a la API de Meta (hágalo solo si no muestra datos personales)",
    "Suggest medicines": "Proponer medicamentos",
    "Asking the model and the official database...": "Consultando al modelo y a la base de datos oficial...",
    "The model could not be reached ({exc}).": "No se pudo contactar con el modelo ({exc}).",
    "no clear match": "sin coincidencia clara",
    "Which medicine is this?": "¿Qué medicamento es?",
    "None of these / I do not know": "Ninguno de estos / No lo sé",
    "{x0} (official picture)": "{x0} (foto oficial)",
    "Yes, this is the medicine": "Sí, es este medicamento",
    # ---- screen 2 ----------------------------------------------------------------------------------------------------------
    "Choose the doses": "Elija las dosis",
    "For each medicine, choose <b>how many to take</b> at each time of day, as written on the doctor's paper. Then tick the box under it. I never choose an amount for you, and medicines that are not ticked stay out of the plan.":
        "Para cada medicamento, elija <b>cuántos tomar</b> en cada momento del día, como pone en el papel del médico. Después marque la casilla de debajo. Nunca elijo una cantidad por usted, y los medicamentos sin marcar quedan fuera del plan.",
    "{ready} of {x1} ready for the plan": "{ready} de {x1} listos para el plan",
    "Have a photo of the doctor's schedule? Let the computer copy it (optional)":
        "¿Tiene una foto de la pauta del médico? Deje que el ordenador la copie (opcional)",
    "The photo LEAVES this computer and goes to the Meta API. Use it only for a sheet without personal data (no name, ID number or address). To keep it on this computer, whoever installed the tool can switch it to the offline model (VLM_BACKEND=local).":
        "La foto SALE de este ordenador y va a la API de Meta. Úsela solo con una hoja sin datos personales (sin nombre, DNI ni dirección). Para que no salga del ordenador, quien instaló la herramienta puede cambiar al modelo sin conexión (VLM_BACKEND=local).",
    "Local model: the picture does not leave this computer.": "Modelo local: la imagen no sale de este ordenador.",
    "Photo of the schedule": "Foto de la pauta",
    "I understand where the picture is sent and want the computer to read it": "Entiendo adónde se envía la imagen y quiero que el ordenador la lea",
    "Read the schedule": "Leer la pauta",
    "Read the latest {x0} photo as the schedule": "Leer la última foto ({x0}) como pauta",
    "Reading the schedule...": "Leyendo la pauta...",
    "The schedule could not be read ({exc}). You can choose the doses by hand below.": "No se pudo leer la pauta ({exc}). Puede elegir las dosis a mano abajo.",
    "Check every medicine against the paper: a computer reading can contain mistakes.":
        "Compruebe cada medicamento con el papel: una lectura del ordenador puede tener errores.",
    "Box on the table": "Caja en la mesa",
    "No matching box in the photos": "Ninguna caja de las fotos coincide",
    '<div class="mt-alert">The box has expired: this medicine will be left out of the plan until there is a new box.</div>':
        '<div class="mt-alert">La caja está caducada: este medicamento quedará fuera del plan hasta que haya una caja nueva.</div>',
    '<div class="mt-meta">The schedule says: {x0}</div>': '<div class="mt-meta">La pauta dice: {x0}</div>',
    '<div class="mt-alert">Please check: {big:g} a day is more than usual for one medicine. Compare it with the doctor\'s paper.</div>':
        '<div class="mt-alert">Revíselo: {big:g} al día es más de lo habitual para un medicamento. Compárelo con el papel del médico.</div>',
    "Ready for the plan": "Listo para el plan",
    '<div class="mt-meta">Note: {x0}</div>': '<div class="mt-meta">Nota: {x0}</div>',
    "Change the amounts": "Cambiar las cantidades",
    "how many {plural}?": "¿número de {plural}?",
    "how many?": "¿qué cantidad?",
    "Type the amount (for example 4 or 2,5)": "Escriba la cantidad (por ejemplo 4 o 2,5)",
    "Which days?": "¿Qué días?",
    "Every day": "Todos los días",
    "Only some days of the week": "Solo algunos días de la semana",
    "Tick the days it is taken": "Marque los días en que se toma",
    '<p class="mt-hint">Tick at least one day.</p>': '<p class="mt-hint">Marque al menos un día.</p>',
    "Add a note to print next to this medicine (optional)": "Añadir una nota para imprimir junto a este medicamento (opcional)",
    "Tick what the doctor's paper says": "Marque lo que dice el papel del médico",
    "Anything else (for example: white tablet, keep in the fridge)": "Algo más (por ejemplo: pastilla blanca, guardar en la nevera)",
    "Yes, this matches the doctor's schedule": "Sí, coincide con la pauta del médico",
    "Will be in the plan": "Estará en el plan",
    "Ticked, but every amount is None": "Marcado, pero todas las cantidades son Nada",
    "Not in the plan yet: choose the amounts, then tick the box": "Todavía fuera del plan: elija las cantidades y marque la casilla",
    "A medicine on the schedule that has no box on the table": "Un medicamento de la pauta que no tiene caja en la mesa",
    'Type its name as written on the schedule. The plan will list it as "on the schedule but not on the table".':
        'Escriba su nombre como aparece en la pauta. El plan lo indicará como "en la pauta pero no en la mesa".',
    "Name on the schedule": "Nombre en la pauta",
    "Add this line": "Añadir esta línea",
    "Next: see the plan": "Siguiente: ver el plan",
    "There are no medicines yet. Go back and add one.": "Todavía no hay medicamentos. Vuelva atrás y añada uno.",
    "{ready} of {x1} will be in the plan.": "{ready} de {x1} estarán en el plan.",
    # ---- screens 3 and 4 ---------------------------------------------------------------------------------------------------
    "Preparing the plan...": "Preparando el plan...",
    "Check the plan": "Revise el plan",
    "This is exactly what will be printed. Read it through, and read what was left out and why.":
        "Esto es exactamente lo que se imprimirá. Léalo entero, y lea también lo que quedó fuera y por qué.",
    "Nothing in the plan yet": "Todavía no hay nada en el plan",
    "Go back to <b>Doses</b>, choose the amounts and tick <b>Yes, this matches the doctor's schedule</b> for at least one medicine.":
        "Vuelva a <b>Dosis</b>, elija las cantidades y marque <b>Sí, coincide con la pauta del médico</b> en al menos un medicamento.",
    " Waiting for you: {x0} medicine(s).": " Pendientes de usted: {x0} medicamento(s).",
    '<p class="mt-lead">Plan for <b>{x0}</b></p>': '<p class="mt-lead">Plan para <b>{x0}</b></p>',
    "<span class=mt-empty>Nothing</span>": "<span class=mt-empty>Nada</span>",
    "Please check the amount of {x0}": "Revise la cantidad de {x0}",
    "{big:g} a day is more than usual for one medicine. It is in the plan as you chose it: compare it with the doctor's paper.":
        "{big:g} al día es más de lo habitual para un medicamento. Está en el plan tal como lo eligió: compárelo con el papel del médico.",
    "<li><b>{x0}</b>: a full box of {units} lasts about <b>{days_left} days</b> at these amounts.</li>":
        "<li><b>{x0}</b>: una caja llena de {units} dura unos <b>{days_left} días</b> con estas cantidades.</li>",
    "How long a box lasts": "Cuánto dura una caja",
    '<ul style="margin:.3rem 0 0 1.1rem;padding:0">{x0}</ul><div class="mt-meta">Counted from the pack size listed by AEMPS CIMA, for a full box. Ask for the next box a week before.</div>':
        '<ul style="margin:.3rem 0 0 1.1rem;padding:0">{x0}</ul><div class="mt-meta">Calculado con el tamaño de envase que indica AEMPS CIMA, para una caja llena. Pida la siguiente caja una semana antes.</div>',
    "Waiting for you ({x0})": "Pendientes de usted ({x0})",
    "Not in the plan until you tick the box on the Doses screen: {x0}.": "No estarán en el plan hasta que marque la casilla en la pantalla Dosis: {x0}.",
    "Left out: a box I could not recognise": "Fuera del plan: una caja que no pude reconocer",
    ". It is not in the plan.": ". No está en el plan.",
    "Left out: {what}": "Fuera del plan: {what}",
    " <b>What to do:</b> {x0}": " <b>Qué hacer:</b> {x0}",
    '<p class="mt-title" style="font-size:1.3rem;margin-top:1rem">To ask your pharmacist ({x0})</p>':
        '<p class="mt-title" style="font-size:1.3rem;margin-top:1rem">Para consultar con su farmacéutico ({x0})</p>',
    '<div class="mt-meta">Source: {x0}</div>': '<div class="mt-meta">Fuente: {x0}</div>',
    "More information ({x0})": "Más información ({x0})",
    "What was checked, and what was not": "Qué se ha comprobado y qué no",
    "Checks run: the same active ingredient in two boxes, the same drug group, the expiry date printed in the code, and whether each box matches the schedule":
        "Comprobaciones hechas: el mismo principio activo en dos cajas, el mismo grupo de fármacos, la caducidad impresa en el código y si cada caja coincide con la pauta",
    ", and word-for-word quotes from sections 4.2 and 4.5 of the official leaflets (the quotes stay in Spanish, as AEMPS wrote them).":
        ", y citas literales de los apartados 4.2 y 4.5 de las fichas técnicas oficiales (tal como las escribió la AEMPS).",
    ". The official leaflets were NOT consulted (turned off in Settings).": ". NO se consultaron las fichas técnicas oficiales (desactivado en Ajustes).",
    " For some medicine a leaflet section could not be checked (see the notes above).":
        " En algún medicamento no se pudo comprobar un apartado de la ficha técnica (vea las notas de arriba).",
    "Remember": "Recuerde",
    "No warning does <b>not</b> mean the plan is safe. This helper schedules what the doctor prescribed; ask a pharmacist about the medicines together.":
        "Que no haya avisos <b>no</b> significa que el plan sea seguro. Esta ayuda organiza lo que recetó el médico; consulte en la farmacia los medicamentos en conjunto.",
    "Next: print or listen": "Siguiente: imprimir o escuchar",
    "The plan is empty. Go back and choose doses.": "El plan está vacío. Vuelva atrás y elija las dosis.",
    "Print, listen, remind": "Imprimir, escuchar, recordar",
    "Take the plan with you: a page for the fridge, a voice that reads it out, or reminders on a phone.":
        "Llévese el plan: una hoja para la nevera, una voz que lo lee en alto o recordatorios en el móvil.",
    "Nothing to print yet": "Todavía no hay nada que imprimir",
    "Go back and confirm at least one medicine.": "Vuelva atrás y confirme al menos un medicamento.",
    '<p class="mt-name">Before you print</p><p class="mt-hint">Both are optional. Anything left empty is printed as lines to write on by hand.</p>':
        '<p class="mt-name">Antes de imprimir</p><p class="mt-hint">Los dos son opcionales. Lo que quede vacío se imprime como líneas para escribir a mano.</p>',
    "Notes for the whole plan (for example: doctor's phone number, allergies)": "Notas para todo el plan (por ejemplo: teléfono del médico, alergias)",
    "Change the reminder times": "Cambiar las horas de los recordatorios",
    '<p class="mt-title" style="font-size:1.25rem;margin-top:1rem">This is the page you will print</p>':
        '<p class="mt-title" style="font-size:1.25rem;margin-top:1rem">Esta es la hoja que va a imprimir</p>',
    '<p class="mt-title" style="font-size:1.25rem;margin-top:1rem">A page to print</p><p class="mt-hint">Large print, with the official picture of each medicine.</p>':
        '<p class="mt-title" style="font-size:1.25rem;margin-top:1rem">Una hoja para imprimir</p><p class="mt-hint">Letra grande, con la foto oficial de cada medicamento.</p>',
    "Download the calendar to print (PDF)": "Descargar el calendario para imprimir (PDF)",
    '<p class="mt-title" style="font-size:1.25rem;margin-top:1rem">A guide to fill the weekly pill organiser</p><p class="mt-hint">One page: the seven days and four times of day, with what goes into each compartment.</p>':
        '<p class="mt-title" style="font-size:1.25rem;margin-top:1rem">Una guía para llenar el pastillero semanal</p><p class="mt-hint">Una hoja: los siete días y los cuatro momentos del día, con lo que va en cada casilla.</p>',
    "Download the pill organiser sheet (PDF)": "Descargar la hoja del pastillero (PDF)",
    '<p class="mt-title" style="font-size:1.25rem;margin-top:1rem">Listen to it</p><p class="mt-hint">A voice reads each time of day.</p>':
        '<p class="mt-title" style="font-size:1.25rem;margin-top:1rem">Escucharlo</p><p class="mt-hint">Una voz lee cada momento del día.</p>',
    "Read the plan aloud": "Leer el plan en voz alta",
    "Reading aloud needs a voice in this language on this computer; none is installed.":
        "Para leer en voz alta hace falta una voz en este idioma en el ordenador; no hay ninguna instalada.",
    '<p class="mt-title" style="font-size:1.25rem;margin-top:1rem">Reminders on a phone</p><p class="mt-hint">Open the file on the phone to add daily reminders to its calendar.</p>':
        '<p class="mt-title" style="font-size:1.25rem;margin-top:1rem">Recordatorios en el móvil</p><p class="mt-hint">Abra el archivo en el móvil para añadir recordatorios diarios a su calendario.</p>',
    '<p class="mt-title" style="font-size:1.25rem;margin-top:1rem">Continue later</p><p class="mt-hint">Saves the medicines and the doses (not the photos) in a small file. Open it next month on the first screen.</p>':
        '<p class="mt-title" style="font-size:1.25rem;margin-top:1rem">Continuar más tarde</p><p class="mt-hint">Guarda los medicamentos y las dosis (no las fotos) en un archivo pequeño. Ábralo el mes que viene en la primera pantalla.</p>',
    "Save this plan to continue later": "Guardar este plan para continuar más tarde",
    "Download the phone reminders (.ics)": "Descargar los recordatorios para el móvil (.ics)",
    "Start over with new medicines": "Empezar de nuevo con otros medicamentos",
    # ---- reasons a line is left out (shown with tr_reason) ------------------------------------------------------------------
    "the caregiver has not confirmed this line": "el cuidador no ha confirmado esta línea",
    "no verified pack": "ninguna caja verificada",
    "no day of the week is chosen": "no se ha elegido ningún día de la semana",
    "could not be verified": "no se pudo verificar",
    "no pack on the table matches": "ninguna caja de la mesa coincide",
    "several packs match; say which one": "coinciden varias cajas; indique cuál",
    "the strength on the sheet does not match the pack": "la dosis de la pauta no coincide con la de la caja",
    "the pack is on several lines; keep one": "la caja está en varias líneas; deje una",
    "the line has no dose": "la línea no tiene dosis",
    "unidentified pack": "caja sin identificar",
    "AEMPS CIMA does not know the national code {x0}": "AEMPS CIMA no conoce el código nacional {x0}",
    "the code read is not a GS1 medicine code": "el código leído no es un código GS1 de medicamento",
    "the check digit of the national code is invalid": "el dígito de control del código nacional no es válido",
    "the code does not contain a Spanish national code": "el código no contiene un código nacional español",
    "field 712 is not a valid national code": "el campo 712 no es un código nacional válido",
    "the code holds no medicine data": "el código no contiene datos de medicamento",
    "the official database could not be reached (no internet?): press Try again":
        "no se pudo contactar con la base de datos oficial (¿sin internet?): pulse Reintentar",
    '"{x0}" is already in the list, so the new line was not added. Check the list in case they were different lines.':
        '"{x0}" ya está en la lista, así que no se añadió la línea nueva. Revise la lista por si eran líneas distintas.',
    # ---- findings ----------------------------------------------------------------------------------------------------------
    "This is not a full interaction check.": "Esto no es una comprobación completa de interacciones.",
    "{a} and {b} contain the same active ingredient ({detail}). Review with a pharmacist or doctor before using both.":
        "{a} y {b} contienen el mismo principio activo ({detail}). Revíselo con un farmacéutico o médico antes de usar los dos.",
    "There are two packs of {a}. Make sure they are not taken together by mistake.": "Hay dos cajas de {a}. Asegúrese de que no se toman juntas por error.",
    "{a} and {b} belong to the same pharmacological group ({detail}). To review with a pharmacist.":
        "{a} y {b} pertenecen al mismo grupo farmacológico ({detail}). Para revisar con un farmacéutico.",
    "{a} expired on {detail}. Do not include it in the calendar without asking a pharmacist.":
        "{a} caducó el {detail}. No lo incluya en el calendario sin consultar a un farmacéutico.",
    "{a} expires on {detail}.": "{a} caduca el {detail}.",
    'The official leaflet of {a} (SmPC section 4.5) mentions {detail}: "{quote}" To review with a pharmacist. This is not a full interaction check.':
        'La ficha técnica oficial de {a} (apartado 4.5) menciona {detail}: "{quote}" Para revisar con un farmacéutico. Esto no es una comprobación completa de interacciones.',
    'The official leaflet of {a} (SmPC section 4.2) says about meals: "{quote}" This is a quotation; the schedule is decided by the caregiver with a doctor or pharmacist.':
        'La ficha técnica oficial de {a} (apartado 4.2) dice sobre las comidas: "{quote}" Es una cita; el horario lo decide el cuidador con un médico o farmacéutico.',
    "The pack {a} appears on several sheet lines ({detail}). Use one line per pack: merge or correct them before continuing.":
        "La caja {a} aparece en varias líneas de la pauta ({detail}). Use una línea por caja: júntelas o corríjalas antes de seguir.",
    'The line "{detail}" has no dose at all (all 0), so it is not in the calendar. If this is a mistake, correct it.':
        'La línea "{detail}" no tiene ninguna dosis (todo 0), así que no está en el calendario. Si es un error, corríjalo.',
    "The expiry of {a} was not checked: {detail}. Look at the pack.": "No se comprobó la caducidad de {a}: {detail}. Mírela en la caja.",
    "Section {detail} of the official leaflet (SmPC) of {a} could not be checked: that check was not done for this medicine.":
        "No se pudo consultar el apartado {detail} de la ficha técnica de {a}: esa comprobación no se hizo para este medicamento.",
    "Listed on the medication sheet but not found on the table: {detail}.": "En la pauta pero no en la mesa: {detail}.",
    "On the table but not on the medication sheet: {a}.": "En la mesa pero no en la pauta: {a}.",
    'The sheet says "{detail}" but the pack is {a}. The strength does not match: check before continuing.':
        'La pauta dice "{detail}" pero la caja es {a}. La dosis no coincide: revísela antes de seguir.',
    'The line "{detail}" could match several packs ({a}). Say which one it is.': 'La línea "{detail}" puede corresponder a varias cajas ({a}). Indique cuál es.',
    'The dose "{quote}" on the line "{detail}" is not understood. Correct or confirm it.': 'No se entiende la dosis "{quote}" de la línea "{detail}". Corríjala o confírmela.',
    "This pack could not be verified ({detail}). It is not included in the calendar.": "Esta caja no se pudo verificar ({detail}). No está en el calendario.",
    "Same active ingredient": "Mismo principio activo", "Two packs of one medicine": "Dos cajas del mismo medicamento", "Same drug class": "Mismo grupo de fármacos",
    "Expired pack": "Caja caducada", "Expires soon": "Caduca pronto", "Leaflet mentions another pack": "La ficha técnica menciona otra caja",
    "Leaflet note about meals": "Nota de la ficha técnica sobre las comidas", "Pack on several lines": "Caja en varias líneas", "Line without doses": "Línea sin dosis",
    "Expiry not checked": "Caducidad sin comprobar", "Leaflet section unavailable": "Apartado de la ficha técnica no disponible",
    "On the sheet, not on the table": "En la pauta, no en la mesa", "On the table, not on the sheet": "En la mesa, no en la pauta",
    "Strength does not match": "La dosis no coincide", "Line matches several packs": "La línea coincide con varias cajas", "Dose not understood": "Dosis no entendida",
    "Pack not verified": "Caja no verificada",
    # ---- printed calendar and pill organiser -------------------------------------------------------------------------------
    "This plan was prepared from the medication sheet that the caregiver confirmed line by line. It is an aid to organise medication: it does not replace the doctor or the pharmacist. Ask your pharmacist before using it.":
        "Este plan se preparó a partir de la pauta que el cuidador confirmó línea a línea. Es una ayuda para organizar la medicación: no sustituye al médico ni al farmacéutico. Consulte a su farmacéutico antes de usarlo.",
    "Page {x0} of 2": "Página {x0} de 2",
    "Medication plan": "Plan de medicación",
    "<b>For:</b> {who} &nbsp;&nbsp;&nbsp; <b>Date:</b> {x1}": "<b>Para:</b> {who} &nbsp;&nbsp;&nbsp; <b>Fecha:</b> {x1}",
    "<b>Medicine</b>": "<b>Medicamento</b>",
    "<b>Notes</b>": "<b>Notas</b>",
    "No medication in the plan.": "No hay medicación en el plan.",
    "<b>{x0} item(s) are NOT in this calendar.</b> See page 2 for what and why.": "<b>{x0} elemento(s) NO están en este calendario.</b> Vea la página 2: qué y por qué.",
    "Doctor: {x0} &nbsp; Phone: {x1}": "Médico: {x0} &nbsp; Teléfono: {x1}",
    "Pharmacy: {x0} &nbsp; Phone: {x1}": "Farmacia: {x0} &nbsp; Teléfono: {x1}",
    "Other: {x0}": "Otros: {x0}",
    "<b>Notes for the whole plan</b>": "<b>Notas para todo el plan</b>",
    "For the pharmacist and the caregiver": "Para el farmacéutico y el cuidador",
    "<b>Plan for:</b> {who} &nbsp;&nbsp; <b>Date:</b> {x1}": "<b>Plan para:</b> {who} &nbsp;&nbsp; <b>Fecha:</b> {x1}",
    "<b>Not included in the calendar</b>": "<b>No incluido en el calendario</b>",
    "<b>Changes since the saved plan</b>": "<b>Cambios desde el plan guardado</b>",
    "&bull; New: {x0}": "&bull; Nuevo: {x0}",
    "&bull; Not seen in the new photos: {x0}": "&bull; No aparece en las fotos nuevas: {x0}",
    "<b>To review with your pharmacist</b>": "<b>Para revisar con su farmacéutico</b>",
    "Source: {x0}": "Fuente: {x0}",
    "No points were raised by the checks listed below. That does not mean the plan is safe.":
        "Las comprobaciones de abajo no encontraron puntos que revisar. Eso no significa que el plan sea seguro.",
    "Checks done: duplicate active ingredient, ATC group, expiry read from the code and match with the sheet":
        "Comprobaciones hechas: principio activo repetido, grupo ATC, caducidad leída del código y coincidencia con la pauta",
    ", and verbatim quotes from sections 4.2 and 4.5 of the leaflets (SmPC; quotes stay in the original Spanish).":
        ", y citas literales de los apartados 4.2 y 4.5 de las fichas técnicas.",
    ". The leaflets (SmPC) were NOT consulted.": ". NO se consultaron las fichas técnicas.",
    " Some leaflet section could not be checked (see above).": " Algún apartado de las fichas técnicas no se pudo comprobar (vea arriba).",
    " No warning does not mean the plan is safe.": " Que no haya avisos no significa que el plan sea seguro.",
    "Sources consulted: ": "Fuentes consultadas: ",
    "none": "ninguna",
    "Weekly pill organiser": "Pastillero semanal",
    "<b>For:</b> {who} &nbsp;&nbsp;&nbsp; <b>Plan of:</b> {x1}": "<b>Para:</b> {who} &nbsp;&nbsp;&nbsp; <b>Plan del:</b> {x1}",
    "Fill each compartment with what its box says. A dash means nothing at that time.":
        "Llene cada casilla del pastillero con lo que indica su recuadro. Un guion significa nada a esa hora.",
    "<b>{x0} item(s) are NOT on this page</b> (see page 2 of the medication plan).": "<b>{x0} elemento(s) NO están en esta hoja</b> (vea la página 2 del plan de medicación).",
    "Filled on: ______________ &nbsp;&nbsp; by: ______________ &nbsp;&nbsp; Checked by: ______________":
        "Llenado el: ______________ &nbsp;&nbsp; por: ______________ &nbsp;&nbsp; Revisado por: ______________",
    # ---- printed dose words, voice and reminders (plan.py) -----------------------------------------------------------------
    "{days} only": "solo {days}",
    "{slot}: nothing in the plan.": "{slot}: nada en el plan.",
    "Medication: {slot}": "Medicación: {slot}",
    "Time for the medication": "Hora de la medicación",
    "{dose} of {name}": "{dose} de {name}",
    "Based on the medication sheet confirmed by the caregiver. Ask a pharmacist if in doubt.":
        "Según la pauta confirmada por el cuidador. Ante cualquier duda, consulte a un farmacéutico.",
}
