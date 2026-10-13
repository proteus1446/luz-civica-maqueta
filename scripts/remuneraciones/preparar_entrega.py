#!/usr/bin/env python3
"""CSV nacional -> agregados pequeños para Postgres/Supabase y web estática.
No necesita IA. Python 3.10+; DuckDB solo para casos puntuales desde el origen.
"""
import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path
from auditar_remuneraciones import analizar, LIMITES

STATS=['n','total','min','p10','p25','mediana','p75','p90','max','top10_n','top10_pct']
HEADERS=['organismo_codigo','organismo_nombre','anio','area','vinculo',*STATS]
MESES=['ENERO','FEBRERO','MARZO','ABRIL','MAYO','JUNIO','JULIO','AGOSTO','SEPTIEMBRE','OCTUBRE','NOVIEMBRE','DICIEMBRE']

def leer_js(path, variable):
    text=Path(path).read_text(encoding='utf-8')
    prefix='const '+variable+' ='
    if prefix not in text: raise ValueError(f'Falta {variable} en {path}')
    return json.loads(text.split(prefix,1)[1].strip().rstrip(';'))

def escribir_csv(path, headers, rows):
    with Path(path).open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f);w.writerow(headers);w.writerows(rows)

def exportar(payload, salida):
    """Los CSV contienen campos tipados sin formato monetario ni porcentual."""
    stats=[];mensual=[];hist=[];organismos=[]
    for codigo,o in sorted(payload['organismos'].items()):
        organismos.append([codigo,o['nombre']])
        for year,a in sorted(o['anios'].items()):
            for area,vs in a['distribuciones'].items():
                for vinc,d in vs.items():
                    assert sum(d['histograma'])==d['n']
                    assert d['min']<=d['p10']<=d['p25']<=d['mediana']<=d['p75']<=d['p90']<=d['max']
                    stats.append([codigo,o['nombre'],int(year),area,vinc,*[d[k] for k in STATS]])
                    for i,n in enumerate(d['histograma']):
                        hist.append([codigo,int(year),area,vinc,i,LIMITES[i],LIMITES[i+1] if i+1<len(LIMITES) else None,n])
            for m in a['mensual']:
                if m: mensual.append([codigo,int(year),m['mes'],m['n'],m['total']])
            d=a['distribuciones']['Todas']['Todos']
            assert sum(m['n'] for m in a['mensual'] if m)==d['n']
            assert abs(sum(m['total'] for m in a['mensual'] if m)-d['total'])<.1
    escribir_csv(salida/'rem_organismos.csv',['organismo_codigo','organismo_nombre'],organismos)
    escribir_csv(salida/'rem_distribuciones.csv',HEADERS,stats)
    escribir_csv(salida/'rem_mensual.csv',['organismo_codigo','anio','mes','n','total'],mensual)
    escribir_csv(salida/'rem_histogramas.csv',['organismo_codigo','anio','area','vinculo','tramo','desde_clp','hasta_clp','n'],hist)
    return {'organismos':len(organismos),'distribuciones':len(stats),'meses':len(mensual),'tramos':len(hist)}

