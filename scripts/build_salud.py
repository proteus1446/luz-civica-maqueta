#!/usr/bin/env python3
"""
Genera data/data_salud.js a partir de datos reales SINIM (4-SALUD.xlsx), para
las 345 comunas de Chile, años 2008-2025.

A diferencia de Administración/Dotación, esta página consume los códigos SINIM
"en crudo" (sin renombrar a un esquema propio) — el JS de maqueta_salud.html
lee directamente d.ISAL019, d.MPSP, etc. Este script simplemente vuelca las
columnas usadas por la página, ya identificadas comparando el DATA embebido
original (5 comunas de muestra) contra las columnas reales del archivo SINIM.

Nota: MVACU y MTFCOTR existen en el archivo SINIM y en la especificación de
variables, pero el JS de la página NO los referencia (grep confirmó 0 usos) —
se omiten a propósito para no incluir datos que la página no consume.
"""
import json
import re
import openpyxl

from build_administracion import comuna_key, num

SINIM_SALUD = "/Users/cristobal/prueba/sinim/4-SALUD.xlsx"
OUT_JS = "/Users/cristobal/Downloads/maqueta/data/data_salud.js"

# Códigos numéricos usados por maqueta_salud.html (confirmado por inspección del
# DATA embebido original + grep del JS). MTAS se maneja aparte por ser texto.
CODES_NUM = [
    "GTCM", "HPISM", "ISAL005", "ISAL009", "ISAL010", "ISAL012", "ISAL013",
    "ISAL015", "ISAL018", "ISAL019", "ISAL021", "ISAL023", "ISAL025",
    "ISAL029", "ISAL031", "ISAL032", "ISAL23", "MAMBUL", "MCECOF", "MCESFAM",
    "MCOSAM", "MDENTAL", "MNCGR", "MNCGU", "MNPR", "MPSCC", "MPSCDT", "MPSH",
    "MPSOC", "MPSP", "MSAPU", "MSFARM", "MSOPT", "MTFCE", "MTFCM", "MTFFOND",
    "MTFGER", "MTFKINE", "MTFMATRO", "MTFNUTRI", "MTFODON", "MTFPSICO",
    "MTFPSIQ", "MTFTECENF", "MTFTECMED",
]
CODE_TEXT = "MTAS"


def find_col(header, code):
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


def main():
    wb = openpyxl.load_workbook(SINIM_SALUD, read_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = ws.iter_rows(values_only=True)
    header = next(rows)

    idx_num = {c: find_col(header, c) for c in CODES_NUM}
    idx_text = find_col(header, CODE_TEXT)
    idx_anio = find_anio_col(header)

    data = {}
    for r in rows:
        if r[0] is None:
            continue
        municipio = comuna_key(str(r[1]).strip())
        anio = str(r[idx_anio])
        record = {c: num(r[i]) for c, i in idx_num.items()}
        raw_text = r[idx_text]
        record[CODE_TEXT] = raw_text if isinstance(raw_text, str) else None
        data.setdefault(municipio, {})[anio] = record

    with open(OUT_JS, "w", encoding="utf-8") as f:
        f.write("// Generado por scripts/build_salud.py — no editar a mano.\n")
        f.write("const DATA_SALUD = ")
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")

    n_comunas = len(data)
    n_rows = sum(len(v) for v in data.values())
    print(f"OK: {n_comunas} comunas, {n_rows} filas comuna-año -> {OUT_JS}")


if __name__ == "__main__":
    main()
