# Entrega de remuneraciones de Luz Cívica

## Qué se entrega

La página `remuneraciones.html`, su módulo de presentación y sus datos JavaScript funcionan sin Supabase, como la versión revisada localmente. Esta entrega añade un proceso independiente para obtener tablas pequeñas destinadas a Supabase. **Subir los CSV a Supabase no cambia automáticamente la fuente de datos de la página.**

El Excel `Remuneraciones_tecnico.xlsx` sirve para revisión: resumen general de 2017–2025, casos de 2025, diccionario y pasos de trabajo. Para importar use los cinco CSV completos, no el Excel. No contiene los 31 millones de pagos individuales.

| Archivo | Una fila representa | Tabla Supabase |
|---|---|---|
| rem_organismos.csv | Un organismo MU | rem_organismos |
| rem_distribuciones.csv | Comuna/año/área/vínculo, con conteo, suma y percentiles | rem_distribuciones |
| rem_mensual.csv | Comuna/año/mes observado | rem_mensual |
| rem_histogramas.csv | Un tramo de importes dentro de cada distribución | rem_histogramas |
| rem_casos_puntuales.csv | Uno de los cinco mayores períodos de 1–2 meses de cada comuna/año | rem_casos_puntuales |

En la entrega inicial: 324 organismos, 45.554 distribuciones, 31.547 meses observados, 455.540 tramos y 15.120 casos puntuales. Las distribuciones proceden de la auditoría completa de 30.953.244 pagos positivos MU de 2017–2025. Los casos de esta entrega se regeneraron leyendo completo el CSV original con el nuevo procesador DuckDB, desde 2015 a 2025. Su columna `registros` indica las filas positivas incluidas. La exportación opcional desde el JavaScript anterior conserva su procedencia y deja esa columna vacía. Los datos nuevos de casos incluyen organismos que no tenían detalle heredado: no son una copia exacta de todas las listas anteriores. La procedencia está en `manifiesto.json`.

## 1. Instalar una vez

Descargar el repositorio, abrir una terminal en su carpeta raíz y crear un entorno Python 3.10 o posterior:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r scripts/remuneraciones/requirements.txt
```

En Windows use `py -m venv .venv`, active con `.venv\Scripts\Activate.ps1` y use `python` en los comandos. No necesita una IA ni claves de OpenAI.

## 2. Regenerar desde el CSV gigante

Conservar el original fuera del repositorio. Debe ser UTF-8, separador `;`, y mantener los encabezados originales. No abrirlo ni volver a guardarlo con Excel. El procesador necesita, entre otros, código y nombre del organismo, año, mes en español, vínculo, origen, remuneración bruta, nombres y apellidos; la auditoría también utiliza estamento, calificación y cargo.

```bash
python scripts/remuneraciones/preparar_entrega.py \
  --fuente "/ruta/TA_PersonalMunicipal_2008_2025_NUEVO_LIMPIO.csv" \
  --salida "salida/entrega_2025" \
  --desde 2017 --hasta 2025 --casos-desde 2015
```

Usar una carpeta de salida nueva en cada ejecución. La auditoría lee el CSV secuencialmente y conserva importes en arrays para calcular percentiles exactos; **no es un algoritmo de memoria constante**. La ejecución completa anterior tardó unos 12 minutos en este equipo, pero el tiempo depende del equipo y los datos. Para el proceso nuevo conviene disponer de al menos 8 GB de RAM y espacio para la entrada y archivos temporales. El cálculo de casos usa DuckDB con 1 GB de límite, disco temporal y lotes por año. Si falta memoria, puede usar `--memoria-casos 2GB` en un equipo con recursos suficientes. No estimar resultados desde una muestra ni promediar medianas.

El script genera los cinco CSV, el JavaScript de distribución, un manifiesto con hashes SHA-256 y salidas de auditoría. La propuesta de estudios es exploratoria: **no se utiliza para reclasificar los pagos**. Los CSV que se importan contienen resúmenes, no todas las profesiones ni todos los pagos personales.

Para refrescar la web estática existente, agregar `--web "/ruta/luz-civica-maqueta"`. Actualiza distribución y casos; conserva el detalle heredado por grupos y su año. Hacer primero una prueba en una copia del sitio. Los nuevos años se incorporan al selector del sitio existente; revisar el catálogo comunal al incorporar organismos nuevos.

Para exportar de nuevo los datos ya calculados sin releer 12 GB:

```bash
python scripts/remuneraciones/preparar_entrega.py \
  --salida "salida/exportacion_existente" \
  --distribucion-existente data/data_distribucion_registros.js \
  --casos-web-existente data/data_remuneraciones.js
