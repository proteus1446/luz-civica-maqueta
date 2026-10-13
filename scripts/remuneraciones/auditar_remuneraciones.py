#!/usr/bin/env python3
"""Auditoría reproducible del CSV nacional sin inferir estudios desde el cargo.

La distribución es de remuneraciones brutas de FILAS de pago, no de personas
únicas ni sueldos equivalentes. Conserva importes extremos; informa ausencias.
Biblioteca estándar, lectura secuencial y arrays compactos, sin cargar el CSV.
"""
import argparse
from array import array
from collections import Counter, defaultdict
import csv
from functools import lru_cache
import json
import math
from pathlib import Path
import re
import time
import unicodedata


@lru_cache(maxsize=100000)
def normalizar(texto):
    texto = unicodedata.normalize('NFD', texto.upper().strip())
    texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', re.sub(r'[^A-Z0-9]+', ' ', texto)).strip()


@lru_cache(maxsize=100000)
def nivel_declarado(texto):
    """Reglas textuales conservadoras, no acreditación ni clasificación legal.
    No completa textos truncados, profesiones genéricas o niveles ambiguos.
    """
    t = normalizar(texto)
    if not t or t in {'SIN PROFESION', 'SIN INFORMACION', 'NO INFORMA', 'NO APLICA', 'S I', 'S P'}:
        return 'No determinado', 'Sin evidencia de nivel'
    if any(p in t for p in ['ESTUDIANTE', 'EGRESAD', 'EN CURSO']):
        return 'No determinado', 'Estudios o título no acreditados por el texto'
    candidatos = set()
    incompleta = bool(re.search(r'\b(INCOMPLET[AO]S?|INCOMP)\b', t))
    completa = bool(re.search(r'\b(COMPLET[AO]S?|LICENCIA|LICENCIADO|APROBADA|APROBADO)\b', t))
    for palabra, etiqueta in [('BASICA', 'Básica'), ('MEDIA', 'Media')]:
        if palabra in t and any(p in t for p in ['EDUCACION', 'ENSENANZA', 'LICENCIA', 'ESCOLARIDAD']):
            if incompleta:
                candidatos.add(etiqueta + ' incompleta')
            elif completa:
                candidatos.add(etiqueta + ' completa')
    tecnico = bool(re.search(r'\b(TECNIC[OA]|TEC|TNS)\b', t))
    if tecnico and ('SUPERIOR' in t or re.search(r'\bTNS\b', t)):
        candidatos.add('Técnico superior declarado')
    if tecnico and ('NIVEL MEDIO' in t or 'TECNICO MEDIO' in t or 'TECNICA MEDIA' in t):
        candidatos.add('Técnico medio declarado')
    if 'PROFESIONAL' in t and 'UNIVERSITARIO' in t:
        candidatos.add('Profesional universitario declarado')
    if len(candidatos) == 1:
        return candidatos.pop(), 'Expresión explícita en el campo de calificación'
    if len(candidatos) > 1:
        return 'No determinado', 'Múltiples niveles: requiere revisión'
    if tecnico:
        return 'No determinado', 'Título técnico sin nivel explícito'
    return 'No determinado', 'Profesión, cargo o texto insuficiente para determinar nivel'


def numero(texto):
    # Misma interpretación numérica del pipeline original; no adivina miles.
    try:
        n = float(texto.strip().replace(',', '.'))
        return n if math.isfinite(n) else None
    except (ValueError, AttributeError):
        return None


def percentil(ordenados, q):
    indice = (len(ordenados) - 1) * q
    abajo = int(indice)
    arriba = min(abajo + 1, len(ordenados) - 1)
    return ordenados[abajo] + (ordenados[arriba] - ordenados[abajo]) * (indice - abajo)


LIMITES = [0, 250000, 500000, 750000, 1000000, 1500000, 2000000, 3000000, 5000000, 10000000]


