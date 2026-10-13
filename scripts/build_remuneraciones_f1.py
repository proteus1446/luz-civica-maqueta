#!/usr/bin/env python3
"""
Remuneraciones — Fase 1: resumen/detalle por estamento (Municipal, Salud,
Educación) desde grupos_estadisticas.csv, para las comunas con datos
disponibles (~320 de 345 — el resto quedó fuera del pipeline original por
tener grupos con menos del mínimo de 8 personas, N_MINIMO_GRUPO en
preparar_grupos.py).

IMPORTANTE — adaptación de p25/p75 a mediana±MAD:
La página original (remuneraciones.html) esperaba percentiles p25/p75 reales
por grado/categoría/hora, pero el pipeline ya corrido (preparar_grupos.py)
calcula mediana + MAD (median absolute deviation), no percentiles — y el
archivo intermedio que sí tendría percentiles (persona_grupo.csv) no se
guardó en disco (recalcularlo requiere reprocesar el archivo nacional de
12GB). Se decidió con el usuario: adaptar la página para mostrar un rango
aproximado mediana±MAD en vez de p25/p75 reales (ver ajuste en
tablaVinculo() dentro de remuneraciones.html).

IMPORTANTE — resumen (sin desglose de grado):
El archivo resumen_estadisticas.csv (que el propio preparar_grupos.py genera
con la mediana recalculada de verdad sobre las personas, sin desglosar por
grado) tampoco se guardó en disco. Como aproximación, "resumen_*" se calcula
acá como una MEDIANA PONDERADA de las medianas de cada grado (ponderada por
n) — no es matemáticamente idéntica a la mediana real sobre las personas,
pero es la mejor aproximación posible sin volver a procesar el archivo
nacional. Se documenta explícitamente para que quede claro que es un proxy.
"""
import json
import re
import sys

import pandas as pd

sys.path.insert(0, ".")
from organismo_mapping import organismo_a_comuna_key

GRUPOS_CSV = "/Users/cristobal/prueba/luz-civica-web/script sueldo/grupos_estadisticas.csv"
GASTO_CSV = "/Users/cristobal/prueba/luz-civica-web/script sueldo/gasto_mensual.csv"
NOMBRES_JS = "/Users/cristobal/Downloads/maqueta/data/nombres_comunas.js"
OUT_JSON = "/Users/cristobal/Downloads/maqueta/data/remuneraciones_f1.json"

# --- Mapeo estamento_norm -> etiqueta de display -------------------------
MUNICIPAL_ESTAMENTOS = {
    "DIRECTIVO": "Directivo",
    "JEFATURA": "Jefatura",
    "PROFESIONAL": "Profesional",
    "TECNICO": "Técnico",
    "ADMINISTRATIVO": "Administrativo",
    "AUXILIAR": "Auxiliar",
}
# Categorías legales A-F (Ley 19.378) — mapeo por nombre de estamento_norm.
SALUD_ESTAMENTOS = {
    "MEDICOS CIRUJANOS FARMACEUTICOS QUIMICOFARMACEUTICOS BIOQUIMICOS CIRUJANODENTISTAS": "Médicos y Prof. Salud (A)",
    "OTROS PROFESIONALES (LEY 19.378)": "Otros Profesionales (B)",
    "TECNICOS DE NIVEL SUPERIOR (LEY 19.378)": "Técnicos Sup. Salud (C)",
    "TECNICOS DE SALUD": "Técnicos de Salud (D)",
    "ADMINISTRATIVOS DE SALUD": "Administrativos Salud (E)",
    "AUXILIARES DE SERVICIOS DE SALUD": "Auxiliares Salud (F)",
    "AUXILIAR PARAMEDICO": "Auxiliares Salud (F)",
}
EDUCACION_ESTAMENTOS = {
    "DOCENTEDIRECTIVO": "Docentedirectivo",
    "DOCENTE": "Docente",
    "EDUCACION": "Educación",
    "NO DOCENTE DE CARACTER PROFESIONAL": "No docente de carácter profesional",
    "NO DOCENTE PARADOCENTE": "No docente paradocente",
    "NO DOCENTE DE SERVICIOS AUXILIARES": "No docente de servicios auxiliares",
    "ASISTENTE DE LA EDUCACION": "Asistente de la Educación",
}

FULL_REGION_NAMES = {
    "XV": "Región de Arica y Parinacota", "I": "Región de Tarapacá",
    "II": "Región de Antofagasta", "III": "Región de Atacama",
    "IV": "Región de Coquimbo", "V": "Región de Valparaíso",
    "RM": "Región Metropolitana de Santiago",
    "VI": "Región del Libertador General Bernardo O'Higgins",
    "VII": "Región del Maule", "XVI": "Región de Ñuble",
    "VIII": "Región del Biobío", "IX": "Región de la Araucanía",
    "XIV": "Región de Los Ríos", "X": "Región de Los Lagos",
    "XI": "Región de Aysén del General Carlos Ibáñez del Campo",
    "XII": "Región de Magallanes y de la Antártica Chilena",
}


