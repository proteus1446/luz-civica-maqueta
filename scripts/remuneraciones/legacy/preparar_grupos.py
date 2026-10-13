import os
from pathlib import Path
# =============================================================
# LUZ CÍVICA — Script 1/3: preparar_grupos.py
# Lee el archivo nacional (~10GB), arma grupos de comparación
# LIMPIOS y exporta:
#   1. grupos_estadisticas.csv  -- mediana + MAD por grupo
#   2. persona_grupo.csv        -- tabla intermedia (insumo del
#                                   Script 2, mucho más liviana
#                                   que el archivo nacional)
# -------------------------------------------------------------
# FIX vs. v2 (deteccion_anomalias_v2.py):
#   Antes, `persona_anual` agrupaba SOLO por persona+año y usaba
#   max(grado_municipal)/max(estamento_norm)/max(tipo_vinculo)
#   para "resumir" el año a un solo valor -- pero la mediana de
#   sueldo se calculaba sobre los 12 meses SIN filtrar por ese
#   valor. Resultado: alguien que cambia de grado/estamento/
#   vínculo a mitad de año quedaba con un sueldo "mezclado" y
#   mal clasificado (ver resumen_sesion_deteccion_grado.md).
#
#   Ahora, `persona_periodo` agrupa por persona + AÑO + VÍNCULO +
#   ESTAMENTO + GRADO/CATEGORÍA/HORAS. Si la persona cambió de
#   grado a mitad de año, esto genera automáticamente DOS filas
#   (una por grado), cada una con la mediana de SOLO esos meses.
#   No hace falta detectar fechas de cambio a mano -- el GROUP BY
#   separa los períodos solo.
# =============================================================

import duckdb
import time

# --------------------- CONFIGURACIÓN -------------------------
RUTA_DATOS   = os.environ.get("RUTA_DATOS", str(Path(os.environ.get("REM_LEGACY_DIR", ".")) / "TA_PersonalMunicipal_2008_2025_NUEVO_LIMPIO.csv"))
RUTA_REGIMEN = os.environ.get("RUTA_REGIMEN", str(Path(os.environ.get("REM_LEGACY_DIR", ".")) / "tabla_regimen.csv"))

RUTA_SALIDA_GRUPOS        = os.environ.get("RUTA_SALIDA_GRUPOS", str(Path(os.environ.get("REM_LEGACY_DIR", ".")) / "grupos_estadisticas.csv"))
RUTA_SALIDA_PERSONA_GRUPO = os.environ.get("RUTA_SALIDA_PERSONA_GRUPO", str(Path(os.environ.get("REM_LEGACY_DIR", ".")) / "persona_grupo.csv"))
RUTA_SALIDA_RESUMEN_ESTAMENTO = os.environ.get("RUTA_SALIDA_RESUMEN_ESTAMENTO", str(Path(os.environ.get("REM_LEGACY_DIR", ".")) / "resumen_estadisticas.csv"))

N_MINIMO_GRUPO = 8
MAD_PISO_PCT      = 0.03
MAD_PISO_ABSOLUTO = 5000
MESES_MINIMO_PERIODO = 3   # igual que antes: no calcular mediana con <3 meses

con = duckdb.connect()
con.execute("SET memory_limit='6GB'; SET threads=4;")
con.execute("SET preserve_insertion_order=false;")
con.execute("SET enable_progress_bar=true;")

_inicio = time.time()
def avance(msg):
    print(f"[{time.time()-_inicio:6.1f}s] {msg}")

avance("Paso 1/7: cargando tabla_regimen...")
# --------------------- 1. TABLAS DE APOYO ----------------------
con.execute(f"""
CREATE OR REPLACE TABLE regimen AS
SELECT * FROM read_csv_auto('{RUTA_REGIMEN}', delim=';', header=true);
""")

