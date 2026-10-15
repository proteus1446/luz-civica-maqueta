"""Genera una base anual de prueba; no elimina categorías de la selección GitHub."""
from pathlib import Path
import json, unicodedata, math, hashlib
import pandas as pd
import openpyxl
from shapely.geometry import shape, mapping
from shapely import orient_polygons

import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--entradas',type=Path,required=True,help='Carpeta con cead.parquet, poblacion.csv y r01.geojson a r16.geojson')
parser.add_argument('--sinim',type=Path,required=True,help='Archivo SINIM Social y comunitaria')
args=parser.parse_args()
ROOT=args.entradas
REPO=Path(__file__).resolve().parents[1]
OUT=REPO/'data'; OUT.mkdir(exist_ok=True)
def norm(s):
    return ''.join(c for c in unicodedata.normalize('NFD',str(s).upper()) if unicodedata.category(c)!='Mn').replace('´',"'")
def jsdata(path,name):
    s=path.read_text();return json.JSONDecoder().raw_decode(s[s.index('{'):])[0]
names=jsdata(REPO/'data/nombres_comunas.js','NOMBRES_COMUNAS')
namekeys={norm(v):k for k,v in names.items()}
aliases={'AISEN':'AYSEN','COIHAIQUE':'COYHAIQUE','TREGUACO':'TREHUACO'}
x=pd.read_parquet(ROOT/'cead.parquet')
x['anio']=pd.to_datetime(x.fecha).dt.year
assert not x.duplicated(['cut_comuna','fecha','delito']).any()
bad=x.delito_n.notna() & x.delito_n.mod(1).ne(0)
fixes=x.loc[bad,['comuna','fecha','delito','delito_n']].copy()
fixes['corregido']=(fixes.delito_n*1000).round()
x.loc[bad,'delito_n']=(x.loc[bad,'delito_n']*1000).round()
assert x.delito_n.notna().all() and x.delito_n.mod(1).eq(0).all() and x.delito_n.ge(0).all()
a=x.groupby(['cut_comuna','comuna','cut_region','region','anio','delito'],observed=True).agg(casos=('delito_n','sum'),meses=('fecha','nunique')).reset_index()
assert a.meses.eq(12).all()
p=pd.read_csv(ROOT/'poblacion.csv').rename(columns={'año':'anio','población':'poblacion'})
a=a.merge(p[['cut_comuna','anio','poblacion']],on=['cut_comuna','anio'],how='left',validate='many_to_one')
assert a.poblacion.notna().all() and a.poblacion.gt(0).all()
years=sorted(int(y) for y in a.anio.unique()); delitos=sorted(str(d) for d in a.delito.unique())
wb=openpyxl.load_workbook(args.sinim,read_only=True,data_only=True)
rows=wb.worksheets[0].iter_rows(values_only=True);header=next(rows)
codes={'camaras':'MNSEGCIUCA','drones':'MNSEGCIUD','autos':'MNSEGCIUAU','camionetas':'MNSEGCIUCM','motos':'MNSEGCIUMO','bicicletas':'MNSEGCIUBI','inspectores':'MNSEGCIUIN','profesionales':'MNSEGCIU','casetas':'MNSEGCIUC'}
idx={k:next(i for i,h in enumerate(header) if str(h).split(' ')[0]==v) for k,v in codes.items()}
iy=next(i for i,h in enumerate(header) if str(h).strip().upper()=='AÑO')
security={}
for r in rows:
    try:cut=str(int(r[0])).zfill(5);y=str(int(r[iy]))
    except (TypeError,ValueError):continue
    security.setdefault(cut,{})[y]={k:int(r[i]) if isinstance(r[i],(int,float)) and math.isfinite(r[i]) and r[i]>=0 else None for k,i in idx.items()}