def weighted_median_of_medians(rows):
    """Aproxima la mediana real sobre personas usando las medianas de cada
    grado, ponderadas por n (ver nota del módulo)."""
    rows = sorted(rows, key=lambda r: r["mediana_grupo"])
    total = sum(r["n"] for r in rows)
    if total == 0:
        return None
    acumulado = 0
    for r in rows:
        acumulado += r["n"]
        if acumulado >= total / 2:
            return r["mediana_grupo"]
    return rows[-1]["mediana_grupo"]


def cargar_n_total_real():
    """n_total real de headcount (personas, no persona-mes) desde el mes más
    reciente de gasto_mensual.csv por comuna+año — no está filtrado por
    tamaño de grupo (a diferencia de grupos_estadisticas.csv), así que se
    acerca mucho más al total real que sumar los grupos ya filtrados.
    No reproduce el número original exacto (que requeriría deduplicar
    personas a través del año completo, solo posible con el archivo
    nacional de 12GB) pero es la mejor aproximación disponible."""
    g = pd.read_csv(GASTO_CSV, sep=";", usecols=["organismo_nombre", "anyo", "mes_num", "n_personas"])
    g["comuna_key"] = g["organismo_nombre"].map(organismo_a_comuna_key)
    ultimo_mes = g.groupby(["comuna_key", "anyo"])["mes_num"].transform("max")
    g = g[g["mes_num"] == ultimo_mes]
    return g.groupby(["comuna_key", "anyo"])["n_personas"].sum().to_dict()


def main():
    with open(NOMBRES_JS, encoding="utf-8") as f:
        nombres = json.loads(re.search(r"const NOMBRES_COMUNAS = (\{.*?\});", f.read(), re.S).group(1))

    n_total_real = cargar_n_total_real()

    df = pd.read_csv(GRUPOS_CSV, sep=";")
    df["comuna_key"] = df["organismo_nombre"].map(organismo_a_comuna_key)

    # nos quedamos con el año más reciente disponible por comuna
    ultimo_anyo = df.groupby("comuna_key")["anyo"].transform("max")
    df = df[df["anyo"] == ultimo_anyo].copy()

    resultado = {}
    for comuna_key, sub in df.groupby("comuna_key"):
        anyo = int(sub["anyo"].iloc[0])
        n_total = int(n_total_real.get((comuna_key, anyo), sub["n"].sum()))

        def build_area(regimen, mapping, grado_col):
            area_df = sub[sub["regimen"] == regimen]
            resumen = {}
            detalle = {}
            for estamento_norm, label in mapping.items():
                est_df = area_df[area_df["estamento_norm"] == estamento_norm]
                if est_df.empty:
                    continue
                resumen_est = {}
                detalle_est = {}
                for vinculo in ("Planta", "Contrata"):
                    vd = est_df[est_df["tipo_vinculo"] == vinculo]
                    if vd.empty:
                        continue
                    filas = vd.to_dict("records")
                    n_vinc = int(vd["n"].sum())
                    mediana_vinc = weighted_median_of_medians(filas)
                    resumen_est[vinculo] = {"n": n_vinc, "mediana": mediana_vinc}
                    detalle_est[vinculo] = [
                        {
                            "grado": (str(int(r[grado_col])) if grado_col != "categoria_salud"
                                      else r[grado_col]),
                            "n": int(r["n"]),
                            "mediana": r["mediana_grupo"],
                            "mad": r["mad_grupo"],
                        }
                        for r in filas if pd.notna(r[grado_col])
                    ]
                if resumen_est:
                    resumen[label] = resumen_est
                    detalle[label] = detalle_est
            return resumen, detalle

        resumen_municipal, detalle_municipal = build_area("MUNICIPAL", MUNICIPAL_ESTAMENTOS, "grado_municipal")
        resumen_salud, detalle_salud = build_area("SALUD", SALUD_ESTAMENTOS, "categoria_salud")
        resumen_educacion, detalle_educacion = build_area("EDUCACION", EDUCACION_ESTAMENTOS, "horas_jornada_edu")

        docente_n = int(sub[(sub["regimen"] == "EDUCACION") &
                             (sub["estamento_norm"].isin(["DOCENTE", "DOCENTEDIRECTIVO"]))]["n"].sum())

        areas = []
        if resumen_municipal:
            areas.append("Municipal")
        if resumen_salud:
            areas.append("Salud")
        if resumen_educacion:
            areas.append("Educación")
        if not areas:
            continue  # sin ninguna área con datos, no incluir la comuna

        region_code = None  # se completa en F4 (necesita REGION_POR_COMUNA)

        resultado[comuna_key] = {
            "nombre": nombres.get(comuna_key, comuna_key.title()),
            "anyo": anyo,
            "n_total": n_total,
            "areas": areas,
            "resumen_municipal": resumen_municipal,
            "detalle_municipal": detalle_municipal,
            "resumen_salud": resumen_salud,
            "detalle_salud": detalle_salud,
            "resumen_educacion": resumen_educacion,
            "detalle_educacion": detalle_educacion,
            "docente_n": docente_n,
        }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False)

    print(f"OK: {len(resultado)} comunas -> {OUT_JSON}")


if __name__ == "__main__":
    main()
