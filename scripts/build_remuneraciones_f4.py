#!/usr/bin/env python3
"""
Remuneraciones — Fase 4: gasto mensual por vínculo/estamento (todos los años
disponibles) y gasto_anual_total, desde gasto_mensual.csv. Luego ensambla
F1+F2+F3+F4 en data/data_remuneraciones.js.

Fórmulas (verificadas exactas contra Ñuñoa/Maipú/Puerto Montt):
  gasto_anual_total        = sum(gasto_total) del año más reciente de la comuna
  gasto_mensual[año].total = gasto_total sumado por mes (12 valores, Ene-Dic)
  gasto_mensual[año].vinculo[v]   = ídem, filtrado por tipo_vinculo
  gasto_mensual[año].estamento[e] = ídem, filtrado por estamento
"""
import json
import re
import sys

import pandas as pd

sys.path.insert(0, ".")
from organismo_mapping import organismo_a_comuna_key
from build_remuneraciones_f1 import FULL_REGION_NAMES

GASTO_CSV = "/Users/cristobal/prueba/luz-civica-web/script sueldo/gasto_mensual.csv"
REGIONES_JS = "/Users/cristobal/Downloads/maqueta/data/regiones_comunas.js"
F1_JSON = "/Users/cristobal/Downloads/maqueta/data/remuneraciones_f1.json"
F2_JSON = "/Users/cristobal/Downloads/maqueta/data/remuneraciones_f2.json"
F3_JSON = "/Users/cristobal/Downloads/maqueta/data/remuneraciones_f3.json"
OUT_JS = "/Users/cristobal/Downloads/maqueta/data/data_remuneraciones.js"

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def serie_12_meses(df, filtro=None):
    d = df if filtro is None else df[filtro]
    por_mes = d.groupby("mes_num")["gasto_total"].sum()
    return [float(por_mes.get(i, 0.0)) for i in range(1, 13)]


def main():
    with open(F1_JSON, encoding="utf-8") as f:
        f1 = json.load(f)
    with open(F2_JSON, encoding="utf-8") as f:
        f2 = json.load(f)
    with open(F3_JSON, encoding="utf-8") as f:
        f3 = json.load(f)
    with open(REGIONES_JS, encoding="utf-8") as f:
        content = f.read()
    region_por_comuna = json.loads(re.search(r"const REGION_POR_COMUNA = (\{.*?\});", content, re.S).group(1))

    df = pd.read_csv(GASTO_CSV, sep=";")
    df["comuna_key"] = df["organismo_nombre"].map(organismo_a_comuna_key)

    resultado = {}
    for comuna_key, base in f1.items():
        sub = df[df["comuna_key"] == comuna_key]
        if sub.empty:
            continue
        anyo_actual = base["anyo"]

        gasto_mensual = {}
        for anyo, sub_anyo in sub.groupby("anyo"):
            vinculos = sorted(sub_anyo["tipo_vinculo"].dropna().unique())
            estamentos = sorted(sub_anyo["estamento"].dropna().unique())
            gasto_mensual[str(int(anyo))] = {
                "total": serie_12_meses(sub_anyo),
                "vinculo": {v: serie_12_meses(sub_anyo, sub_anyo["tipo_vinculo"] == v) for v in vinculos},
                "estamento": {e: serie_12_meses(sub_anyo, sub_anyo["estamento"] == e) for e in estamentos},
            }

        gasto_anual_total = float(sub[sub["anyo"] == anyo_actual]["gasto_total"].sum())

        codigo_region = region_por_comuna.get(comuna_key)
        region_nombre = FULL_REGION_NAMES.get(codigo_region, "Región no identificada")

        entry = dict(base)
        entry["region"] = region_nombre
        entry.update(f2.get(comuna_key, {}))
        entry.update(f3.get(comuna_key, {}))
        entry["gasto_mensual"] = gasto_mensual
        entry["gasto_anual_total"] = gasto_anual_total
        resultado[comuna_key] = entry

    with open(OUT_JS, "w", encoding="utf-8") as f:
        f.write("// Generado por scripts/build_remuneraciones_f{1,2,3,4}.py — no editar a mano.\n")
        f.write("const COMUNAS_REM = ")
        json.dump(resultado, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")

    print(f"OK: {len(resultado)} comunas -> {OUT_JS}")


if __name__ == "__main__":
    main()