def casos_desde_csv(fuente, salida, desde, hasta, memoria='1GB'):
    """Dos meses con filas positivas no acreditan duración efectiva del contrato.
    Se agrupa por nombres originales exactos, apellidos, vínculo y organismo.
    No se fusionan variantes ni se deduplican importes.
    """
    import duckdb
    db_path=salida/'_casos.duckdb'
    if db_path.exists(): raise ValueError('Ya existe una base temporal de casos; use otra carpeta de salida.')
    db=duckdb.connect(str(db_path),config={'memory_limit':memoria,'threads':2,'temp_directory':str(salida/'temporales')})
    db.execute('SET preserve_insertion_order=false')
    meses='CASE upper(trim(mes)) '+' '.join(f"WHEN '{m}' THEN {i}" for i,m in enumerate(MESES,1))+' END'
    # No ignore_errors: un CSV malformado detiene la ejecución.
    db.execute(f'''CREATE TABLE honorarios AS
      SELECT trim(organismo_codigo) codigo, trim(organismo_nombre) organismo_nombre,
        try_cast(anyo AS INTEGER) anio, {meses} mes,
        trim(tipo_vinculo) vinculo,
        coalesce(trim(nombres),'') nombres, coalesce(trim(paterno),'') paterno,
        coalesce(trim(materno),'') materno,
        try_cast(replace(trim(remuneracion_bruta),',','.') AS DOUBLE) monto
      FROM read_csv(?,delim=';',header=true,all_varchar=true)
      WHERE regexp_full_match(trim(organismo_codigo),'MU[0-9]+')
        AND try_cast(anyo AS INTEGER) BETWEEN ? AND ?
        AND trim(tipo_vinculo) IN ('Honorarios','Código Trabajo','Código del Trabajo')''',[str(fuente),desde,hasta])
    omitted=db.execute('''SELECT count(*) FROM honorarios
      WHERE mes IS NULL OR monto IS NULL OR NOT isfinite(monto) OR monto<=0
      OR concat(nombres,paterno,materno)='' ''').fetchone()[0]
    rows=[]
    consulta='''WITH personas AS (
      SELECT codigo, min(organismo_nombre) organismo_nombre, anio, vinculo,
        nombres,paterno,materno,count(DISTINCT mes) meses_informados,
        count(*) registros,sum(monto) monto_total_clp
      FROM honorarios WHERE anio=? AND mes IS NOT NULL AND monto>0 AND isfinite(monto)
        AND concat(nombres,paterno,materno)<>''
      GROUP BY codigo,anio,vinculo,nombres,paterno,materno
      HAVING count(DISTINCT mes) BETWEEN 1 AND 2
    ), ranking AS (
      SELECT *,row_number() OVER(PARTITION BY codigo,anio
        ORDER BY monto_total_clp DESC,vinculo,nombres,paterno,materno) posicion
      FROM personas
    ) SELECT codigo,organismo_nombre,anio,posicion,
       trim(concat_ws(' ',nullif(nombres,''),nullif(paterno,''),nullif(materno,''))) nombre,
       vinculo,meses_informados,registros,round(monto_total_clp,2)
      FROM ranking WHERE posicion<=5 ORDER BY codigo,anio,posicion'''
    for year in range(desde,hasta+1):
        print(f'Casos puntuales: {year}',flush=True)
        rows.extend(db.execute(consulta,[year]).fetchall())
    headers=['organismo_codigo','organismo_nombre','anio','posicion','nombre','vinculo','meses_informados','registros','monto_total_clp']
    escribir_csv(salida/'rem_casos_puntuales.csv',headers,rows)
    db.close()
    db_path.unlink()
    return {'casos_puntuales':len(rows),'filas_honorarios_excluidas':omitted,'casos_desde':desde,'casos_hasta':hasta}

def casos_desde_web(perfiles, payload, salida):
    """Exporta la salida histórica existente. Su procedencia queda en manifiesto."""
    from reparar_casos_remuneraciones import comuna
    codes={comuna(o['nombre']):c for c,o in payload['organismos'].items()}
    rows=[]
    for key,e in perfiles.items():
        codigo=codes.get(key)
        if not codigo: continue
        for year,cs in e.get('honorarios_contexto',{}).get('top_casos_por_anio',{}).items():
            for i,c in enumerate(cs,1):
                rows.append([codigo,e['nombre'],int(year),i,c['nombre'],c['vinculo'],c['meses'],None,c['monto']])
    escribir_csv(salida/'rem_casos_puntuales.csv',['organismo_codigo','organismo_nombre','anio','posicion','nombre','vinculo','meses_informados','registros','monto_total_clp'],sorted(rows))
    return {'casos_puntuales':len(rows),'procedencia_casos':'honorarios_personas.csv, salida anterior incorporada en la web; registros no disponibles en esta exportación'}

