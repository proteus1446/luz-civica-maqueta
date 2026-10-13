import os
from pathlib import Path
# =============================================================
# LUZ CÍVICA — Script 3/3: gasto_y_honorarios.py
# Lee el archivo nacional directo (independiente de los Scripts
# 1 y 2 -- todo a nivel de fila/mes, nunca "resume" a una persona
# a un solo número por año, así que no tiene el bug del max()).
# Exporta:
#   1. gasto_mensual.csv          -- desglosado: base/bono/extras/total
#   2. honorarios_ranking_comunas.csv  -- % dependencia honorarios
#   3. horas_extra_ranking_comunas.csv -- % dependencia horas extra (nuevo)
#   4. honorarios_personas.csv    -- FIX: esporádico vs. sostenido
# =============================================================

import duckdb
import time

# --------------------- CONFIGURACIÓN -------------------------
RUTA_DATOS = os.environ.get("RUTA_DATOS", str(Path(os.environ.get("REM_LEGACY_DIR", ".")) / "TA_PersonalMunicipal_2008_2025_NUEVO_LIMPIO.csv"))

RUTA_SALIDA_GASTO_MENSUAL          = os.environ.get("RUTA_SALIDA_GASTO_MENSUAL", str(Path(os.environ.get("REM_LEGACY_DIR", ".")) / "gasto_mensual.csv"))
RUTA_SALIDA_HONORARIOS_RANKING     = os.environ.get("RUTA_SALIDA_HONORARIOS_RANKING", str(Path(os.environ.get("REM_LEGACY_DIR", ".")) / "honorarios_ranking_comunas.csv"))
RUTA_SALIDA_HORAS_EXTRA_RANKING    = os.environ.get("RUTA_SALIDA_HORAS_EXTRA_RANKING", str(Path(os.environ.get("REM_LEGACY_DIR", ".")) / "horas_extra_ranking_comunas.csv"))
RUTA_SALIDA_HONORARIOS_PERSONAS    = os.environ.get("RUTA_SALIDA_HONORARIOS_PERSONAS", str(Path(os.environ.get("REM_LEGACY_DIR", ".")) / "honorarios_personas.csv"))

MESES_MINIMO_SOSTENIDO = 3    # 1-2 meses = esporádico; 3+ = sostenido
MINIMO_FILAS_RANKING   = 50   # umbral de calidad: comuna-año con menos de esto no entra al ranking

con = duckdb.connect()
con.execute("SET memory_limit='6GB'; SET threads=4;")
con.execute("SET preserve_insertion_order=false;")
con.execute("SET enable_progress_bar=true;")

_inicio = time.time()
def avance(msg):
    print(f"[{time.time()-_inicio:6.1f}s] {msg}")

avance("Paso 1/6: abriendo el archivo nacional (streaming)...")
# --------------------- 1. VISTA BASE (streaming) ----------------
con.execute(f"""
CREATE OR REPLACE VIEW base AS
SELECT
    organismo_codigo,
    organismo_nombre,
    TRY_CAST(anyo AS INT)                                   AS anyo,
    mes,
    tipo_vinculo,
    regexp_replace(strip_accents(upper(trim(tipo_estamento))), '\\s+', ' ', 'g') AS estamento_norm,
    upper(trim(coalesce(nombres,'') || '|' || coalesce(paterno,'') || '|' || coalesce(materno,''))) AS persona_id,
    cargo_funcion,
    TRY_CAST(replace(remuneracion_bruta, ',', '.') AS DOUBLE)   AS bruta,
    coalesce(TRY_CAST(replace(remu_bonoin, ',', '.') AS DOUBLE), 0)         AS bono,
    coalesce(TRY_CAST(replace(pago_extra_diurnas,   ',', '.') AS DOUBLE),0)
  + coalesce(TRY_CAST(replace(pago_extra_nocturnas, ',', '.') AS DOUBLE),0)
  + coalesce(TRY_CAST(replace(pago_extra_festivas,  ',', '.') AS DOUBLE),0)    AS pago_extras
FROM read_csv_auto('{RUTA_DATOS}', delim=';', header=true,
                   all_varchar=true, ignore_errors=true)
WHERE TRY_CAST(replace(remuneracion_bruta, ',', '.') AS DOUBLE) > 0
  AND TRY_CAST(anyo AS INT) BETWEEN 2015 AND 2025;
""")
# remu_adicional NO se incluye: está en $0 en el 100% de las filas
# verificadas (columna sin uso real en este archivo).

