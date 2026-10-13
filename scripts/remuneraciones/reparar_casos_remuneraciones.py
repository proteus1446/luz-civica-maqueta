#!/usr/bin/env python3
"""Actualiza casos desde salidas existentes, conservando clasificación original.

Añade meses informados y corrige grados terminados en cero. No vuelve a
detectar anomalías, no reclasifica profesiones, no usa el archivo nacional.
"""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import re
import unicodedata


ALIASES={'CABO DE HORNOS Y ANTARTICA':'CABO DE HORNOS','LA CALERA':'CALERA','LLAY LLAY':'LLAILLAY','MARCHIGE':'MARCHIHUE','OHIGGINS':'O´HIGGINS','PAIHUANO':'PAIGUANO','PUERTO NATALES':'NATALES','SAN VICENTE DE TAGUA TAGUA':'SAN VICENTE'}


def comuna(nombre):
    nombre=re.sub(r'^(Ilustre\s+)?(I\.\s*)?Municipalidad de\s+','',nombre.strip(),flags=re.I)
    nombre=re.sub(r'\s*\([^)]*\)','',nombre).strip().upper().replace('Ñ','\x01')
    nombre=''.join(c for c in unicodedata.normalize('NFD',nombre) if unicodedata.category(c)!='Mn').replace('\x01','Ñ')
    return ALIASES.get(nombre,nombre)


def grado(row):
    for field in ['grado_municipal','categoria_salud','horas_jornada_edu']:
        value=row.get(field,'').strip()
        if not value or value.lower() in {'nan','null'}:
            continue
        try:
            numeric=float(value)
            return str(int(numeric)) if numeric.is_integer() else str(numeric)
        except ValueError:
            return value
    return None


def num(value, default=None):
    try:
        return float(value)
    except (ValueError,TypeError):
        return default


def nombre(persona):
    return ' '.join(p.strip().title() for p in persona.split('|') if p.strip())


def caso(row, mensual=False):
    out={'nombre':nombre(row['persona_id']), 'cargo':row.get('cargo_funcion'),
         'estamento':row.get('estamento_norm'), 'grado':grado(row),
         'vinculo':row.get('tipo_vinculo'), 'monto':num(row['base_sin_extras']),
         'mediana_grupo':num(row.get('mediana_grupo')), 'n_grupo':num(row.get('n_grupo'))}
    if mensual:
        out['mes']=row.get('mes')
    else:
        out['meses_informados']=num(row.get('meses_informados'))
        out['flag_extras_altas']=str(row.get('flag_extras_altas','')).lower() in {'true','1','t'}
        out['extras_mediana']=num(row.get('extras_mediana'))
    return out


def reparar(datos_js, csv_dir):
    datos_js=Path(datos_js)
    contenido=datos_js.read_text()
    data=json.loads(contenido.split('const COMUNAS_REM = ',1)[1].rstrip(';\n'))
    areas={'Municipal':'municipal','Salud':'salud','Educación':'educacion'}
    for filename,mensual in [('outliers_detectados.csv',False),('outliers_detectados_mensual.csv',True)]:
        grupos=defaultdict(list)
        counts=defaultdict(int)
        with (Path(csv_dir)/filename).open(encoding='utf-8-sig',newline='') as f:
            for row in csv.DictReader(f,delimiter=';'):
                key=comuna(row['organismo_nombre'])
                if key not in data or int(row['anyo']) != data[key]['anyo']:
                    continue
                counts[key]+=1
                if row['pestana'] in areas:
                    grupos[(key,areas[row['pestana']])].append(row)
        for key,entry in data.items():
            if not mensual:
                entry['n_atipicos']=counts[key]
            for area in areas.values():
                filas=sorted(grupos[(key,area)],key=lambda r:num(r.get('z_robusto_mes' if mensual else 'z_robusto'),-float('inf')),reverse=True)[:8]
                entry[('casos_mensuales_' if mensual else 'casos_')+area]=[caso(r,mensual) for r in filas]
    honorarios=defaultdict(list)
    with (Path(csv_dir)/'honorarios_personas.csv').open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f,delimiter=';'):
            key=comuna(row['organismo_nombre'])
            if key not in data or row['tipo_periodo']!='esporadico':
                continue
            honorarios[key].append(row)
    for key,entry in data.items():
        if 'honorarios_contexto' not in entry:
            continue
        casos=[
            {'nombre':nombre(r['persona_id']), 'anyo':int(r['anyo']), 'meses':int(r['meses_informados']),
             'monto':num(r['monto_total_periodo']), 'vinculo':r['tipo_vinculo'],
             'tipo_periodo':r['tipo_periodo'], 'trabajos_simultaneos':int(r['max_trabajos_simultaneos'])}
            for r in sorted(honorarios[key],key=lambda r:num(r['monto_total_periodo'],0),reverse=True)
        ]
        hc=entry['honorarios_contexto']
        hc['top_casos_historico']=casos[:5]
        hc['top_casos_anio']=[c for c in casos if c['anyo']==entry['anyo']][:5]
        hc['top_casos_por_anio']={str(y):[c for c in casos if c['anyo']==y][:5] for y in sorted({c['anyo'] for c in casos})}
        hc['top_casos']=hc['top_casos_historico']
    datos_js.write_text('// Casos actualizados por reparar_casos_remuneraciones.py; agrupaciones originales conservadas.\nconst COMUNAS_REM = '+json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False)+';\n')
    print(f'Casos actualizados para {len(data)} comunas; meses informados, grados y año explícitos.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--datos-js',required=True)
    parser.add_argument('--csv-dir',required=True)
    args=parser.parse_args()
    reparar(args.datos_js,args.csv_dir)
