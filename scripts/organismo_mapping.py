#!/usr/bin/env python3
"""
Mapeo compartido organismo_codigo/organismo_nombre (archivos de la carpeta
"script sueldo/") -> comuna_key (misma clave usada en el resto del sitio,
p.ej. "MAIPU", "ÑUÑOA"). Usado por todos los scripts build_remuneraciones_*.py.
"""
import re

from build_administracion import comuna_key

# Casos donde el nombre en los archivos de sueldo no calza directo con
# comuna_key() incluso después de limpiar el prefijo "Municipalidad de" y los
# paréntesis — verificado contra las 345 comunas de data/nombres_comunas.js.
ALIASES_ORGANISMO = {
    "CABO DE HORNOS Y ANTARTICA": "CABO DE HORNOS",
    "LA CALERA": "CALERA",
    "LLAY LLAY": "LLAILLAY",
    "MARCHIGE": "MARCHIHUE",
    "OHIGGINS": "O´HIGGINS",
    "PAIHUANO": "PAIGUANO",
    "PUERTO NATALES": "NATALES",
    "SAN VICENTE DE TAGUA TAGUA": "SAN VICENTE",
}


def organismo_a_comuna_key(nombre):
    s = re.sub(r"^(Ilustre\s+)?(I\.\s*)?Municipalidad de\s+", "", str(nombre).strip(), flags=re.I)
    s = re.sub(r"\s*\([^)]*\)", "", s)  # quita paréntesis, ej. "(Rapa Nui)"
    key = comuna_key(s.strip())
    return ALIASES_ORGANISMO.get(key, key)