avance("Paso 2/6: calculando gasto mensual desglosado (base/bono/extras/total)...")
# --------------------- 2. GASTO MENSUAL DESGLOSADO ----------------
con.execute("""
CREATE OR REPLACE TABLE gasto_mensual AS
SELECT organismo_codigo, max(organismo_nombre) AS organismo_nombre, anyo,
       CASE upper(mes)
         WHEN 'ENERO' THEN 1 WHEN 'FEBRERO' THEN 2 WHEN 'MARZO' THEN 3
         WHEN 'ABRIL' THEN 4 WHEN 'MAYO' THEN 5 WHEN 'JUNIO' THEN 6
         WHEN 'JULIO' THEN 7 WHEN 'AGOSTO' THEN 8 WHEN 'SEPTIEMBRE' THEN 9
         WHEN 'OCTUBRE' THEN 10 WHEN 'NOVIEMBRE' THEN 11 WHEN 'DICIEMBRE' THEN 12
       END AS mes_num,
       mes, tipo_vinculo, estamento_norm AS estamento,
       count(*)                              AS n_personas,
       sum(bruta - pago_extras - bono)       AS gasto_base,
       sum(bono)                             AS gasto_bono,
       sum(pago_extras)                      AS gasto_extras,
       sum(bruta)                            AS gasto_total
FROM base
GROUP BY organismo_codigo, anyo, mes, tipo_vinculo, estamento_norm;
""")

con.execute(f"""
COPY (
  SELECT organismo_codigo, organismo_nombre, anyo, mes_num, mes, tipo_vinculo, estamento,
         n_personas,
         round(gasto_base)   AS gasto_base,
         round(gasto_bono)   AS gasto_bono,
         round(gasto_extras) AS gasto_extras,
         round(gasto_total)  AS gasto_total
  FROM gasto_mensual
  ORDER BY organismo_codigo, anyo, mes_num
) TO '{RUTA_SALIDA_GASTO_MENSUAL}' (DELIMITER ';', HEADER);
""")
avance(f"  ...{RUTA_SALIDA_GASTO_MENSUAL} listo.")

avance("Paso 3/6: filtro de calidad -- comunas que reportaron Alcalde ese año...")
# --------------------- 3. FILTRO DE CALIDAD (comunas completas) ---
con.execute("""
CREATE OR REPLACE TABLE comunas_completas AS
SELECT DISTINCT organismo_codigo, anyo
FROM base
WHERE estamento_norm IN ('ALCALDE','ALCALDESA');
""")

avance("Paso 4/6: ranking nacional de honorarios...")
# --------------------- 4. HONORARIOS: ranking nacional -------------
con.execute("""
CREATE OR REPLACE TABLE honorarios_por_comuna AS
SELECT b.organismo_codigo, max(b.organismo_nombre) AS organismo_nombre, b.anyo,
       count(*) AS n_total,
       count(*) FILTER (WHERE b.tipo_vinculo='Honorarios') AS n_honorarios,
       sum(b.bruta) AS gasto_total,
       sum(b.bruta) FILTER (WHERE b.tipo_vinculo='Honorarios') AS gasto_honorarios
FROM base b
JOIN comunas_completas cc ON b.organismo_codigo = cc.organismo_codigo AND b.anyo = cc.anyo
WHERE (b.estamento_norm NOT IN ('ALCALDE','ALCALDESA','CONCEJAL') OR b.estamento_norm IS NULL)
  -- "estamento_norm IS NULL" necesario: Honorarios/Código del Trabajo no
  -- tienen estamento (NULL NOT IN (...) da NULL, no TRUE -- sin este OR
  -- se excluirían todas las filas de honorarios silenciosamente).
GROUP BY b.organismo_codigo, b.anyo
HAVING count(*) >= {MINIMO_FILAS_RANKING};
""".replace("{MINIMO_FILAS_RANKING}", str(MINIMO_FILAS_RANKING)))

con.execute(f"""
COPY (
  SELECT organismo_codigo, organismo_nombre, anyo, n_total, n_honorarios,
         round(100.0*n_honorarios/n_total, 1) AS honorarios_pct_personal,
         round(100.0*gasto_honorarios/gasto_total, 1) AS honorarios_pct_gasto,
         round(100.0 * percent_rank() OVER (PARTITION BY anyo ORDER BY n_honorarios::DOUBLE/n_total), 0) AS percentil_nacional
  FROM honorarios_por_comuna
  ORDER BY anyo DESC, honorarios_pct_personal DESC
) TO '{RUTA_SALIDA_HONORARIOS_RANKING}' (DELIMITER ';', HEADER);
""")
avance(f"  ...{RUTA_SALIDA_HONORARIOS_RANKING} listo.")

avance("Paso 5/6: ranking nacional de horas extra (mismo patrón que honorarios)...")
# --------------------- 5. HORAS EXTRA: ranking nacional (nuevo) ----
con.execute("""
CREATE OR REPLACE TABLE horas_extra_por_comuna AS
SELECT b.organismo_codigo, max(b.organismo_nombre) AS organismo_nombre, b.anyo,
       count(*) AS n_total,
       count(*) FILTER (WHERE b.pago_extras > 0) AS n_con_extras,
       sum(b.bruta) AS gasto_total,
       sum(b.pago_extras) AS gasto_extras
FROM base b
JOIN comunas_completas cc ON b.organismo_codigo = cc.organismo_codigo AND b.anyo = cc.anyo
GROUP BY b.organismo_codigo, b.anyo
HAVING count(*) >= {MINIMO_FILAS_RANKING};
""".replace("{MINIMO_FILAS_RANKING}", str(MINIMO_FILAS_RANKING)))
# No hace falta excluir Alcalde/Concejal aquí (a diferencia de honorarios):
# horas extra ya es prácticamente inexistente en cargos de autoridad, no
# distorsiona el cálculo de forma relevante.

