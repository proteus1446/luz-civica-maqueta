import os
from pathlib import Path
# =============================================================
# LUZ CÍVICA — Script 2/3: detectar_outliers.py
# Lee los archivos livianos del Script 1 para la parte ANUAL
# (rápido, sin tocar el archivo nacional de 10GB) y el archivo
# nacional directo para la parte MENSUAL (necesita el detalle
# de cada mes, que no vive en el intermedio anual).
# -------------------------------------------------------------
# FIX vs. v2:
#   `flag_extras_altas` (horas extra > 30% del sueldo base) ya
#   NO depende de que el grupo tenga 8+ personas (N_MINIMO_GRUPO).
#   Antes quedaba atado sin querer al mismo filtro que el z-score,
#   aunque no necesita comparación contra nadie -- es un chequeo
#   de la propia persona. Ahora se evalúa siempre, para cualquier
#   tamaño de grupo. El z-score sigue exigiendo grupo de 8+.
# =============================================================

import duckdb
import os
import time

# --------------------- CONFIGURACIÓN -------------------------
RUTA_DATOS   = os.environ.get("RUTA_DATOS", str(Path(os.environ.get("REM_LEGACY_DIR", ".")) / "TA_PersonalMunicipal_2008_2025_NUEVO_LIMPIO.csv"))
RUTA_REGIMEN = os.environ.get("RUTA_REGIMEN", str(Path(os.environ.get("REM_LEGACY_DIR", ".")) / "tabla_regimen.csv"))

RUTA_PERSONA_GRUPO      = os.environ.get("RUTA_PERSONA_GRUPO", str(Path(os.environ.get("REM_LEGACY_DIR", ".")) / "persona_grupo.csv"))       # del Script 1
RUTA_GRUPOS_ESTADISTICAS = os.environ.get("RUTA_GRUPOS_ESTADISTICAS", str(Path(os.environ.get("REM_LEGACY_DIR", ".")) / "grupos_estadisticas.csv")) # del Script 1

RUTA_SALIDA_OUTLIERS          = os.environ.get("RUTA_SALIDA_OUTLIERS", str(Path(os.environ.get("REM_LEGACY_DIR", ".")) / "outliers_detectados.csv"))
RUTA_SALIDA_OUTLIERS_MENSUAL  = os.environ.get("RUTA_SALIDA_OUTLIERS_MENSUAL", str(Path(os.environ.get("REM_LEGACY_DIR", ".")) / "outliers_detectados_mensual.csv"))

N_MINIMO_GRUPO = 8
Z_UMBRAL       = 3.5
Z_UMBRAL_SALUD = 4.5
MAD_PISO_PCT      = 0.03
MAD_PISO_ABSOLUTO = 5000
TECHO_PLAUSIBILIDAD = 50_000_000   # descarta solo lo físicamente imposible
UMBRAL_EXTRAS_ALTAS  = 0.30        # horas extra > 30% del sueldo base -> flag

con = duckdb.connect()
con.execute("SET memory_limit='6GB'; SET threads=4;")
con.execute("SET preserve_insertion_order=false;")
con.execute("SET enable_progress_bar=true;")

_inicio = time.time()
def avance(msg):
    print(f"[{time.time()-_inicio:6.1f}s] {msg}")

# =============================================================
# PARTE 1 — CASOS ATÍPICOS ANUALES (rápido, desde el intermedio)
# =============================================================
avance("Parte 1/2: casos atípicos ANUALES (desde persona_grupo.csv, sin tocar el archivo nacional)...")

con.execute(f"""
CREATE OR REPLACE TABLE persona_grupo AS
SELECT * FROM read_csv_auto('{RUTA_PERSONA_GRUPO}', delim=';', header=true);
""")
con.execute(f"""
CREATE OR REPLACE TABLE grupos_estadisticas AS
SELECT * FROM read_csv_auto('{RUTA_GRUPOS_ESTADISTICAS}', delim=';', header=true);
""")

con.execute(f"""
CREATE OR REPLACE TABLE resultado AS
SELECT
    p.*,
    g.n              AS n_grupo,
    g.mediana_grupo,
    g.mad_grupo,
    -- z-score: solo se calcula si el grupo tiene tamaño mínimo confiable.
    -- Si el grupo es chico (o no calzó con ningún grupo publicado), z_robusto
    -- queda NULL -- esa persona simplemente no entra por z-score (pero SÍ
    -- puede entrar igual por flag_extras_altas, ver más abajo).
    CASE WHEN g.n >= {N_MINIMO_GRUPO} AND g.mediana_grupo > 0
         THEN (p.base_sin_extras - g.mediana_grupo)
              / (1.4826 * GREATEST(g.mad_grupo, {MAD_PISO_PCT} * g.mediana_grupo, {MAD_PISO_ABSOLUTO}))
         ELSE NULL END AS z_robusto,
    -- flag_extras_altas: chequeo de la PROPIA persona, no necesita grupo de
    -- comparación -- por eso NO depende de g.n >= N_MINIMO_GRUPO.
    CASE WHEN p.base_sin_extras > 0 AND p.extras_mediana > {UMBRAL_EXTRAS_ALTAS} * p.base_sin_extras
         THEN 1 ELSE 0 END AS flag_extras_altas
FROM persona_grupo p
LEFT JOIN grupos_estadisticas g USING (grupo)
WHERE p.regimen != 'RESPALDO';
-- RESPALDO (Honorarios/Código Trabajo) no se detecta por z-score aquí:
-- ya tiene su propio tratamiento (esporádico/sostenido) en el Script 3.
""")