avance("Paso 2/7: abriendo el archivo grande (streaming)...")
# --------------------- 2. VISTA BASE (streaming) ----------------
con.execute(f"""
CREATE OR REPLACE VIEW base AS
SELECT
    organismo_codigo,
    organismo_nombre,
    TRY_CAST(anyo AS INT)                                   AS anyo,
    mes,
    tipo_vinculo,
    regexp_replace(strip_accents(upper(trim(tipo_estamento))), '\\s+', ' ', 'g') AS estamento_norm,
    trim(grado_eus)                                         AS grado_raw,
    upper(trim(coalesce(nombres,'') || '|' || coalesce(paterno,'') || '|' || coalesce(materno,''))) AS persona_id,
    cargo_funcion,
    TRY_CAST(replace(remuneracion_bruta, ',', '.') AS DOUBLE)   AS bruta,
    coalesce(TRY_CAST(replace(pago_extra_diurnas,   ',', '.') AS DOUBLE),0)
  + coalesce(TRY_CAST(replace(pago_extra_nocturnas, ',', '.') AS DOUBLE),0)
  + coalesce(TRY_CAST(replace(pago_extra_festivas,  ',', '.') AS DOUBLE),0)    AS pago_extras,
    CASE
      WHEN upper(camino) LIKE '%SALUD%'      THEN 'Salud'
      WHEN upper(camino) LIKE '%EDUC%'       THEN 'Educacion'
      WHEN upper(camino) LIKE '%CEMENTERI%'  THEN 'Cementerio'
      WHEN upper(camino) LIKE '%MUNICIPAL%'  THEN 'Municipal'
      ELSE 'Sin Clasificar'
    END AS origen
    -- 'origen' viene de la carpeta de archivo ('camino') del portal de origen.
    -- SOLO se usa como respaldo para decidir la PESTAÑA de despliegue en el
    -- HTML de casos sin estamento claro (Chofer, Sin Estamento, etc.) --
    -- NUNCA se usa para agrupar comparaciones de sueldo (eso sigue siendo
    -- 100% tipo_estamento). Ver 'pestana' más abajo.
FROM read_csv_auto('{RUTA_DATOS}', delim=';', header=true,
                   all_varchar=true, ignore_errors=true)
WHERE TRY_CAST(replace(remuneracion_bruta, ',', '.') AS DOUBLE) > 0;
""")

avance("Paso 3/7: separando Categoría (Salud) y horas de jornada (Educación)...")
# --------------------- 3. PARSEO DE grado_eus SEGÚN RÉGIMEN -----
con.execute("""
CREATE OR REPLACE VIEW base_parseada AS
SELECT b.*,
    CASE WHEN regexp_matches(grado_raw, '^[A-Za-z]\\d+$')
         THEN upper(substr(grado_raw,1,1)) END AS categoria_salud,
    CASE WHEN regexp_matches(grado_raw, '^\\d+$')
         THEN TRY_CAST(grado_raw AS INT) END AS grado_municipal,
    CASE
      WHEN regexp_matches(upper(regexp_replace(grado_raw,'\\s+',' ','g')), 'NO\\s*ASIMIL|NO\\s*APLICA')
        THEN -1
      WHEN regexp_matches(upper(regexp_replace(grado_raw,'\\s+',' ','g')), '(?:JORNADA\\s*(?:DE\\s*)?)?\\d{1,2}\\s*(?:HRS?\\.?|HORAS?)\\b')
        THEN TRY_CAST(regexp_extract(upper(regexp_replace(grado_raw,'\\s+',' ','g')),
             '(?:JORNADA\\s*(?:DE\\s*)?)?(\\d{1,2})\\s*(?:HRS?\\.?|HORAS?)\\b', 1) AS INT)
    END AS horas_jornada_edu
FROM base b;
""")