def distribucion(importes):
    vals = sorted(importes)
    n = len(vals)
    if not n:
        return None
    total = math.fsum(vals)
    hist = [0] * len(LIMITES)
    for v in vals:
        tramo = len(LIMITES) - 1
        for i in range(len(LIMITES) - 1):
            if v < LIMITES[i + 1]:
                tramo = i
                break
        hist[tramo] += 1
    n_top = max(1, math.ceil(n * .1))
    return {
        'n': n, 'total': round(total, 2), 'min': vals[0], 'max': vals[-1],
        'mediana': round(percentil(vals, .5), 2),
        'p10': round(percentil(vals, .1), 2), 'p25': round(percentil(vals, .25), 2),
        'p75': round(percentil(vals, .75), 2), 'p90': round(percentil(vals, .9), 2),
        'top10_n': n_top, 'top10_pct': round(math.fsum(vals[-n_top:]) / total * 100, 2),
        'histograma': hist,
    }


def analizar(fuente, salida, desde=2017, hasta=2025, max_filas=None):
    inicio = time.monotonic()
    fuente = Path(fuente)
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    importes = defaultdict(lambda: array('d'))
    mensual = defaultdict(lambda: [0, 0.0])
    audit = Counter()
    anual = Counter()
    origenes = Counter()
    niveles = Counter()
    estamentos = Counter()
    calificaciones = Counter()
    cargos = Counter()
    cruces = Counter()
    nombres = {}
    exclusion_codigos = Counter()
    requeridos = ['organismo_codigo','organismo_nombre','anyo','mes','tipo_vinculo',
                  'tipo_estamento','tipo_calificacionp','cargo_funcion','remuneracion_bruta','origen']
    meses = {m: i for i, m in enumerate(['ENERO','FEBRERO','MARZO','ABRIL','MAYO','JUNIO',
             'JULIO','AGOSTO','SEPTIEMBRE','OCTUBRE','NOVIEMBRE','DICIEMBRE'], 1)}
    with fuente.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.reader(f, delimiter=';')
        encabezado = next(reader)
        idx = {campo: encabezado.index(campo) for campo in requeridos}
        for fila in reader:
            audit['filas_leidas'] += 1
            if len(fila) != len(encabezado):
                audit['filas_malformadas'] += 1
                continue
            codigo = fila[idx['organismo_codigo']].strip()
            if not re.fullmatch(r'MU\d+', codigo):
                audit['fuera_MU'] += 1
                exclusion_codigos[codigo[:12]] += 1
                continue
            try:
                anio = int(fila[idx['anyo']])
            except ValueError:
                audit['anio_invalido'] += 1
                continue
            if not desde <= anio <= hasta:
                audit['fuera_periodo'] += 1
                continue
            audit['filas_en_alcance'] += 1
            anual[anio] += 1
            nombres[codigo] = fila[idx['organismo_nombre']].strip()
            origen = fila[idx['origen']].strip() or 'Sin origen declarado'
            vinculo = fila[idx['tipo_vinculo']].strip() or 'Sin vínculo declarado'
            estamento = fila[idx['tipo_estamento']].strip()
            calificacion = fila[idx['tipo_calificacionp']].strip()
            cargo = fila[idx['cargo_funcion']].strip()
            origenes[origen] += 1
            estamentos[(origen, estamento)] += 1
            calificaciones[calificacion] += 1
            cargos[(origen, cargo)] += 1
            nivel, motivo = nivel_declarado(calificacion)
            niveles[nivel] += 1
            cruces[(origen, normalizar(estamento), nivel)] += 1
            mes = meses.get(normalizar(fila[idx['mes']]))
            if mes is None:
                audit['mes_invalido'] += 1
                continue
            monto = numero(fila[idx['remuneracion_bruta']])
            if monto is None:
                audit['monto_invalido'] += 1
            elif monto <= 0:
                audit['monto_cero_o_negativo'] += 1
            else:
                audit['pagos_positivos'] += 1
                importes[(codigo, anio, origen, vinculo)].append(monto)
                mensual[(codigo, anio, mes)][0] += 1
                mensual[(codigo, anio, mes)][1] += monto
            if audit['filas_leidas'] % 500000 == 0:
                print(f"{audit['filas_leidas']:,} filas leídas; {audit['filas_en_alcance']:,} MU {desde}-{hasta}; {time.monotonic()-inicio:.0f}s", flush=True)
            if max_filas and audit['filas_leidas'] >= max_filas:
                break
    print('Lectura terminada; calculando percentiles exactos de registros...', flush=True)
    grupos = defaultdict(dict)
    datos = {}
    for (codigo, anio, area, vinculo), vals in importes.items():
        grupos[(codigo, anio)].setdefault(area, {})[vinculo] = vals
    for contador, ((codigo, anio), areas) in enumerate(sorted(grupos.items()), 1):
        todo = array('d')
        por_vinculo = defaultdict(lambda: array('d'))
        vistas = {}
        for area, vinculos in areas.items():
            vista = {}
            area_vals = array('d')
            for vinculo, vals in vinculos.items():
                vista[vinculo] = distribucion(vals)
                area_vals.extend(vals)
                por_vinculo[vinculo].extend(vals)
            vista['Todos'] = distribucion(area_vals)
            todo.extend(area_vals)
            vistas[area] = vista
        vistas['Todas'] = {v: distribucion(vals) for v, vals in por_vinculo.items()}
        vistas['Todas']['Todos'] = distribucion(todo)
        meses_anio = [
            {'mes': m, 'n': mensual[(codigo, anio, m)][0],
             'total': round(mensual[(codigo, anio, m)][1], 2)}
            if (codigo, anio, m) in mensual else None for m in range(1, 13)
        ]
        datos.setdefault(codigo, {'nombre': nombres[codigo], 'anios': {}})['anios'][str(anio)] = {
            'distribuciones': vistas, 'mensual': meses_anio,
        }
        if contador % 400 == 0:
            print(f'{contador:,}/{len(grupos):,} combinaciones organismo-año calculadas', flush=True)
    meta = {
        'fuente': fuente.name, 'desde': desde, 'hasta': hasta,
        'filtro': 'organismo_codigo MU seguido de dígitos',
        'unidad': 'pesos nominales; remuneracion_bruta por fila de pago positiva',
        'unidad_analisis': 'registros de pago, NO personas únicas ni sueldos por jornada',
        'percentiles': 'interpolación lineal (n-1)*q sobre pagos positivos',
        'alcance_areas': 'origen declarado en el archivo, sin inferirlo desde estamento o profesión',
        'duplicados': 'No se deduplicaron pagos; una fila no acredita un contrato distinto',
        'clasificacion': 'Lectura textual exploratoria; no valida títulos ni cumplimiento legal',
        'muestra': bool(max_filas), 'limites_histograma': LIMITES,
    }
    payload = {'meta': meta, 'organismos': datos}
    (salida/'data_distribucion_registros.js').write_text(
        'const DISTRIBUCION_REGISTROS = '+json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False)+';\n', encoding='utf-8')
    informe = {'meta': meta, 'conteos': dict(audit), 'organismos': len(nombres),
               'por_anio': dict(sorted(anual.items())), 'por_origen': dict(origenes),
               'niveles_textuales': dict(niveles), 'valores_calificacion_distintos': len(calificaciones),
               'valores_estamento_por_origen': len(estamentos), 'valores_cargo_por_origen': len(cargos),
               'codigos_excluidos': exclusion_codigos.most_common(25)}
    (salida/'auditoria.json').write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding='utf-8')
    with (salida/'calificaciones_para_revision.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(['texto_original','texto_normalizado','filas','nivel_propuesto','evidencia'])
        for texto, n in calificaciones.most_common():
            writer.writerow([texto, normalizar(texto), n, *nivel_declarado(texto)])
    with (salida/'estamentos_para_revision.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(['origen_declarado','estamento_original','estamento_normalizado','filas'])
        for (origen, texto), n in estamentos.most_common():
            writer.writerow([origen, texto, normalizar(texto), n])
    with (salida/'cruces_estudios_estamento.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(['origen_declarado','estamento_normalizado','nivel_textual_propuesto','filas'])
        for (origen, estamento, nivel), n in cruces.most_common():
            writer.writerow([origen, estamento, nivel, n])
    print(json.dumps(informe, ensure_ascii=False), flush=True)
    print(f'Terminado en {time.monotonic()-inicio:.1f}s', flush=True)
    return informe


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fuente', required=True)
    parser.add_argument('--salida', required=True)
    parser.add_argument('--desde', type=int, default=2017)
    parser.add_argument('--hasta', type=int, default=2025)
    parser.add_argument('--max-filas', type=int)
    args = parser.parse_args()
    analizar(args.fuente, args.salida, args.desde, args.hasta, args.max_filas)