con.execute(f"""
COPY (
  SELECT organismo_codigo, organismo_nombre, anyo, persona_id, regimen, pestana, estamento_norm,
         grado_municipal, categoria_salud, horas_jornada_edu,
         cargo_funcion, tipo_vinculo, meses_informados,
         base_sin_extras, extras_mediana,
         n_grupo, mediana_grupo,
         round(z_robusto, 2)  AS z_robusto,
         flag_extras_altas
  FROM resultado
  WHERE base_sin_extras <= {TECHO_PLAUSIBILIDAD}
    AND (
          (z_robusto >= CASE WHEN regimen = 'SALUD' THEN {Z_UMBRAL_SALUD} ELSE {Z_UMBRAL} END)
          OR flag_extras_altas = 1
        )
  ORDER BY z_robusto DESC NULLS LAST
) TO '{RUTA_SALIDA_OUTLIERS}' (DELIMITER ';', HEADER);
""")
avance(f"  ...{RUTA_SALIDA_OUTLIERS} listo.")

# =============================================================
# PARTE 2 — CASOS ATÍPICOS MENSUALES (necesita el archivo nacional)
# =============================================================
avance("Parte 2/2: casos atípicos MENSUALES (releyendo el archivo nacional, año por año)...")

con.execute(f"""
CREATE OR REPLACE TABLE regimen AS
SELECT * FROM read_csv_auto('{RUTA_REGIMEN}', delim=';', header=true);
""")

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
FROM read_csv_auto('{RUTA_DATOS}', delim=';', header=true,
                   all_varchar=true, ignore_errors=true)
