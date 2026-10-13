import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('audit', Path(__file__).parent/'auditar_remuneraciones.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class AuditoriaTests(unittest.TestCase):
    def test_percentiles_exactos(self):
        result = audit.distribucion([100, 200, 300, 400])
        self.assertEqual(result['mediana'], 250)
        self.assertEqual(result['p25'], 175)
        self.assertEqual(result['p75'], 325)
        self.assertEqual(sum(result['histograma']), 4)
        self.assertEqual(result['top10_n'], 1)
        self.assertEqual(result['top10_pct'], 40)

    def test_tramos_y_extremos_no_se_eliminan(self):
        result = audit.distribucion([249999, 250000, 10000000])
        self.assertEqual(result['histograma'][0], 1)
        self.assertEqual(result['histograma'][1], 1)
        self.assertEqual(result['histograma'][-1], 1)
        self.assertEqual(result['max'], 10000000)

    def test_no_infiere_nivel_desde_profesion(self):
        for text in ['Profesional', 'Ingeniero', 'Secretaria ejecutiva', 'TECNICO EN ENFERMERIA DE NIVEL', 'Enseñanza media', 'Estudiante de técnico superior']:
            self.assertEqual(audit.nivel_declarado(text)[0], 'No determinado', text)

    def test_niveles_explicitos(self):
        for text, expected in [('Licencia enseñanza básica','Básica completa'),('Enseñanza media incompleta','Media incompleta'),('TECNICO DE NIVEL SUPERIOR','Técnico superior declarado'),('Técnico nivel medio','Técnico medio declarado')]:
            self.assertEqual(audit.nivel_declarado(text)[0], expected)

    def test_monto_invalido_no_es_cero(self):
        self.assertIsNone(audit.numero('No informado'))
        self.assertIsNone(audit.numero('NaN'))
        self.assertIsNone(audit.numero('inf'))
        self.assertEqual(audit.numero('100,5'), 100.5)

    def test_filtros_areas_y_mes_ausente(self):
        fields=['organismo_codigo','organismo_nombre','anyo','mes','tipo_vinculo','tipo_estamento','tipo_calificacionp','cargo_funcion','remuneracion_bruta','origen']
        rows=[['MU001','Municipalidad de Prueba','2017','Enero','Planta','Profesional','Profesional','Cargo','100','Municipal'],
              ['MU001','Municipalidad de Prueba','2017','Enero','Planta','Técnico','Técnico superior','Cargo','300','Salud'],
              ['MU001','Municipalidad de Prueba','2016','Enero','Planta','','','','500','Municipal'],
              ['CO001','Corporación','2017','Enero','Planta','','','','900','Salud'],
              ['MU001','Municipalidad de Prueba','2017','Marzo','Planta','','','','','Municipal']]
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'fixture.csv'
            with source.open('w',newline='') as f:
                writer=csv.writer(f,delimiter=';'); writer.writerow(fields); writer.writerows(rows)
            report=audit.analizar(source,Path(tmp)/'out')
            content=(Path(tmp)/'out/data_distribucion_registros.js').read_text()
            data=json.loads(content.removeprefix('const DISTRIBUCION_REGISTROS = ').rstrip(';\n'))
            year=data['organismos']['MU001']['anios']['2017']
            self.assertEqual(year['distribuciones']['Todas']['Todos']['mediana'],200)
            self.assertIn('Salud',year['distribuciones'])
            self.assertIsNone(year['mensual'][1])
            self.assertEqual(report['conteos']['fuera_MU'],1)
            self.assertEqual(report['conteos']['fuera_periodo'],1)
            self.assertEqual(report['conteos']['monto_invalido'],1)



class CasosPuntualesTests(unittest.TestCase):
    def test_suma_periodos_y_separa_anios(self):
        from preparar_entrega import casos_desde_csv
        fields=['organismo_codigo','organismo_nombre','anyo','mes','tipo_vinculo','nombres','paterno','materno','remuneracion_bruta']
        rows=[['MU186','Municipalidad de Ñuñoa',2025,'ENERO','Honorarios','Ana','Perez','Soto',100],
              ['MU186','Municipalidad de Ñuñoa',2025,'FEBRERO','Honorarios','Ana','Perez','Soto',200],
              ['MU186','Municipalidad de Ñuñoa',2025,'ENERO','Honorarios','Otra','Perez','Soto',250],
              ['MU186','Municipalidad de Ñuñoa',2024,'ENERO','Honorarios','Antes','Perez','Soto',900],
              ['MU186','Municipalidad de Ñuñoa',2025,'ENERO','Honorarios','Negativo','Perez','Soto',-500]]
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);source=out/'original.csv'
            with source.open('w',encoding='utf-8',newline='') as f:
                w=csv.writer(f,delimiter=';');w.writerow(fields);w.writerows(rows)
            result=casos_desde_csv(source,out,2024,2025,'256MB')
            with (out/'rem_casos_puntuales.csv').open(encoding='utf-8') as f:cases=list(csv.DictReader(f))
            self.assertEqual(result['filas_honorarios_excluidas'],1)
            self.assertEqual(len(cases),3)
            self.assertEqual(cases[0]['anio'],'2024')
            self.assertEqual(cases[1]['nombre'],'Ana Perez Soto')
            self.assertEqual(float(cases[1]['monto_total_clp']),300)
            self.assertEqual(cases[1]['meses_informados'],'2')

if __name__ == '__main__':
    unittest.main()
