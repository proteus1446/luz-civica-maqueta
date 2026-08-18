#!/usr/bin/env python3
"""
Genera data/data_dotacion.js a partir de datos reales SINIM, para las 345 comunas
de Chile, años 2008-2025.

Fuentes:
  - /Users/cristobal/prueba/sinim/1-Administracion_finanzas.xlsx  (gasto personal municipal, límites legales)
  - /Users/cristobal/prueba/sinim/2-Recursos H.xlsx                (headcount municipal, % profesionalización/femenina)
  - /Users/cristobal/prueba/sinim/3-Educacion.xlsx                 (headcount y gasto personal Educación)
  - /Users/cristobal/prueba/sinim/4-SALUD.xlsx                     (headcount y gasto personal Salud)
  - /Users/cristobal/prueba/sinim/7-caracterizacion comunal.xlsx   (población, ICAR004)

Fórmulas (verificadas al número exacto contra los valores hardcodeados originales
de Providencia 2008):
  poblacion                     = ICAR004
  profesionalizacion_pct        = IADM25 (SINIM ya lo calcula, fracción 0-1)
  participacion_femenina_pct    = IADM33 (ídem)
  municipal_total   = IRH05 + IRH12 + IRH15 + IRH16               (planta+contrata+honorarios+comunitarios; IRH16 solo existe desde 2019)
  educacion_total   = IEDU040 + IEDU042 + IEDU043 + IEDU041       (+ cdt)
  salud_total       = MPSP + MPSCC + MPSH + MPSCDT + MPSOC        (+ cdt + comunitarios)
  consolidado_total = municipal_total + educacion_total + salud_total
  consolidado.planta       = IRH05 + IEDU040 + MPSP
  consolidado.contrata     = IRH12 + IEDU042 + MPSCC
  consolidado.cdt          = IEDU041 + MPSCDT
  consolidado.honorarios   = IRH15 + IEDU043 + MPSH
  consolidado.comunitarios = IRH16 + MPSOC
  gasto.planta       = IADM78 + IEDU040.1 + ISAL029
  gasto.contrata      = IADM79 + IEDU042.1 + ISAL031
  gasto.honorarios    = IADM80 + IEDU043.1 + ISAL032
  gasto.comunitarios  = IADM111  (solo categoría municipal)
  gasto.total         = IADM61 + IEDU026.1 + ISAL019.1
  limites.lim42 (gasto en personal)   = (IADM61 / (IADM42 * 0.42)) * 100
  limites.lim40 (personal a contrata) = (IADM79 / (IADM78 * 0.40)) * 100
  limites.lim10 (honorarios)          = (IADM80 / (IADM61 * 0.10)) * 100
    (el documento de especificación dice "IADM80 / IADM78 x 100", pero eso NO
    reproduce el valor original hardcodeado de Providencia 2008 (86,43); la
    fórmula de arriba sí lo reproduce exacto — se prioriza el comportamiento
    real de la página por sobre el documento, que quedó desactualizado)
  municipal_honorarios_sindato = True si IRH15 falta/0 pero IADM80 (gasto) > 0
  areas_activas.educacion/salud = True si el gasto total de ese sector es > 0
  gasto_por_area.{municipal,educacion,salud} = IADM61, IEDU026.1, ISAL019.1
    (campo usado por el gráfico de evolución "Municipal/Educación/Salud" del HTML;
    no existía en los datos originales — el gráfico estaba roto desde antes)
"""
import json
import re
import openpyxl

from build_administracion import comuna_key, num  # reutiliza normalización ya validada

SINIM_ADMIN = "/Users/cristobal/prueba/sinim/1-Administracion_finanzas.xlsx"
SINIM_RRHH = "/Users/cristobal/prueba/sinim/2-Recursos H.xlsx"
SINIM_EDU = "/Users/cristobal/prueba/sinim/3-Educacion.xlsx"
SINIM_SALUD = "/Users/cristobal/prueba/sinim/4-SALUD.xlsx"
SINIM_CARAC = "/Users/cristobal/prueba/sinim/7-caracterizacion comunal.xlsx"
OUT_JS = "/Users/cristobal/Downloads/maqueta/data/data_dotacion.js"


def find_col(header, code):
    """Ubica la columna cuyo header contiene el código SINIM como token exacto,
    en cualquier posición (algunos archivos lo ponen al inicio, otros al final)."""
    pat = r"(?<![A-Za-z0-9])" + re.escape(code) + r"(?!\.\d)(?![A-Za-z0-9])"
    for i, h in enumerate(header):
        if h and re.search(pat, str(h)):
            return i
    raise KeyError(f"Column not found for code {code}")


def find_anio_col(header):
    for i, h in enumerate(header):
        if h and str(h).strip().upper() == "AÑO":
            return i
    raise KeyError("Año column not found")


def load_sheet(path, codes):
    """Devuelve {(comuna_key, anio): {code: valor_numerico}} para los códigos pedidos."""
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = ws.iter_rows(values_only=True)
    header = next(rows)
    idx = {c: find_col(header, c) for c in codes}
    idx_anio = find_anio_col(header)
    out = {}
    for r in rows:
        if r[0] is None:
            continue
        municipio = comuna_key(str(r[1]).strip())
        anio = str(r[idx_anio])
        out[(municipio, anio)] = {c: num(r[i]) for c, i in idx.items()}
    return out


