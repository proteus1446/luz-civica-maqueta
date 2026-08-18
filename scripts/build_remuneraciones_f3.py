#!/usr/bin/env python3
"""
Remuneraciones — Fase 3: casos destacados anuales y mensuales, por área
(Municipal/Salud/Educación), desde outliers_detectados.csv y
outliers_detectados_mensual.csv (49MB). No requiere el archivo nacional.

Fórmulas (verificadas exactas contra Ñuñoa/Maipú/Puerto Montt):
  n_atipicos       = cantidad total de filas en outliers_detectados.csv para
                      esa comuna+año (ya viene pre-filtrado por z_robusto>=3.5
                      —4.5 en Salud— o flag_extras_altas, en el script 2 del
                      pipeline original)
  tasa_atipicos_100 = n_atipicos / n_total * 100
  casos_<area>      = top 8 filas de outliers_detectados.csv para esa comuna
                      +año+pestana, ordenadas por z_robusto descendente
  casos_mensuales_<area> = top 8 filas de outliers_detectados_mensual.csv,
                      mismo criterio pero ordenado por z_robusto_mes
"""
import json
import re
import sys

import pandas as pd

sys.path.insert(0, ".")
from organismo_mapping import organismo_a_comuna_key

OUTLIERS_CSV = "/Users/cristobal/prueba/luz-civica-web/script sueldo/outliers_detectados.csv"
OUTLIERS_MENSUAL_CSV = "/Users/cristobal/prueba/luz-civica-web/script sueldo/outliers_detectados_mensual.csv"
F1_JSON = "/Users/cristobal/Downloads/maqueta/data/remuneraciones_f1.json"
OUT_JSON = "/Users/cristobal/Downloads/maqueta/data/remuneraciones_f3.json"

AREAS = {"Municipal": "municipal", "Salud": "salud", "Educación": "educacion"}
TOP_N = 8


def nombre_legible(persona_id):
    partes = [p.strip().title() for p in str(persona_id).split("|") if p.strip()]
    return " ".join(partes)


def grado_de(row):
    for c in ("grado_municipal", "categoria_salud", "horas_jornada_edu"):
        v = row.get(c)
        if pd.notna(v):
            return str(v).rstrip(".0") if isinstance(v, float) and v == int(v) else str(v)
    return None


def num_o_none(v, cast=float):
    return cast(v) if pd.notna(v) else None


def caso_dict(row, con_mes=False):
    d = {
        "nombre": nombre_legible(row["persona_id"]),
        "cargo": row.get("cargo_funcion"),
        "estamento": row.get("estamento_norm"),
        "grado": grado_de(row),
        "vinculo": row.get("tipo_vinculo"),
        "monto": float(row["base_sin_extras"]),
        "mediana_grupo": num_o_none(row.get("mediana_grupo")),
        "n_grupo": num_o_none(row.get("n_grupo"), int),
    }
    if con_mes:
        d["mes"] = row.get("mes")
    return d


def main():
    with open(F1_JSON, encoding="utf-8") as f:
        f1 = json.load(f)
    anyo_por_comuna = {k: v["anyo"] for k, v in f1.items()}

    anual = pd.read_csv(OUTLIERS_CSV, sep=";")
    anual["comuna_key"] = anual["organismo_nombre"].map(organismo_a_comuna_key)

    mensual = pd.read_csv(OUTLIERS_MENSUAL_CSV, sep=";")
    mensual["comuna_key"] = mensual["organismo_nombre"].map(organismo_a_comuna_key)

    resultado = {}
    for comuna_key, anyo in anyo_por_comuna.items():
        sub_anual = anual[(anual["comuna_key"] == comuna_key) & (anual["anyo"] == anyo)]
        sub_mensual = mensual[(mensual["comuna_key"] == comuna_key) & (mensual["anyo"] == anyo)]

        n_atipicos = int(len(sub_anual))
        n_total = f1[comuna_key]["n_total"]
        tasa_atipicos_100 = round(n_atipicos / n_total * 100, 2) if n_total else 0

        entry = {"n_atipicos": n_atipicos, "tasa_atipicos_100": tasa_atipicos_100}
        for pestana, sufijo in AREAS.items():
            an = sub_anual[sub_anual["pestana"] == pestana].sort_values("z_robusto", ascending=False).head(TOP_N)
            me = sub_mensual[sub_mensual["pestana"] == pestana].sort_values("z_robusto_mes", ascending=False).head(TOP_N)
            entry[f"casos_{sufijo}"] = [caso_dict(r) for _, r in an.iterrows()]
            entry[f"casos_mensuales_{sufijo}"] = [caso_dict(r, con_mes=True) for _, r in me.iterrows()]

        resultado[comuna_key] = entry

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False)

    print(f"OK: {len(resultado)} comunas -> {OUT_JSON}")


if __name__ == "__main__":
    main()
