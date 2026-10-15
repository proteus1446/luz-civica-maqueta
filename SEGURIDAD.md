# Mapa de seguridad comunal

Abrir `seguridad_comunal.html` mediante un servidor HTTP. La portada, el panel comunal y el perfil enlazan al módulo. Se preservan los parámetros `comuna` y `anio`.

## Alcance de los datos

345 comunas, 2010–2025, 30 categorías de la recopilación de Bastián Olea de CEAD. La opción inicial suma todas las categorías, según la selección solicitada: **no representa el total completo de las ocho familias oficiales**, conserva superposición en armas y excluye otras categorías. La interfaz lo informa y permite explorar cada categoría por separado.

Las tasas usan población proyectada del mismo año del repositorio de origen, base INE 2017. No se utiliza población 2024 fija para años diferentes. Los cambios anuales comparan tasas, no frecuencias. Los recursos se consultan para el mismo año y se conservan valores nulos frente a ceros declarados. No se calcula gasto, índice de eficacia ni efecto causal.

Se corrigieron 108 valores fraccionarios del Parquet multiplicándolos por 1.000, según la interpretación de separadores acordada; `data/seguridad_correcciones.json` conserva los registros antes y después. No se modificaron valores enteros. Los registros ambiguos por separadores ya perdidos y la comparabilidad histórica requieren validación contra CEAD antes de tratar los resultados como cifras oficiales.

En Ñuñoa 2025 se reproduce la selección: 13.650 casos / 270.521 habitantes × 100.000 = 5.045,819. Recursos SINIM: 200 cámaras, 1 dron, 20 autos, 6 camionetas, 16 motos, 4 bicicletas; inspectores sin dato.

## Regenerar

Dependencias del generador: Python, pandas, pyarrow, openpyxl y shapely >= 2.1. Los archivos fuente no se incluyen en el repositorio.

En una carpeta de entradas reunir:

- `cead.parquet`: `datos/procesados/cead_delincuencia_chile.parquet` del repositorio de casos.
- `poblacion.csv`: `app/censo_proyecciones_año.csv` del mismo repositorio.
- `r01.geojson` a `r16.geojson`: cartografía comunal de chilemapas.
- Archivo SINIM `5-Social_y_comunitaria.xlsx`, fuera del repositorio.

```sh
python scripts/build_seguridad.py --entradas /ruta/entradas --sinim /ruta/Social_y_comunitaria.xlsx
python scripts/check_seguridad.py
```

La cartografía se simplifica con tolerancia 0,0015 grados. Se orientan polígonos para D3; no es cartografía oficial ni sirve para determinar límites legales.

## Fuentes y atribuciones

- CEAD, Carabineros y PDI: https://cead.minsegpublica.gob.cl/estadisticas-delictuales/
- Recopilación de Bastián Olea, datos y población: https://github.com/bastianolea/delincuencia_chile
- Recursos municipales: SINIM / SUBDERE, archivo Social y comunitaria.
- Geometrías: https://github.com/pachadotdev/chilemapas/tree/master/data_geojson/comunas
- D3 7.9.0: Mike Bostock. Licencia ISC conservada en `vendor/d3-LICENSE`.

## Validación

El generador rechaza claves mensuales duplicadas, números de casos negativos o fraccionarios tras corrección, años con menos de 12 registros mensuales, población ausente o no positiva, claves comunales sin correspondencia con el portal y códigos sin geometría. Esto valida consistencia estructural, no la calidad del registro original.

Revisar en navegador: selección de comuna y año; mapa nacional y por región; cambio anual con año anterior cero o ausente; cambio de categoría; zoom; series con datos faltantes; navegación al panel; adaptación a pantalla estrecha. No interpretar asociaciones temporales como causalidad municipal.
