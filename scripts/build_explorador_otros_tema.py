#!/usr/bin/env python3
"""
Mueve al tema "Otros" (nuevo) las variables del Explorador Comunal que no
vienen de SINIM: la remuneración del alcalde (Panel_alcalde_remuneracion.xlsx)
y las 3 que sí vienen de Contraloría (deficit, deuda_flotante,
deuda_flotante_pagado_pct — ver build_administracion.py líneas 9/46).

El resto de las variables "Contraloría" que parecían serlo por estar mezcladas
en el mismo grupo de KPIs de Administración (dependencia_fcm=IADM75,
ejecucion=IADM125, eficiencia_cobro=IADM100, ingresos.fcm_recibido) en
realidad vienen de SINIM, así que se quedan en el tema Administración.

Solo cambia el campo "area" de esas 4 entradas en DB.catalog — no toca
DB.data ni ninguna otra variable.
"""
import json

EXPLORADOR = "/Users/cristobal/Downloads/maqueta/explorador-comunal.html"

# ids a mover -> nuevo area
MOVER = {
    "adm_alcalde_sueldo": "Otros",
    "adm_deficit": "Otros",
    "adm_deuda_flotante": "Otros",
    "adm_deuda_flotante_pct": "Otros",
}


def main():
    with open(EXPLORADOR, encoding="utf-8") as f:
        content = f.read()

    idx = content.find("const DB")
    tail_start = content.find(";\n", idx)
    db_str = content[idx + len("const DB = \n"): tail_start]
    db = json.loads(db_str)

    changed = []
    for c in db["catalog"]:
        if c["id"] in MOVER:
            c["area"] = MOVER[c["id"]]
            changed.append(c["id"])

    missing = set(MOVER) - set(changed)
    if missing:
        print("AVISO: no encontrados en el catálogo:", missing)

    new_db_str = json.dumps(db, ensure_ascii=False, separators=(",", ":"))
    new_content = content[:idx] + "const DB = \n" + new_db_str + content[tail_start:]

    with open(EXPLORADOR, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"OK: {len(changed)} variables movidas a 'Otros': {changed}")


if __name__ == "__main__":
    main()