def load_poblacion():
    wb = openpyxl.load_workbook(SINIM_CARAC, read_only=True)
    ws = wb["Hoja1"]
    rows = ws.iter_rows(values_only=True)
    header = next(rows)
    idx_pob = [i for i, h in enumerate(header) if h and str(h).startswith("ICAR004")][0]
    idx_anio = len(header) - 1
    out = {}
    for r in rows:
        if r[0] is None:
            continue
        municipio = comuna_key(str(r[1]).strip())
        anio = str(r[idx_anio])
        out[(municipio, anio)] = num(r[idx_pob])
    return out


def main():
    admin = load_sheet(SINIM_ADMIN, ["IADM78", "IADM79", "IADM80", "IADM111", "IADM61", "IADM42"])
    rrhh = load_sheet(SINIM_RRHH, ["IRH05", "IRH12", "IRH15", "IRH16", "IADM25", "IADM33"])
    edu = load_sheet(SINIM_EDU, ["IEDU040", "IEDU042", "IEDU043", "IEDU041",
                                  "IEDU040.1", "IEDU042.1", "IEDU043.1", "IEDU026.1"])
    salud = load_sheet(SINIM_SALUD, ["MPSP", "MPSCC", "MPSH", "MPSCDT", "MPSOC",
                                      "ISAL029", "ISAL031", "ISAL032", "ISAL019.1"])
    poblacion = load_poblacion()

    keys = sorted(set(admin) & set(rrhh))
    data = {}
    for (municipio, anio) in keys:
        a = admin[(municipio, anio)]
        rh = rrhh.get((municipio, anio), {})
        e = edu.get((municipio, anio), {})
        s = salud.get((municipio, anio), {})

        def g(d, k):
            return d.get(k) or 0

        municipal_total = g(rh, "IRH05") + g(rh, "IRH12") + g(rh, "IRH15") + g(rh, "IRH16")
        educacion_total = g(e, "IEDU040") + g(e, "IEDU042") + g(e, "IEDU043") + g(e, "IEDU041")
        salud_total = g(s, "MPSP") + g(s, "MPSCC") + g(s, "MPSH") + g(s, "MPSCDT") + g(s, "MPSOC")

        gasto_planta = g(a, "IADM78") + g(e, "IEDU040.1") + g(s, "ISAL029")
        gasto_contrata = g(a, "IADM79") + g(e, "IEDU042.1") + g(s, "ISAL031")
        gasto_honorarios = g(a, "IADM80") + g(e, "IEDU043.1") + g(s, "ISAL032")
        gasto_comunitarios = g(a, "IADM111")
        gasto_total = g(a, "IADM61") + g(e, "IEDU026.1") + g(s, "ISAL019.1")

        iadm78 = a.get("IADM78")
        iadm42 = a.get("IADM42")
        lim42 = round(g(a, "IADM61") / (iadm42 * 0.42) * 100, 2) if iadm42 else None
        lim40 = round(g(a, "IADM79") / (iadm78 * 0.40) * 100, 2) if iadm78 else None
        iadm61 = a.get("IADM61")
        lim10 = round(g(a, "IADM80") / (iadm61 * 0.10) * 100, 2) if iadm61 else None

        irh15_raw = rh.get("IRH15")
        sindato = (irh15_raw is None or irh15_raw == 0) and g(a, "IADM80") > 0

        gasto_edu_total_sector = e.get("IEDU026.1")
        gasto_sal_total_sector = s.get("ISAL019.1")

        data.setdefault(municipio, {})[anio] = {
            "poblacion": poblacion.get((municipio, anio)),
            "profesionalizacion_pct": rh.get("IADM25"),
            "participacion_femenina_pct": rh.get("IADM33"),
            "municipal_total": municipal_total,
            "educacion_total": educacion_total,
            "salud_total": salud_total,
            "consolidado_total": municipal_total + educacion_total + salud_total,
            "consolidado": {
                "planta": g(rh, "IRH05") + g(e, "IEDU040") + g(s, "MPSP"),
                "contrata": g(rh, "IRH12") + g(e, "IEDU042") + g(s, "MPSCC"),
                "cdt": g(e, "IEDU041") + g(s, "MPSCDT"),
                "honorarios": g(rh, "IRH15") + g(e, "IEDU043") + g(s, "MPSH"),
                "comunitarios": g(rh, "IRH16") + g(s, "MPSOC"),
            },
            "municipal_honorarios_sindato": sindato,
            "gasto": {
                "planta": gasto_planta,
                "contrata": gasto_contrata,
                "honorarios": gasto_honorarios,
                "comunitarios": gasto_comunitarios,
                "total": gasto_total,
            },
            "limites": {"lim42": lim42, "lim40": lim40, "lim10": lim10},
            "gasto_por_area": {
                "municipal": a.get("IADM61"),
                "educacion": gasto_edu_total_sector,
                "salud": gasto_sal_total_sector,
            },
            "areas_activas": {
                "municipal": True,
                "educacion": bool(gasto_edu_total_sector),
                "salud": bool(gasto_sal_total_sector),
            },
        }

    with open(OUT_JS, "w", encoding="utf-8") as f:
        f.write("// Generado por scripts/build_dotacion.py — no editar a mano.\n")
        f.write("const DATA_DOTACION = ")
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")

    n_comunas = len(data)
    n_rows = sum(len(v) for v in data.values())
    print(f"OK: {n_comunas} comunas, {n_rows} filas comuna-año -> {OUT_JS}")


if __name__ == "__main__":
    main()
