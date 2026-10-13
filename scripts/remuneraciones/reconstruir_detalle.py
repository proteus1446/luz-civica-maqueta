#!/usr/bin/env python3
"""Cadena heredada opcional. Recalcula grupos y anomalías; varias pasadas del CSV.
Requiere espacio para persona_grupo.csv y al menos 6 GB de memoria disponibles.
No modifica las reglas estadísticas anteriores. No aplica profesiones propuestas.
"""
import argparse,os,shutil,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--fuente',required=True,type=Path);p.add_argument('--salida',required=True,type=Path)
p.add_argument('--web',required=True,type=Path)
a=p.parse_args();root=Path(__file__).resolve().parents[2];out=a.salida.resolve();web=a.web.resolve()
out.mkdir(parents=True,exist_ok=True)
if any(out.glob('*.csv')):p.error('Use una carpeta de salida nueva.')
shutil.copy2(Path(__file__).parent/'legacy/tabla_regimen.csv',out/'tabla_regimen.csv')
env=os.environ.copy();env.update(REM_LEGACY_DIR=str(out),REM_WEB_DIR=str(web),RUTA_DATOS=str(a.fuente.resolve()))
# Los builders importan organismo_mapping desde scripts.
for script in ['preparar_grupos.py','gasto_y_honorarios.py','detectar_outliers.py']:
 subprocess.run([sys.executable,str(Path(__file__).parent/'legacy'/script)],env=env,check=True)
backup=web/'data/data_remuneraciones.antes_detalle.js'
if not backup.exists():shutil.copy2(web/'data/data_remuneraciones.js',backup)
for i in range(1,5):
 subprocess.run([sys.executable,str(root/f'scripts/build_remuneraciones_f{i}.py')],cwd=root/'scripts',env=env,check=True)
subprocess.run([sys.executable,str(Path(__file__).parent/'reparar_casos_remuneraciones.py'),'--datos-js',str(web/'data/data_remuneraciones.js'),'--csv-dir',str(out)],check=True)
print('Detalle heredado reconstruido. Ejecute preparar_entrega.py --web para sincronizar pagos y casos del año seleccionado.')