WHERE TRY_CAST(replace(remuneracion_bruta, ',', '.') AS DOUBLE) > 0;
""")

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

_archivos_temporales_mes = []
for _anyo_lote in range(2015, 2026):
    con.execute(f"""
    CREATE OR REPLACE TABLE persona_mes AS
    SELECT organismo_codigo, max(organismo_nombre) AS organismo_nombre, anyo, mes, persona_id,
           tipo_vinculo, estamento_norm, grado_municipal, categoria_salud, horas_jornada_edu,
           max(cargo_funcion)     AS cargo_funcion,
           sum(bruta - pago_extras) AS base_sin_extras,
           mode(origen)            AS origen_mes
    FROM base_parseada
    WHERE anyo = {_anyo_lote}
    GROUP BY organismo_codigo, anyo, mes, persona_id, tipo_vinculo, estamento_norm,
             grado_municipal, categoria_salud, horas_jornada_edu;
    """)
    # FIX: antes se agrupaba solo por persona+mes, usando max() para
    # "resumir" vínculo/estamento/grado -- eso mezclaba trabajos distintos
    # dentro del mismo mes (ej. una docente con 3 jornadas distintas en 3
    # colegios el mismo mes quedaba con un solo valor, el más alto). Ahora
    # el vínculo/estamento/grado entran al GROUP BY (igual que en
    # persona_periodo del Script 1) -- cada trabajo distinto queda en su
    # propia fila. Y se usa sum() en vez de avg(): si dos filas de un mismo
    # mes SÍ comparten la misma clasificación exacta (ej. pago base + ajuste
    # retroactivo del mismo cargo), se suman en vez de promediarse -- avg()
    # le asignaba a la persona la MITAD de lo que realmente ganó ese mes.

    con.execute("""
    CREATE OR REPLACE TABLE con_grupo_mes AS
    SELECT
        p.*,
        coalesce(r.regimen, 'RESPALDO')  AS regimen,
        CASE
          WHEN coalesce(r.regimen, 'RESPALDO') IN ('MUNICIPAL','AUTORIDAD') THEN 'Municipal'
          WHEN coalesce(r.regimen, 'RESPALDO') = 'SALUD' THEN 'Salud'
          WHEN coalesce(r.regimen, 'RESPALDO') = 'EDUCACION' THEN 'Educación'
          WHEN p.origen_mes = 'Salud'      THEN 'Salud'
          WHEN p.origen_mes = 'Educacion'  THEN 'Educación'
          ELSE 'Municipal'
        END AS pestana,
        CASE
          WHEN r.regimen = 'MUNICIPAL' AND p.grado_municipal IS NOT NULL
            THEN p.organismo_codigo||'|'||p.estamento_norm||'|G'||p.grado_municipal||'|'||p.tipo_vinculo||'|'||p.mes||'|'||p.anyo
          WHEN r.regimen = 'SALUD' AND p.categoria_salud IS NOT NULL
            THEN p.organismo_codigo||'|'||p.estamento_norm||'|CAT'||p.categoria_salud||'|'||p.tipo_vinculo||'|'||p.mes||'|'||p.anyo
          WHEN r.regimen = 'EDUCACION' AND p.horas_jornada_edu IS NOT NULL AND p.horas_jornada_edu > 0
            THEN p.organismo_codigo||'|'||p.estamento_norm||'|H'||p.horas_jornada_edu||'|'||p.tipo_vinculo||'|'||p.mes||'|'||p.anyo
          WHEN r.regimen = 'EDUCACION' AND p.horas_jornada_edu = -1
            THEN p.organismo_codigo||'|'||p.estamento_norm||'|NO_ASIMILADO|'||p.tipo_vinculo||'|'||p.mes||'|'||p.anyo
          WHEN r.regimen = 'AMBIGUO' AND p.grado_municipal IS NOT NULL
            THEN p.organismo_codigo||'|'||p.estamento_norm||'|G'||p.grado_municipal||'|'||p.tipo_vinculo||'|'||p.mes||'|'||p.anyo
          WHEN r.llave_agrupacion = 'cargo_nacional_percentil'
            THEN 'NACIONAL|'||p.estamento_norm||'|'||p.tipo_vinculo||'|'||p.mes||'|'||p.anyo
          WHEN r.llave_agrupacion IN ('comuna+estamento+grado','comuna+estamento')
            THEN p.organismo_codigo||'|'||p.estamento_norm||'|'||p.tipo_vinculo||'|'||p.mes||'|'||p.anyo
          ELSE p.organismo_codigo||'|CARGO:'||
               regexp_replace(strip_accents(upper(trim(coalesce(p.cargo_funcion,'SIN CARGO')))), '\\s+', ' ', 'g')
               ||'|'||p.tipo_vinculo||'|'||p.mes||'|'||p.anyo
        END AS grupo
    FROM persona_mes p
    LEFT JOIN regimen r ON p.estamento_norm = r.estamento_norm
    WHERE coalesce(r.excluir_deteccion, 0) = 0;
    """)

    con.execute("""
    CREATE OR REPLACE TABLE stats_grupo_mes AS
    WITH med AS (
        SELECT grupo, count(*) AS n, median(base_sin_extras) AS mediana_grupo
        FROM con_grupo_mes GROUP BY grupo
    )
    SELECT m.grupo, m.n, m.mediana_grupo,
           median(abs(c.base_sin_extras - m.mediana_grupo)) AS mad_grupo
    FROM con_grupo_mes c JOIN med m USING (grupo)
    GROUP BY m.grupo, m.n, m.mediana_grupo;
    """)

    _ruta_temp = f"{RUTA_SALIDA_OUTLIERS_MENSUAL}.{_anyo_lote}.tmp.csv"
    con.execute(f"""
    COPY (
      SELECT c.organismo_codigo, c.organismo_nombre, c.anyo, c.mes, c.persona_id, c.regimen, c.pestana,
             c.estamento_norm, c.grado_municipal, c.categoria_salud,
             c.horas_jornada_edu, c.cargo_funcion, c.tipo_vinculo,
             round(c.base_sin_extras) AS base_sin_extras,
             s.n AS n_grupo, round(s.mediana_grupo) AS mediana_grupo,
             round((c.base_sin_extras - s.mediana_grupo)
                   / (1.4826 * GREATEST(s.mad_grupo, {MAD_PISO_PCT} * s.mediana_grupo, {MAD_PISO_ABSOLUTO})), 2) AS z_robusto_mes
      FROM con_grupo_mes c
      JOIN stats_grupo_mes s ON c.grupo = s.grupo
      WHERE c.regimen != 'RESPALDO'
        AND s.n >= {N_MINIMO_GRUPO}
        AND c.base_sin_extras <= {TECHO_PLAUSIBILIDAD}
        AND (c.base_sin_extras - s.mediana_grupo)
            / (1.4826 * GREATEST(s.mad_grupo, {MAD_PISO_PCT} * s.mediana_grupo, {MAD_PISO_ABSOLUTO}))
            >= CASE WHEN c.regimen = 'SALUD' THEN {Z_UMBRAL_SALUD} ELSE {Z_UMBRAL} END
      ORDER BY z_robusto_mes DESC
    ) TO '{_ruta_temp}' (DELIMITER ';', HEADER);
    """)
    _archivos_temporales_mes.append(_ruta_temp)
    avance(f"  ...año {_anyo_lote} listo ({len(_archivos_temporales_mes)}/11)")

with open(RUTA_SALIDA_OUTLIERS_MENSUAL, 'w', encoding='utf-8') as _out:
    for i, _ruta_temp in enumerate(_archivos_temporales_mes):
        with open(_ruta_temp, 'r', encoding='utf-8') as _in:
            lineas = _in.readlines()
            _out.writelines(lineas if i == 0 else lineas[1:])
        os.remove(_ruta_temp)

avance("¡Listo!")
print(f"""
  {RUTA_SALIDA_OUTLIERS}
  {RUTA_SALIDA_OUTLIERS_MENSUAL}""")
