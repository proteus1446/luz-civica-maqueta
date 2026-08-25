#!/usr/bin/env python3
"""
Agrega el sueldo del alcalde/alcaldesa (mediana mensual) al catálogo de
variables del Explorador Comunal (explorador-comunal.html), usando el mismo
dato que ya muestra panel_comunal.html (campo "alcalde" dentro de
data/data_panel_comunal.js, construido a partir de
/Users/cristobal/Downloads/Panel_alcalde_remuneracion(1).xlsx).

Sigue el mismo patrón que build_explorador_variables.py: solo agrega
series[comuna][año] + ranking[año] a DB.data, y una entrada nueva a
DB.catalog. No toca las variables existentes.
"""
import json
import re
import statistics
import unicodedata

DATA_DIR = "/Users/cristobal/Downloads/maqueta/data"
EXPLORADOR = "/Users/cristobal/Downloads/maqueta/explorador-comunal.html"


def norm_name(s):
    s = unicodedata.normalize("NFD", s.upper())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def build_key_mapping(db):
    """data_panel_comunal.js usa comuna_key() (conserva Ñ), pero el DB del
    explorador usa claves 100% ASCII (CAMINA, NUNOA, O HIGGINS...) — se
    mapean por nombre de display, que sí coincide en ambos lados."""
    with open(f"{DATA_DIR}/nombres_comunas.js", encoding="utf-8") as f:
        nombres = json.loads(re.search(r"const NOMBRES_COMUNAS = (\{.*?\});", f.read(), re.S).group(1))
    explorer_by_norm = {norm_name(v): k for k, v in db["nombres"].items()}
    mapping = {}
    for mykey, myname in nombres.items():
        ek = explorer_by_norm.get(norm_name(myname))
        if ek:
            mapping[mykey] = ek
    return mapping


def load_js_object(path, varname):
    with open(path, encoding="utf-8") as f:
        content = f.read()
    m = re.search(r"const " + varname + r"\s*=\s*", content)
    start = m.end()
    return json.JSONDecoder().raw_decode(content, start)[0]


def build_series_and_ranking(dataset, key_mapping):
    series = {}
    all_years = set()
    for comuna, years in dataset.items():
        explorer_key = key_mapping.get(comuna)
        if not explorer_key:
            continue
        ser = {}
        for anio, record in years.items():
            alcalde = record.get("alcalde")
            if not alcalde:
                continue
            v = alcalde.get("mediana")
            if isinstance(v, (int, float)):
                ser[anio] = v
                all_years.add(anio)
        if ser:
            series[explorer_key] = ser

    ranking = {}
    for anio in all_years:
        vals = [ser[anio] for ser in series.values() if anio in ser]
        if not vals:
            continue
        ranking[anio] = {
            "mediana_nacional": round(statistics.median(vals), 3),
            "total_comunas": len(vals),
        }
    return series, ranking


def main():
    with open(EXPLORADOR, encoding="utf-8") as f:
        content = f.read()

    idx = content.find("const DB")
    tail_start = content.find(";\n", idx)
    db_str = content[idx + len("const DB = \n"): tail_start]
    db = json.loads(db_str)
    key_mapping = build_key_mapping(db)

    var_id = "adm_alcalde_sueldo"
    existing_ids = {c["id"] for c in db["catalog"]}
    if var_id in existing_ids:
        print(f"{var_id} ya existe en el catálogo — no se hace nada.")
        return

    dataset = load_js_object(f"{DATA_DIR}/data_panel_comunal.js", "DATA_PANEL_COMUNAL")
    series, ranking = build_series_and_ranking(dataset, key_mapping)
    if not series:
        print("AVISO: sin datos para adm_alcalde_sueldo")
        return

    db["catalog"].append({
        "id": var_id,
        "area": "Administración",
        "label": "Remuneración bruta (sueldo) del alcalde/alcaldesa (mediana mensual)",
        "unidad": "$",
        "code": "alcalde.mediana",
    })
    db["data"][var_id] = {"series": series, "ranking": ranking}

    new_db_str = json.dumps(db, ensure_ascii=False, separators=(",", ":"))
    new_content = content[:idx] + "const DB = \n" + new_db_str + content[tail_start:]

    with open(EXPLORADOR, "w", encoding="utf-8") as f:
        f.write(new_content)

    n_comunas = len(series)
    print(f"OK: {var_id} agregado ({n_comunas} comunas con dato, {len(db['catalog'])} variables en total)")


if __name__ == "__main__":
    main()
