#!/usr/bin/env python3
"""Carga CSV verificados con COPY, en una transacción; contraseña solo en entorno.
Instalar: pip install 'psycopg[binary]==3.2.6'. Crear tablas con el SQL entregado.
"""
import argparse,csv,hashlib,json,os
from pathlib import Path
TABLES=['rem_organismos','rem_distribuciones','rem_mensual','rem_histogramas','rem_casos_puntuales']

def validar(salida):
    m=json.loads((salida/'manifiesto.json').read_text(encoding='utf-8'))
    counts={}
    for t in TABLES:
        p=salida/(t+'.csv')
        assert hashlib.sha256(p.read_bytes()).hexdigest()==m['archivos'][p.name]['sha256'],f'Archivo modificado: {p.name}'
        with p.open(encoding='utf-8',newline='') as f:
            r=csv.reader(f);header=next(r);n=0
            for row in r:
                if len(row)!=len(header):raise ValueError(f'Fila inválida en {p.name}')
                n+=1
        if not n:raise ValueError(f'{p.name} no tiene datos; revisar antes de cargar')
        counts[t]=n
    return counts

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--datos',required=True,type=Path)
    p.add_argument('--validar',action='store_true',help='Solo valida archivos; no conecta')
    p.add_argument('--reemplazar',action='store_true',help='Reemplaza el contenido de las cinco tablas rem_* de esta entrega, dentro de una transacción')
    a=p.parse_args();counts=validar(a.datos)
    if a.validar:print(json.dumps(counts));return
    import psycopg
    url=os.environ.get('SUPABASE_DB_URL')
    if not url:raise SystemExit('Falta SUPABASE_DB_URL. Usar conexión Postgres directa o Session pooler, con sslmode=require.')
    # COPY no usa la API REST ni credenciales dentro del frontend.
    with psycopg.connect(url,sslmode='require') as conn:
        with conn.cursor() as cur:
            cur.execute('SET LOCAL statement_timeout=0')
            for t in TABLES:
                cur.execute(f'CREATE TEMP TABLE stage_{t} (LIKE public.{t} INCLUDING DEFAULTS) ON COMMIT DROP')
                with cur.copy(f'COPY stage_{t} FROM STDIN WITH (FORMAT CSV, HEADER TRUE)') as copy:
                    with (a.datos/(t+'.csv')).open('rb') as f:
                        while block:=f.read(1024*1024):copy.write(block)
                cur.execute(f'SELECT count(*) FROM stage_{t}')
                if cur.fetchone()[0]!=counts[t]:raise ValueError('Conteo diferente después de COPY: '+t)
            # Bloqueo impide que otra carga se mezcle con esta versión.
            cur.execute('LOCK TABLE '+','.join('public.'+t for t in TABLES)+' IN ACCESS EXCLUSIVE MODE')
            cur.execute('SELECT '+','.join('(SELECT count(*) FROM public.'+t+')' for t in TABLES))
            if any(cur.fetchone()) and not a.reemplazar:raise ValueError('Ya hay datos. Para una renovación completa y revisada use --reemplazar.')
            if a.reemplazar:
                for t in reversed(TABLES):cur.execute('DELETE FROM public.'+t)
            for t in TABLES:cur.execute(f'INSERT INTO public.{t} SELECT * FROM stage_{t}')
    print('Carga confirmada: '+json.dumps(counts))
if __name__=='__main__':main()