avance("Paso 4/7: mediana por PERÍODO (persona+vínculo+estamento+grado+año) — este es el fix...")
# --------------------- 4. BASE POR PERÍODO (FIX) -----------------
# ANTES: GROUP BY organismo_codigo, persona_id, anyo  (+ max() de vínculo/
#        estamento/grado -> mezclaba meses de distinto grado/vínculo).
# AHORA: el vínculo, estamento y grado/categoría/horas entran directo
#        al GROUP BY. Si la persona cambió de grado a mitad de año, esto
#        genera dos filas (una por grado), cada una con SOLO los meses
#        correspondientes -- sin mezcla.
#
# FIX 2: dentro de un mismo mes, una persona puede tener 2+ filas con
# LA MISMA clasificación exacta (mismo vínculo+estamento+grado) -- ej.
# un pago base + un ajuste retroactivo del mismo cargo, registrados como
# líneas separadas. Sin consolidar esto, cada línea se contaba como "un
# mes" cuando en realidad es "un mes, con el pago repartido en 2 líneas".
# Por eso primero se consolida a nivel PERSONA+MES+clasificación (sumando
# bruta y pago_extras), y recién de ahí se saca la mediana anual.
con.execute(f"""
CREATE OR REPLACE TABLE persona_mes_grupo AS
SELECT
    organismo_codigo,
    max(organismo_nombre) AS organismo_nombre,
    anyo, mes, persona_id,
    tipo_vinculo, estamento_norm, grado_municipal, categoria_salud, horas_jornada_edu,
    max(cargo_funcion)  AS cargo_funcion,
    sum(bruta)           AS bruta_mes,
    sum(pago_extras)     AS pago_extras_mes,
    mode(origen)          AS origen_mes
FROM base_parseada
WHERE anyo BETWEEN 2015 AND 2025
GROUP BY organismo_codigo, anyo, mes, persona_id, tipo_vinculo, estamento_norm,
         grado_municipal, categoria_salud, horas_jornada_edu;
""")

con.execute(f"""
CREATE OR REPLACE TABLE persona_periodo AS
SELECT
    organismo_codigo,
    max(organismo_nombre)  AS organismo_nombre,
    anyo,
    persona_id,
    tipo_vinculo,
    estamento_norm,
    grado_municipal,
    categoria_salud,
    horas_jornada_edu,
    max(cargo_funcion)               AS cargo_funcion,
    count(*)                         AS meses_informados,
    median(bruta_mes - pago_extras_mes)  AS base_sin_extras,
    median(pago_extras_mes)              AS extras_mediana,
    mode(origen_mes)                     AS origen_moda
    -- origen_moda: el 'origen' (carpeta de archivo) más frecuente entre los
    -- meses de este período -- NO un mes suelto, para no repetir el error
    -- tipo "Javiera en septiembre" (un mes mal archivado no debe cambiar
    -- la pestaña de despliegue de toda la persona).
FROM persona_mes_grupo
GROUP BY organismo_codigo, anyo, persona_id, tipo_vinculo, estamento_norm,
         grado_municipal, categoria_salud, horas_jornada_edu
HAVING count(*) >= {MESES_MINIMO_PERIODO};
""")