con.execute(f"""
COPY (
  SELECT organismo_codigo, organismo_nombre, anyo, n_total, n_con_extras,
         round(100.0*n_con_extras/n_total, 1) AS extras_pct_personal,
         round(100.0*gasto_extras/gasto_total, 1) AS extras_pct_gasto,
         round(100.0 * percent_rank() OVER (PARTITION BY anyo ORDER BY gasto_extras/gasto_total), 0) AS percentil_nacional
  FROM horas_extra_por_comuna
  ORDER BY anyo DESC, extras_pct_gasto DESC
) TO '{RUTA_SALIDA_HORAS_EXTRA_RANKING}' (DELIMITER ';', HEADER);
""")
avance(f"  ...{RUTA_SALIDA_HORAS_EXTRA_RANKING} listo.")

avance("Paso 6/6: honorarios por persona -- esporádico vs. sostenido, con fix de multi-trabajo...")
# --------------------- 6. HONORARIOS POR PERSONA (FIX) -------------
# FIX (v3): el archivo trae una fila por CARGO/asignación, no por
# persona-mes -- una misma persona puede tener varios contratos a
# honorarios/código del trabajo simultáneos dentro del MISMO mes (ej.
# un kinesiólogo con un contrato aparte por cada colegio que atiende).
# Sin consolidar esto primero, un mes con 9 pagos chicos se contaba
# como "9 meses" en vez de "1 mes, pago total = suma de los 9".
#
# Paso A: consolidar por persona+mes -> SUMAR los pagos de ese mes,
#         y guardar cuántos trabajos distintos tuvo ese mes.
con.execute("""
CREATE OR REPLACE TABLE honorarios_persona_mes AS
SELECT organismo_codigo, max(organismo_nombre) AS organismo_nombre, anyo, mes, persona_id,
       tipo_vinculo,
       count(*)      AS n_trabajos_mes,
       sum(bruta)    AS pago_mes
FROM base
WHERE tipo_vinculo IN ('Honorarios','Código Trabajo')
GROUP BY organismo_codigo, anyo, mes, persona_id, tipo_vinculo;
""")
# Paso B: de ahí, resumir el año -- meses_informados ahora cuenta MESES
# reales (no filas), y se guarda el máximo de trabajos simultáneos en un
# mismo mes como señal de precariedad (varios contratos chicos a la vez
# con la misma comuna, sin decir la palabra "precariedad" -- se muestra
# el hecho: cuántos trabajos, sumando cuánto).
con.execute(f"""
CREATE OR REPLACE TABLE honorarios_persona_periodo AS
SELECT organismo_codigo, max(organismo_nombre) AS organismo_nombre, anyo, persona_id,
       tipo_vinculo,
       count(*)                              AS meses_informados,
       sum(pago_mes)                         AS monto_total_periodo,
       median(pago_mes)                      AS mediana_mensual,
       max(n_trabajos_mes)                   AS max_trabajos_simultaneos,
       count(*) FILTER (WHERE n_trabajos_mes >= 2) AS meses_con_multitrabajo
FROM honorarios_persona_mes
GROUP BY organismo_codigo, anyo, persona_id, tipo_vinculo;
""")
# cargo_funcion ya no se incluye como columna única -- una persona con
# multi-trabajo no tiene UN cargo representativo (tenía varios a la vez),
# así que mostrar solo uno sería engañoso. Se deja fuera de este archivo.

con.execute(f"""
COPY (
  SELECT organismo_codigo, organismo_nombre, anyo, persona_id, tipo_vinculo,
         meses_informados,
         CASE WHEN meses_informados >= {MESES_MINIMO_SOSTENIDO} THEN 'sostenido' ELSE 'esporadico' END AS tipo_periodo,
         CASE WHEN meses_informados < {MESES_MINIMO_SOSTENIDO} THEN round(monto_total_periodo) END AS monto_total_periodo,
         CASE WHEN meses_informados >= {MESES_MINIMO_SOSTENIDO} THEN round(mediana_mensual) END AS mediana_mensual,
         max_trabajos_simultaneos,
         meses_con_multitrabajo
  FROM honorarios_persona_periodo
  ORDER BY organismo_codigo, anyo, tipo_periodo,
           coalesce(mediana_mensual, monto_total_periodo) DESC
) TO '{RUTA_SALIDA_HONORARIOS_PERSONAS}' (DELIMITER ';', HEADER);
""")
avance(f"  ...{RUTA_SALIDA_HONORARIOS_PERSONAS} listo.")

avance("¡Listo!")
print(f"""
  {RUTA_SALIDA_GASTO_MENSUAL}
  {RUTA_SALIDA_HONORARIOS_RANKING}
  {RUTA_SALIDA_HORAS_EXTRA_RANKING}
  {RUTA_SALIDA_HONORARIOS_PERSONAS}""")