```

## 3. Carga manual inicial a Supabase

1. Abrir el proyecto Supabase. En **SQL Editor**, ejecutar `supabase/remuneraciones.sql`. Crea cinco tablas con claves, tipos y acceso público de solo lectura para los datos de transparencia.
2. En **Table Editor**, abrir `rem_organismos`, elegir **Insert → Import Data from CSV**, seleccionar su CSV y revisar la correspondencia de encabezados.
3. Repetir, en este orden: `rem_distribuciones`, `rem_mensual`, `rem_histogramas`, `rem_casos_puntuales`.
4. Los archivos usan coma como separador CSV, punto decimal y UTF-8. No contienen símbolos `$`, separadores de miles ni porcentajes escritos con `%`. Los montos están en pesos chilenos nominales. `top10_pct=23.55` significa 23,55%; no multiplicarlo otra vez por 100.
5. Ejecutar `supabase/verificar_remuneraciones.sql`. La consulta de reconciliación debe devolver cero diferencias. Comparar conteos con `manifiesto.json`.

Cada CSV inicial está por debajo del límite de 100 MB indicado para la importación del Dashboard. Referencia: [documentación oficial de importación](https://supabase.com/docs/guides/database/import-data).

## 4. Carga automática y futuras actualizaciones

El cargador usa PostgreSQL COPY, tablas temporales y una transacción. El contenido anterior permanece si hay un error. Primero puede validar archivos sin conectar:

```bash
python scripts/remuneraciones/cargar_supabase.py --datos "salida/entrega_2025" --validar
```

Obtener la cadena de conexión Postgres **directa o Session pooler** desde Connect en Supabase. Guardarla en la variable de entorno `SUPABASE_DB_URL` en la terminal local, con `sslmode=require`. No poner contraseñas en el repositorio, Excel ni JavaScript del navegador. Ejecutar:

```bash
python scripts/remuneraciones/cargar_supabase.py --datos "salida/entrega_2025"
```

Si ya existe una entrega, el comando se detiene. Después de revisar la nueva versión, usar:

```bash
python scripts/remuneraciones/cargar_supabase.py --datos "salida/entrega_nueva" --reemplazar
```

**`--reemplazar` sustituye el contenido de las cinco tablas `rem_*` de esta entrega**, no otros datos del proyecto. La sustitución es completa y atómica, no una mezcla entre versiones. Hacer una copia de seguridad antes de una actualización de producción. La carga no se ha ejecutado aquí porque no se ha proporcionado un proyecto ni conexión de Supabase.

## 5. Conectar la página a Supabase

Tarea de integración para el técnico; la página entregada usa aún los JavaScript locales. Configurar URL y clave publicable del proyecto; conservar RLS y no usar `service_role` en navegador.

Consultas que sustituyen los datos actuales:

- Vista general: `rem_distribuciones`, filtrando `organismo_codigo`, `anio`, `area='Todas'`, `vinculo='Todos'`.
- Histograma: `rem_histogramas`, mismos filtros y ordenar por `tramo`.
- Gasto general: `rem_mensual`, organismo/año y ordenar por `mes`; meses ausentes deben seguir como sin dato.
- Casos puntuales: `rem_casos_puntuales`, organismo/año y ordenar por `posicion`.
- Máximos históricos: seleccionar los casos del organismo y ordenar por `monto_total_clp` descendente, limitando a cinco; mostrar el año de cada fila.

Las áreas `Todas` y los vínculos `Todos` son agregados. **No sumarlos junto con sus componentes**: duplicaría los pagos. Para el total nacional sumar solo las filas `Todas/Todos` de cada año. No obtener una mediana nacional promediando medianas comunales: hay que recalcular desde los importes originales.

El detalle por cargo/estamento, sus anomalías y los rangos de honorarios del sitio anterior siguen en `data_remuneraciones.js`. Estas cinco tablas nuevas no sustituyen ese detalle. Para futuros análisis de cualquier persona, profesión o cargo hará falta un conjunto adicional o volver al original.

## 6. Reconstruir también el detalle heredado, si es necesario

Se incluyen los tres procesadores originales y `tabla_regimen.csv` bajo `scripts/remuneraciones/legacy/`, más las cuatro fases `build_remuneraciones_f*.py`. Las rutas ahora son portables. Conservan reglas, umbrales y limitaciones del análisis anterior. No se volvió a ejecutar esta cadena completa en esta entrega; fue conservada y comprobada sintácticamente. El comando opcional es:

```bash
python scripts/remuneraciones/reconstruir_detalle.py \
  --fuente "/ruta/TA_PersonalMunicipal_2008_2025_NUEVO_LIMPIO.csv" \
  --salida "salida/detalle_legacy" --web "/ruta/copia-del-repositorio"
```

Requiere varias pasadas, archivos intermedios grandes y al menos 6 GB de memoria disponibles para DuckDB. Después ejecutar `preparar_entrega.py --web` para sincronizar distribución y casos. Revisar resultados en una copia antes de publicarlos. El resumen por estamento heredado sigue aproximando la mediana mediante medianas ponderadas; no es la mediana directa de todos los pagos.

## 7. Llevar los cambios a GitHub manualmente

Los cambios se prepararon en la rama `codex/remuneraciones-entrega-supabase`; revisar la solicitud de cambios antes de fusionarlos a `main`. Para una aplicación manual alternativa, copiar del ZIP solo los archivos del directorio `sitio/` sobre el repositorio, conservando sus rutas; comprobar `remuneraciones.html` localmente. Los datos reducidos y el Excel se entregan aparte para el técnico. El CSV gigante y credenciales **no** se suben a GitHub.

```bash
git checkout -b mejoras-remuneraciones
git add remuneraciones.html data/data_remuneraciones.js data/data_distribucion_registros.js \
  scripts/distribucion_remuneraciones.js scripts/remuneraciones \
  scripts/build_remuneraciones_f1.py scripts/build_remuneraciones_f2.py \
  scripts/build_remuneraciones_f3.py scripts/build_remuneraciones_f4.py docs supabase .gitignore
git commit -m "Mejorar remuneraciones y añadir entrega reproducible para Supabase"
git push -u origin mejoras-remuneraciones
```

No es necesario publicar los 12 GB ni volver a ejecutar el proceso para mostrar las mejoras ya preparadas. Abrir la web por un servidor HTTP local, no mediante doble clic con `file://`.
