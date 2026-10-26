"""Hand-made medicines in the shape of resolve.Medicine, plus a stand-in for the SmPC cache. Test data, not real SmPC text."""

from datetime import date

from medtable.resolve import Medicine
from medtable.rules import Pack
from medtable.smpc import Section


def med(cn, name, ingredients, atc5, atc4_name="Grupo", strengths=None, form="COMPRIMIDOS", nregistro=None):
    atc = [{"codigo": atc5, "nombre": ingredients[0].title(), "nivel": 5},
           {"codigo": atc5[:5], "nombre": atc4_name, "nivel": 4}]
    return Medicine(
        cn=cn, nregistro=nregistro or f"9{cn}", name=name, active_ingredients=ingredients,
        strengths=strengths or [{"nombre": i, "cantidad": None, "unidad": None} for i in ingredients],
        atc=atc, form=form, presentation=name, marketed=True, holder="Lab", photos={}, docs={},
        source_url=f"https://cima.aemps.es/cima/publico/detalle.html?nregistro={nregistro or '9' + cn}", fetched="2026-10-26")


def pack(medicine, expiry=None, state="verified"):
    return Pack(medicine, state, expiry)


def strength(*pairs):
    return [{"nombre": f"I{i}", "cantidad": q, "unidad": u} for i, (q, u) in enumerate(pairs)]


PARACETAMOL_A = med("650001", "PARACETAMOL ALFA 1 g COMPRIMIDOS", ["PARACETAMOL"], "N02BE01", "Anilidas", strength(("1000", "mg")))
PARACETAMOL_B = med("650002", "TERMALGIN 1 g COMPRIMIDOS", ["PARACETAMOL"], "N02BE01", "Anilidas", strength(("1", "g")))
IBUPROFENO = med("660001", "IBUPROFENO BETA 600 mg COMPRIMIDOS", ["IBUPROFENO"], "M01AE01", "Derivados del acido propionico", strength(("600", "mg")))
NAPROXENO = med("660002", "NAPROXENO GAMMA 500 mg COMPRIMIDOS", ["NAPROXENO"], "M01AE02", "Derivados del acido propionico", strength(("500", "mg")))
ACENOCUMAROL = med("670001", "SINTROM 4 mg COMPRIMIDOS", ["ACENOCUMAROL"], "B01AA07", "Antagonistas de la vitamina K", strength(("4", "mg")))
METFORMINA_850 = med("680001", "METFORMINA DELTA 850 mg COMPRIMIDOS", ["METFORMINA"], "A10BA02", "Biguanidas", strength(("850", "mg")))
METFORMINA_500 = med("680002", "METFORMINA EPSILON 500 mg COMPRIMIDOS", ["METFORMINA"], "A10BA02", "Biguanidas", strength(("500", "mg")))
OMEPRAZOL = med("690001", "OMEPRAZOL ZETA 20 mg CAPSULAS", ["OMEPRAZOL"], "A02BC01", "Inhibidores de la bomba de protones", strength(("20", "mg")), "CAPSULAS DURAS")
LORAZEPAM = med("700001", "LORAZEPAM ETA 1 mg COMPRIMIDOS", ["LORAZEPAM"], "N05BA06", "Derivados de la benzodiazepina", strength(("1", "mg")))
VALSARTAN_HCT = med("710001", "VALSARTAN/HIDROCLOROTIAZIDA THETA 160/12,5 mg COMPRIMIDOS", ["VALSARTAN", "HIDROCLOROTIAZIDA"], "C09DA03",
                    "Antagonistas de angiotensina II y diureticos", strength(("160", "mg"), ("12.5", "mg")))
VALSARTAN_40 = med("710002", "VALSARTAN IOTA 40 mg COMPRIMIDOS", ["VALSARTAN"], "C09CA03", "Antagonistas de angiotensina II", strength(("40", "mg")))

# Invented SmPC 4.5 texts for the tests
SECTIONS = {
    (IBUPROFENO.nregistro, "4.5"): ("Los antiinflamatorios no esteroideos pueden potenciar el efecto de los anticoagulantes orales como el acenocumarol, "
                                    "con riesgo de hemorragia. Se debe evitar su uso conjunto con otros AINE. Los inhibidores de la bomba de protones no "
                                    "modifican su absorcion de forma relevante."),
    (OMEPRAZOL.nregistro, "4.5"): "El omeprazol puede reducir la absorcion de otros farmacos dependientes del pH gastrico. No se han descrito interacciones relevantes con la metformina.",
    (METFORMINA_850.nregistro, "4.5"): "No se han realizado estudios especificos de interacciones con otros medicamentos en este producto concreto.",
}


class FakeSmpc:
    def section(self, nregistro, section):
        text = SECTIONS.get((nregistro, section))
        return Section(nregistro, section, text, "2026-10-26") if text else None


TODAY = date(2026, 10, 26)