avance("Paso 5/7: asignando cada período a su grupo de comparación...")
# --------------------- 5. ASIGNAR GRUPO SEGÚN RÉGIMEN ------------
con.execute("""
CREATE OR REPLACE TABLE con_grupo AS
SELECT
    p.*,
    coalesce(r.regimen, 'RESPALDO')  AS regimen,
    coalesce(r.excluir_deteccion, 0) AS excluir,
    CASE
      WHEN coalesce(r.regimen, 'RESPALDO') IN ('MUNICIPAL','AUTORIDAD') THEN 'Municipal'
      WHEN coalesce(r.regimen, 'RESPALDO') = 'SALUD' THEN 'Salud'
      WHEN coalesce(r.regimen, 'RESPALDO') = 'EDUCACION' THEN 'Educación'
      -- RESPALDO / AMBIGUO (sin grado que los resuelva como Municipal más
      -- abajo): la comparación de sueldo NO cambia (sigue por tipo_estamento),
      -- pero acá sí usamos 'origen' (la carpeta de archivo más frecuente del
      -- período) para decidir en qué pestaña del HTML se muestra la tarjeta.
      WHEN p.origen_moda = 'Salud'      THEN 'Salud'
      WHEN p.origen_moda = 'Educacion'  THEN 'Educación'
      ELSE 'Municipal'
      -- Cementerio y 'Sin Clasificar' caen en Municipal por defecto (no hay
      -- pestaña propia para Cementerio en el diseño actual de 3 pestañas).
    END AS pestana,
    CASE
      WHEN r.regimen = 'MUNICIPAL' AND p.grado_municipal IS NOT NULL
        THEN p.organismo_codigo||'|'||p.estamento_norm||'|G'||p.grado_municipal||'|'||p.tipo_vinculo||'|'||p.anyo
      WHEN r.regimen = 'SALUD' AND p.categoria_salud IS NOT NULL
        THEN p.organismo_codigo||'|'||p.estamento_norm||'|CAT'||p.categoria_salud||'|'||p.tipo_vinculo||'|'||p.anyo
      WHEN r.regimen = 'EDUCACION' AND p.horas_jornada_edu IS NOT NULL AND p.horas_jornada_edu > 0
        THEN p.organismo_codigo||'|'||p.estamento_norm||'|H'||p.horas_jornada_edu||'|'||p.tipo_vinculo||'|'||p.anyo
      WHEN r.regimen = 'EDUCACION' AND p.horas_jornada_edu = -1
        THEN p.organismo_codigo||'|'||p.estamento_norm||'|NO_ASIMILADO|'||p.tipo_vinculo||'|'||p.anyo
      WHEN r.regimen = 'AMBIGUO' AND p.grado_municipal IS NOT NULL
        THEN p.organismo_codigo||'|'||p.estamento_norm||'|G'||p.grado_municipal||'|'||p.tipo_vinculo||'|'||p.anyo
      -- AMBIGUO (Directora, Fiscalizador): si trae grado numérico, se trata
      -- como Municipal. Sin grado, cae al fallback genérico por cargo (ELSE),
      -- mismo tratamiento que RESPALDO.
      WHEN r.llave_agrupacion = 'cargo_nacional_percentil'
        THEN 'NACIONAL|'||p.estamento_norm||'|'||p.tipo_vinculo||'|'||p.anyo
      WHEN r.llave_agrupacion IN ('comuna+estamento+grado','comuna+estamento')
        THEN p.organismo_codigo||'|'||p.estamento_norm||'|'||p.tipo_vinculo||'|'||p.anyo
      ELSE p.organismo_codigo||'|CARGO:'||
           regexp_replace(strip_accents(upper(trim(coalesce(p.cargo_funcion,'SIN CARGO')))), '\\s+', ' ', 'g')
           ||'|'||p.tipo_vinculo||'|'||p.anyo
    END AS grupo
FROM persona_periodo p
LEFT JOIN regimen r ON p.estamento_norm = r.estamento_norm
WHERE coalesce(r.excluir_deteccion, 0) = 0;
""")

avance("Paso 6/7: calculando mediana + MAD por grupo...")
# --------------------- 6. MEDIANA + MAD POR GRUPO -----------------
con.execute("""
CREATE OR REPLACE TABLE stats_grupo AS
WITH med AS (
    SELECT grupo,
           max(organismo_codigo)  AS organismo_codigo,
           max(organismo_nombre)  AS organismo_nombre,
           max(anyo)              AS anyo,
           max(estamento_norm)    AS estamento_norm,
           max(tipo_vinculo)      AS tipo_vinculo,
           max(regimen)           AS regimen,
           max(grado_municipal)   AS grado_municipal,
           max(categoria_salud)   AS categoria_salud,
           max(horas_jornada_edu) AS horas_jornada_edu,
           count(*) AS n, median(base_sin_extras) AS mediana_grupo
    FROM con_grupo GROUP BY grupo
)
SELECT m.grupo, m.organismo_codigo, m.organismo_nombre, m.anyo, m.estamento_norm,
       m.tipo_vinculo, m.regimen, m.grado_municipal, m.categoria_salud, m.horas_jornada_edu,
       m.n, m.mediana_grupo,
       median(abs(c.base_sin_extras - m.mediana_grupo)) AS mad_grupo
FROM con_grupo c JOIN med m USING (grupo)
GROUP BY m.grupo, m.organismo_codigo, m.organismo_nombre, m.anyo, m.estamento_norm,
         m.tipo_vinculo, m.regimen, m.grado_municipal, m.categoria_salud, m.horas_jornada_edu,
         m.n, m.mediana_grupo;
""")
# NOTA: dentro de un mismo "grupo" (comuna+estamento+grado+vínculo+año) el
# max() de organismo_codigo/estamento_norm/tipo_vinculo/grado_municipal/etc.
# es seguro -- por DEFINICIÓN todas las filas de un mismo grupo comparten
# esos valores (son parte de la llave). No es el mismo max() problemático
# de la v2 (que mezclaba filas de grupos DISTINTOS bajo una sola persona-año).