wb.close()
comunas={}
for cut,g in a.groupby('cut_comuna',observed=True):
    first=g.iloc[0];cut=str(int(cut)).zfill(5);n=norm(first.comuna);n=aliases.get(n,n)
    key=namekeys.get(n)
    if key is None:
        key=next((k for k in names if norm(k)==n),None)
    if key is None:raise ValueError('Sin clave de portal: '+str(first.comuna))
    rec={'nombre':names[key],'clave_portal':key,'region':str(int(first.cut_region)).zfill(2),'nombre_region':str(first.region),'anios':{}}
    for y,h in g.groupby('anio',observed=True):
        by=dict(zip(h.delito.astype(str),h.casos));counts=[int(by[d]) for d in delitos]
        rec['anios'][str(int(y))]={'poblacion':int(h.iloc[0].poblacion),'casos':sum(counts),'categorias':counts,'seguridad':security.get(cut,{}).get(str(int(y)))}
    comunas[cut]=rec
metadata={'titulo':'Suma de categorías seleccionadas de casos policiales','fuente_original':'CEAD, Carabineros y PDI','recopilacion':'Bastián Olea / delincuencia_chile','url_repositorio':'https://github.com/bastianolea/delincuencia_chile','fecha_descarga':'2026-10-14','formula_tasa':'Casos del año / población proyectada del mismo año × 100000','fuente_poblacion':'censo_proyecciones_año.csv del mismo repositorio; proyecciones INE base 2017','fuente_recursos':'SINIM, 5-Social_y_comunitaria.xlsx','indicadores_sinim':codes,'correccion_numerica':'Valores fraccionarios multiplicados por 1000 según interpretación de separadores confirmada por el usuario; enteros sin modificar. No recupera separadores perdidos en valores como 1.000 → 1.0.','limites':['Se conservan las 30 categorías de GitHub sin filtrar, por instrucción del usuario.','No equivale al total completo de las ocho familias CEAD: excluye categorías y conserva superposición en armas.','Los recursos municipales son cantidades declaradas, no actividad operativa, inversión ni eficacia.','No permite atribuir causalidad a la gestión municipal. Carabineros, PDI, denuncia, población flotante y otros factores también influyen.','SINIM: los datos ausentes se guardan como null; los ceros numéricos se conservan como declarados.','Los años iniciales requieren validar comparabilidad por cambios de clasificación; 12 registros mensuales no prueban cobertura sustantiva completa.']}
out={'metadata':metadata,'anios':years,'delitos':delitos,'comunas':comunas}
write=lambda path,v:path.write_text(json.dumps(v,ensure_ascii=False,separators=(',',':'),allow_nan=False))
write(OUT/'seguridad_comunal.json',out)
fixes['fecha']=fixes.fecha.astype(str);write(OUT/'seguridad_correcciones.json',fixes.to_dict('records'))
fs=[]
for r in range(1,17):
    for f in json.loads((ROOT/f'r{r:02}.geojson').read_text())['features']:
        cut=str(int(f['properties']['codigo_comuna'])).zfill(5)
        if cut not in comunas:continue
        geo=orient_polygons(shape(f['geometry']).simplify(.0015,preserve_topology=True),exterior_cw=True)
        geo=json.loads(json.dumps(mapping(geo)),parse_float=lambda v:round(float(v),5))
        fs.append({'type':'Feature','properties':{'cut':cut,'region':str(r).zfill(2)},'geometry':geo})
write(OUT/'seguridad_comunas.geojson',{'type':'FeatureCollection','features':fs})
assert set(comunas)=={f['properties']['cut'] for f in fs}
assert comunas['13120']['anios']['2025']['casos']==13650
report={'comunas':len(comunas),'categorias':len(delitos),'anios':years,'registros_mensuales':len(x),'correcciones_numericas':int(bad.sum()),'nunoa2025':comunas['13120']['anios']['2025'],'sha256_fuente':hashlib.sha256((ROOT/'cead.parquet').read_bytes()).hexdigest()}
write(OUT/'seguridad_validacion.json',report)
print(json.dumps({k:v for k,v in report.items() if k!='nunoa2025'},ensure_ascii=False))
print('Ñuñoa recursos 2025:',report['nunoa2025']['seguridad'])
