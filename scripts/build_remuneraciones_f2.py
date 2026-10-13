#!/usr/bin/env python3
"""
Remuneraciones — Fase 2: Honorarios/Código del Trabajo con percentiles reales,
panorama y contexto (top casos), desde honorarios_personas.csv (211MB) y
honorarios_ranking_comunas.csv. No requiere el archivo nacional de 12GB.

Fórmulas (verificadas exactas contra Ñuñoa/Maipú/Puerto Montt, año más
reciente de cada comuna):
  honorarios[vinculo] (solo tipo_periodo == 'sostenido'):
    n        = cantidad de personas
    mediana/p10/p25/p75/p90/min/max = percentiles de mediana_mensual
    gasto_total = sum(mediana_mensual * meses_informados)   [no se usa en el
                  render actual — no hay forma de reproducir el original
                  exacto sin el archivo nacional; campo sin efecto visual]
    sobre_2M = cantidad con mediana_mensual > 2.000.000
  honorarios_panorama:
    n_total          = personas Honorarios+Código Trabajo (sostenido+esporádico)
    pct_sostenido     = % de n_total con tipo_periodo=='sostenido'
    mediana_tipica    = mediana de mediana_mensual entre sostenidos (ambos vínculos)
    pct_multitrabajo  = % con max_trabajos_simultaneos > 1
  honorarios_contexto:
    ratio_pct         = honorarios_pct_personal (honorarios_ranking_comunas.csv)
    percentil_nacional = percentil_nacional (idem)
    top_casos         = top 5 casos esporádicos por monto_total_periodo,
                         TODOS los años disponibles de la comuna (no solo el
                         año más reciente)
"""
import json
import re
import sys

import pandas as pd

sys.path.insert(0, ".")
from organismo_mapping import organismo_a_comuna_key

HONORARIOS_CSV = "/Users/cristobal/prueba/luz-civica-web/script sueldo/honorarios_personas.csv"
RANKING_CSV = "/Users/cristobal/prueba/luz-civica-web/script sueldo/honorarios_ranking_comunas.csv"
F1_JSON = "/Users/cristobal/Downloads/maqueta/data/remuneraciones_f1.json"
OUT_JSON = "/Users/cristobal/Downloads/maqueta/data/remuneraciones_f2.json"

UMBRAL_2M = 2_000_000


def nombre_legible(persona_id):
    partes = [p.strip().title() for p in str(persona_id).split("|") if p.strip()]
    return " ".join(partes)


def main():
    with open(F1_JSON, encoding="utf-8") as f:
        f1 = json.load(f)
    anyo_por_comuna = {k: v["anyo"] for k, v in f1.items()}

    df = pd.read_csv(HONORARIOS_CSV, sep=";")
    df["comuna_key"] = df["organismo_nombre"].map(organismo_a_comuna_key)

    ranking = pd.read_csv(RANKING_CSV, sep=";")
    ranking["comuna_key"] = ranking["organismo_nombre"].map(organismo_a_comuna_key)
    ranking_idx = ranking.set_index(["comuna_key", "anyo"])

    resultado = {}
    for comuna_key, anyo in anyo_por_comuna.items():
        sub_anyo = df[(df["comuna_key"] == comuna_key) & (df["anyo"] == anyo)]
        sub_todos = df[df["comuna_key"] == comuna_key]
        if sub_anyo.empty:
            continue

        sost = sub_anyo[sub_anyo["tipo_periodo"] == "sostenido"]

        honorarios = {}
        for vinc in ("Honorarios", "Código Trabajo"):
            v = sost[sost["tipo_vinculo"] == vinc]
            if v.empty:
                continue
            m = v["mediana_mensual"]
            honorarios[vinc] = {
                "n": int(len(v)),
                "mediana": float(m.median()),
                "p10": float(m.quantile(0.10)),
                "p25": float(m.quantile(0.25)),
                "p75": float(m.quantile(0.75)),
                "p90": float(m.quantile(0.90)),
                "min": float(m.min()),
                "max": float(m.max()),
                "gasto_total": float((v["mediana_mensual"] * v["meses_informados"]).sum()),
                "sobre_2M": int((m > UMBRAL_2M).sum()),
            }

        n_total_hc = int(len(sub_anyo))
        pct_sostenido = round(len(sost) / n_total_hc * 100, 2) if n_total_hc else 0
        mediana_tipica = float(sost["mediana_mensual"].median()) if len(sost) else None
        pct_multitrabajo = (round((sub_anyo["max_trabajos_simultaneos"] > 1).mean() * 100, 2)
                             if n_total_hc else 0)

        honorarios_panorama = {
            "n_total": n_total_hc,
            "pct_sostenido": pct_sostenido,
            "mediana_tipica": mediana_tipica,
            "pct_multitrabajo": pct_multitrabajo,
        }

        ratio_pct = percentil_nacional = None
        if (comuna_key, anyo) in ranking_idx.index:
            row = ranking_idx.loc[(comuna_key, anyo)]
            ratio_pct = float(row["honorarios_pct_personal"])
            percentil_nacional = float(row["percentil_nacional"])
        honorarios_contexto = {"ratio_pct": ratio_pct, "percentil_nacional": percentil_nacional}

        esporadicos = sub_todos[sub_todos["tipo_periodo"] == "esporadico"]
        top5 = esporadicos.sort_values("monto_total_periodo", ascending=False).head(5)
        honorarios_contexto["top_casos"] = [
            {
                "nombre": nombre_legible(r["persona_id"]),
                "anyo": int(r["anyo"]),
                "meses": int(r["meses_informados"]),
                "monto": float(r["monto_total_periodo"]),
                "vinculo": r["tipo_vinculo"],
                "tipo_periodo": r["tipo_periodo"],
                "trabajos_simultaneos": int(r["max_trabajos_simultaneos"]),
            }
            for _, r in top5.iterrows()
        ]

        resultado[comuna_key] = {
            "honorarios": honorarios,
            "honorarios_panorama": honorarios_panorama,
            "honorarios_contexto": honorarios_contexto,
        }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False)

    print(f"OK: {len(resultado)} comunas -> {OUT_JSON}")


if __name__ == "__main__":
    main()
