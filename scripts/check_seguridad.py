"""Controles de integridad de la entrega estática de seguridad (sin dependencias externas)."""
import json, math
from pathlib import Path
root=Path(__file__).resolve().parents[1]
d=json.loads((root/'data/seguridad_comunal.json').read_text())
g=json.loads((root/'data/seguridad_comunas.geojson').read_text())
assert len(d['comunas'])==345 and len(d['delitos'])==30
assert {f['properties']['cut'] for f in g['features']}==set(d['comunas'])
for cut,c in d['comunas'].items():
    assert len(cut)==5 and c['clave_portal']
    assert {int(y) for y in c['anios']}==set(d['anios'])
    for year,r in c['anios'].items():
        assert len(r['categorias'])==len(d['delitos'])
        assert sum(r['categorias'])==r['casos']
        assert r['poblacion']>0
        assert all(isinstance(v,int) and v>=0 for v in r['categorias'])
        assert math.isfinite(r['casos']/r['poblacion']*100000)
n=d['comunas']['13120']['anios']['2025']
assert n['casos']==13650 and n['poblacion']==270521
assert abs(n['casos']/n['poblacion']*100000-5045.818993719527)<1e-8
assert n['seguridad']['drones']==1 and n['seguridad']['inspectores'] is None
assert d['comunas']['13120']['anios']['2024']['seguridad']['drones']==0
print('OK: 345 comunas, 30 categorías, 16 años; sumas, población, tasas, geometría y ausencia frente a cero.')