def actualizar_web(salida, web):
    """Actualiza nueva distribución y casos; conserva grupos anteriores y su año."""
    from reparar_casos_remuneraciones import comuna
    target=web/'data/data_remuneraciones.js'
    perfiles=leer_js(target,'COMUNAS_REM')
    groups={}
    with (salida/'rem_casos_puntuales.csv').open(encoding='utf-8',newline='') as f:
        for r in csv.DictReader(f):
            key=comuna(r['organismo_nombre'])
            groups.setdefault(key,{}).setdefault(r['anio'],[]).append({'nombre':r['nombre'],'anyo':int(r['anio']),
                'meses':int(r['meses_informados']),'monto':float(r['monto_total_clp']),
                'vinculo':r['vinculo'],'tipo_periodo':'esporadico'})
    for key,e in perfiles.items():
        hc=e.setdefault('honorarios_contexto',{})
        hc['top_casos_por_anio']=groups.get(key,{})
        hc['top_casos_anio']=hc['top_casos_por_anio'].get(str(e['anyo']),[])
        hc['top_casos']=hc['top_casos_anio']
        hc['top_casos_historico']=sorted((c for cs in hc['top_casos_por_anio'].values() for c in cs),key=lambda c:c['monto'],reverse=True)[:5]
    payload=leer_js(salida/'data_distribucion_registros.js','DISTRIBUCION_REGISTROS')
    for codigo,o in payload['organismos'].items():
        key=comuna(o['nombre'])
        if key not in perfiles: continue  # Nuevos organismos requieren región en el catálogo.
        gasto=perfiles[key].setdefault('gasto_mensual',{})
        for year,a in o['anios'].items():
            if year not in gasto:
                gasto[year]={'total':[m['total'] if m else None for m in a['mensual']], 'vinculo':{},'estamento':{}}
    # Respaldo local único antes de reemplazar el detalle de casos.
    backup=target.with_suffix('.js.bak')
    if not backup.exists(): shutil.copy2(target,backup)
    target.write_text('const COMUNAS_REM = '+json.dumps(perfiles,ensure_ascii=False,separators=(',',':'),allow_nan=False)+';\n',encoding='utf-8')
    shutil.copy2(salida/'data_distribucion_registros.js',web/'data/data_distribucion_registros.js')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fuente',type=Path,help='CSV gigante original; separador punto y coma, UTF-8')
    p.add_argument('--salida',required=True,type=Path)
    p.add_argument('--desde',default=2017,type=int);p.add_argument('--hasta',default=2025,type=int)
    p.add_argument('--casos-desde',default=2015,type=int)
    p.add_argument('--distribucion-existente',type=Path,help='Reutilizar auditoría completa verificada')
    p.add_argument('--casos-web-existente',type=Path,help='Exportar casos ya calculados; alternativa a releer el original')
    p.add_argument('--memoria-casos',default='1GB')
    p.add_argument('--web',type=Path,help='Opcional: actualizar archivos de datos del sitio existente')
    a=p.parse_args()
    if a.desde>a.hasta or a.casos_desde>a.hasta:p.error('Período inválido')
    if not a.fuente and not(a.distribucion_existente and a.casos_web_existente):p.error('Indique --fuente o ambos archivos existentes')
    a.salida.mkdir(parents=True,exist_ok=True)
    if any(a.salida.glob('rem_*.csv')):p.error('La salida contiene CSV de otra entrega. Use una carpeta nueva para evitar mezclar versiones.')
    distrib=a.salida/'data_distribucion_registros.js'
    if a.distribucion_existente:
        payload=leer_js(a.distribucion_existente,'DISTRIBUCION_REGISTROS')
        if payload['meta'].get('muestra'):p.error('No se puede publicar una auditoría de muestra')
        shutil.copy2(a.distribucion_existente,distrib)
    else:
        print('1/3 Auditoría completa del original; puede tardar varios minutos.',flush=True)
        analizar(a.fuente,a.salida,a.desde,a.hasta)
        payload=leer_js(distrib,'DISTRIBUCION_REGISTROS')
    print('2/3 CSV agregados y comprobaciones.',flush=True)
    manifest={'metodo':payload['meta'],'tablas':exportar(payload,a.salida)}
    print('3/3 Casos puntuales.',flush=True)
    if a.casos_web_existente:
        manifest['tablas'].update(casos_desde_web(leer_js(a.casos_web_existente,'COMUNAS_REM'),payload,a.salida))
    else:manifest['tablas'].update(casos_desde_csv(a.fuente,a.salida,a.casos_desde,a.hasta,a.memoria_casos))
    manifest['archivos']={}
    for f in sorted(a.salida.glob('rem_*.csv')):
        manifest['archivos'][f.name]={'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}
    if a.fuente:manifest['fuente']={'nombre':a.fuente.name,'bytes':a.fuente.stat().st_size}
    (a.salida/'manifiesto.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    if a.web:actualizar_web(a.salida,a.web)
    print(json.dumps(manifest['tablas'],ensure_ascii=False),flush=True)
    print('CSV listos. No se ha cargado nada a Supabase. No se recalcularon los grupos salariales heredados.',flush=True)

if __name__=='__main__':main()