avance("Paso 7/7: exportando grupos_estadisticas.csv y persona_grupo.csv...")
# --------------------- 7. EXPORTAR -------------------------------
con.execute(f"""
COPY (
  SELECT organismo_codigo, organismo_nombre, anyo, estamento_norm, tipo_vinculo, regimen,
         grado_municipal, categoria_salud, horas_jornada_edu,
         n, round(mediana_grupo) AS mediana_grupo, round(mad_grupo) AS mad_grupo,
         grupo
  FROM stats_grupo WHERE n >= {N_MINIMO_GRUPO} ORDER BY organismo_codigo, anyo, n DESC
) TO '{RUTA_SALIDA_GRUPOS}' (DELIMITER ';', HEADER);
""")

con.execute(f"""
COPY (
  SELECT organismo_codigo, organismo_nombre, anyo, persona_id, regimen, pestana, estamento_norm,
         grado_municipal, categoria_salud, horas_jornada_edu,
         cargo_funcion, tipo_vinculo, meses_informados,
         round(base_sin_extras)  AS base_sin_extras,
         round(extras_mediana)   AS extras_mediana,
         grupo
  FROM con_grupo
  ORDER BY organismo_codigo, anyo, persona_id
) TO '{RUTA_SALIDA_PERSONA_GRUPO}' (DELIMITER ';', HEADER);
""")

avance("Extra: resumen_estadisticas.csv -- mediana REAL por estamento (sin desglosar grado)...")
# --------------------- 7b. RESUMEN POR ESTAMENTO (mediana real) ---
# A diferencia de grupos_estadisticas.csv (que desglosa por grado/categoría/
# horas), esta tabla junta TODOS los grados de un estamento en un solo
# número -- útil para la vista "resumen" del HTML. La mediana acá es
# recalculada de verdad sobre las personas (con_grupo), NO un promedio
# ponderado de las medianas de cada grado (que sería matemáticamente
# incorrecto -- las medianas no se promedian entre sí).
con.execute(f"""
CREATE OR REPLACE TABLE resumen_estamento AS
SELECT organismo_codigo, max(organismo_nombre) AS organismo_nombre, anyo, regimen, pestana,
       estamento_norm, tipo_vinculo,
       count(*) AS n, median(base_sin_extras) AS mediana
FROM con_grupo
GROUP BY organismo_codigo, anyo, regimen, pestana, estamento_norm, tipo_vinculo;
""")
con.execute(f"""
COPY (
  SELECT organismo_codigo, organismo_nombre, anyo, regimen, pestana, estamento_norm, tipo_vinculo,
         n, round(mediana) AS mediana
  FROM resumen_estamento WHERE n >= {N_MINIMO_GRUPO}
  ORDER BY organismo_codigo, anyo, n DESC
) TO '{RUTA_SALIDA_RESUMEN_ESTAMENTO}' (DELIMITER ';', HEADER);
""")
# persona_grupo.csv es el insumo del Script 2 (detectar_outliers.py).
# Trae 'grupo' como llave para hacer JOIN directo contra
# grupos_estadisticas.csv y calcular el z-score robusto ahí, sin
# tener que releer el archivo nacional de 10GB.

avance("¡Listo!")
print(con.sql("SELECT regimen, count(*) AS periodos FROM con_grupo GROUP BY 1 ORDER BY 2 DESC"))
print(f"""
  {RUTA_SALIDA_GRUPOS}
  {RUTA_SALIDA_PERSONA_GRUPO}""")
