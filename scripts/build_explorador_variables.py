#!/usr/bin/env python3
"""
Amplía el catálogo de variables del Explorador Comunal (explorador-comunal.html)
usando los datos ya construidos y validados para los 6 paneles de detalle
(data_administracion.js, data_dotacion.js, data_educacion.js, data_salud.js,
data_perfil.js, data_social.js).

Para cada variable nueva solo hace falta:
  - series[comuna][año] = valor          (lo que el explorador usa para TODO:
                                            gráfico, ranking, mediana, MAD, z-score
                                            — todo se calcula en el navegador)
  - ranking[año] = {mediana_nacional, total_comunas}   (valor de conveniencia,
    usado en un par de lugares puntuales; se recalcula acá con la mediana real)

No se tocan las 18 variables originales — solo se agregan nuevas al final de
DB.catalog y nuevas entradas a DB.data.
"""
import json
import re
import statistics
import unicodedata

DATA_DIR = "/Users/cristobal/Downloads/maqueta/data"
EXPLORADOR = "/Users/cristobal/Downloads/maqueta/explorador-comunal.html"


def norm_name(s):
    s = unicodedata.normalize("NFD", s.upper())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def build_key_mapping(db):
    """Los data_*.js usan comuna_key() (conserva Ñ), pero el DB del explorador
    usa claves 100% ASCII (CAMINA, NUNOA, O HIGGINS...) — se mapean por nombre
    de display, que sí coincide en ambos lados."""
    with open(f"{DATA_DIR}/nombres_comunas.js", encoding="utf-8") as f:
        nombres = json.loads(re.search(r"const NOMBRES_COMUNAS = (\{.*?\});", f.read(), re.S).group(1))
    explorer_by_norm = {norm_name(v): k for k, v in db["nombres"].items()}
    mapping = {}
    for mykey, myname in nombres.items():
        ek = explorer_by_norm.get(norm_name(myname))
        if ek:
            mapping[mykey] = ek
    return mapping


def load_js_object(path, varname):
    with open(path, encoding="utf-8") as f:
        content = f.read()
    m = re.search(r"const " + varname + r" = (\{.*\});", content, re.S)
    return json.loads(m.group(1))


def get_path(record, path):
    cur = record
    for part in path.split("."):
        if cur is None:
            return None
        cur = cur.get(part)
    return cur if isinstance(cur, (int, float)) else None


# (id, area, label, unidad, json_path)
ADMIN_VARS = [
    ("adm_ejecucion", "Administración", "Ejecución presupuestaria", "%", "kpis.ejecucion"),
    ("adm_dependencia_fcm", "Administración", "Dependencia del Fondo Común Municipal", "%", "kpis.dependencia_fcm"),
    ("adm_eficiencia_cobro", "Administración", "Eficiencia de cobro de patentes", "%", "kpis.eficiencia_cobro"),
    ("adm_deuda_flotante_pct", "Administración", "% pagado de deuda de arrastre", "%", "kpis.deuda_flotante_pct"),
    ("adm_ing_total", "Administración", "Ingresos municipales totales", "M$", "ingresos.total"),
    ("adm_ing_fcm_recibido", "Administración", "Ingresos por Fondo Común Municipal", "M$", "ingresos.fcm_recibido"),
    ("adm_ing_transferencias", "Administración", "Transferencias recibidas", "M$", "ingresos.transferencias"),
    ("adm_gas_total", "Administración", "Gastos municipales totales", "M$", "gastos.total"),
    ("adm_gas_bienes_servicios", "Administración", "Gasto en bienes y servicios", "M$", "gastos.bienes_servicios"),
    ("adm_gas_inversion", "Administración", "Gasto en inversión", "M$", "gastos.inversion"),
    ("adm_gas_educacion", "Administración", "Gasto transferido a Educación", "M$", "gastos.educacion"),
    ("adm_gas_salud", "Administración", "Gasto transferido a Salud", "M$", "gastos.salud"),
    ("adm_deuda_flotante", "Administración", "Deuda flotante (de arrastre)", "M$", "deuda_flotante"),
    ("adm_poblacion", "Administración", "Población (base Administración)", "habitantes", "poblacion"),
]

DOTACION_VARS = [
    ("dot_municipal_total", "Dotación", "Funcionarios sector Municipal", "personas", "municipal_total"),
    ("dot_educacion_total", "Dotación", "Funcionarios sector Educación", "personas", "educacion_total"),
    ("dot_salud_total", "Dotación", "Funcionarios sector Salud", "personas", "salud_total"),
    ("dot_consolidado_total", "Dotación", "Funcionarios totales (consolidado)", "personas", "consolidado_total"),
    ("dot_planta", "Dotación", "Funcionarios de Planta (consolidado)", "personas", "consolidado.planta"),
    ("dot_contrata", "Dotación", "Funcionarios a Contrata (consolidado)", "personas", "consolidado.contrata"),
    ("dot_honorarios", "Dotación", "Funcionarios a Honorarios (consolidado)", "personas", "consolidado.honorarios"),
    ("dot_gasto_total", "Dotación", "Gasto total en personal (consolidado)", "M$", "gasto.total"),
    ("dot_gasto_planta", "Dotación", "Gasto en personal de Planta", "M$", "gasto.planta"),
    ("dot_gasto_contrata", "Dotación", "Gasto en personal a Contrata", "M$", "gasto.contrata"),
    ("dot_gasto_honorarios", "Dotación", "Gasto en personal a Honorarios", "M$", "gasto.honorarios"),
    ("dot_lim42", "Dotación", "Límite legal 42% (gasto en personal)", "%", "limites.lim42"),
    ("dot_lim40", "Dotación", "Límite legal 40% (personal a contrata)", "%", "limites.lim40"),
    ("dot_lim10", "Dotación", "Límite legal 10% (honorarios)", "%", "limites.lim10"),
]

EDUCACION_VARS = [
    ("edu_edad_escolar", "Educación", "Población en edad escolar", "personas", "edad_escolar"),
    ("edu_asistencia_pct", "Educación", "Asistencia escolar comunal", "%", "asistencia_pct"),
    ("edu_establecimientos", "Educación", "N° de establecimientos municipales", "N°", "establecimientos"),
    ("edu_docentes_aula", "Educación", "Docentes de aula contratados", "N°", "docentes_aula"),
    ("edu_alumnos_docente", "Educación", "Alumnos por docente", "ratio", "alumnos_por_docente"),
    ("edu_gasto_alumno_anual", "Educación", "Gasto por alumno (anual)", "M$", "gasto_alumno_anual"),
    ("edu_dependencia_subvencion", "Educación", "Dependencia de la subvención estatal", "%", "dependencia_subvencion_pct"),
    ("edu_ing_subvencion", "Educación", "Ingresos por subvención escolar", "M$", "ingresos.subvencion"),
    ("edu_ing_aporte_municipal", "Educación", "Aporte municipal a Educación", "M$", "ingresos.aporte_municipal"),
    ("edu_ing_total", "Educación", "Ingresos totales de Educación", "M$", "ingresos.total"),
    ("edu_gas_personal", "Educación", "Gasto en personal de Educación", "M$", "gastos.personal"),
    ("edu_gas_operacional", "Educación", "Gasto operacional de Educación", "M$", "gastos.operacional"),
    ("edu_docentes", "Educación", "N° de docentes (por función)", "personas", "personal_funcion.docentes"),
    ("edu_no_docentes", "Educación", "N° de no docentes (por función)", "personas", "personal_funcion.no_docentes"),
    ("edu_aporte_municipal_pct", "Educación", "Aporte municipal / ingreso municipal total", "%", "aporte_municipal_pct_gasto_muni"),
]

SALUD_VARS = [
    ("sal_cobertura", "Salud", "Cobertura de salud primaria municipal", "%", "ISAL005"),
    ("sal_gasto_inscrito", "Salud", "Gasto anual por inscrito validado", "M$", "ISAL23"),
    ("sal_aporte_minsal_pct", "Salud", "Aporte del MINSAL sobre ingreso total", "%", "ISAL012"),
    ("sal_aporte_municipal", "Salud", "Aporte municipal al sector Salud", "M$", "ISAL013"),
    ("sal_gastos_total", "Salud", "Gastos totales de Salud", "M$", "ISAL018"),
    ("sal_gasto_funcionamiento", "Salud", "Gasto de funcionamiento de Salud", "M$", "ISAL021"),
    ("sal_inversion", "Salud", "Inversión real en Salud", "M$", "ISAL023"),
    ("sal_gasto_capacitacion", "Salud", "Gasto en capacitación de personal", "M$", "ISAL025"),
    ("sal_gasto_planta", "Salud", "Gasto en personal de Planta (Salud)", "M$", "ISAL029"),
    ("sal_gasto_contrata", "Salud", "Gasto en personal a Contrata (Salud)", "M$", "ISAL031"),
    ("sal_gasto_honorarios", "Salud", "Gasto en personal a Honorarios (Salud)", "M$", "ISAL032"),
    ("sal_personal_planta", "Salud", "N° de personal de Planta (Salud)", "personas", "MPSP"),
    ("sal_personal_contrata", "Salud", "N° de personal a Contrata (Salud)", "personas", "MPSCC"),
    ("sal_personal_honorarios", "Salud", "N° de personal a Honorarios (Salud)", "personas", "MPSH"),
    ("sal_medicos", "Salud", "N° de médicos contratados", "personas", "MTFCM"),
    ("sal_ambulancias", "Salud", "N° de ambulancias", "N°", "MAMBUL"),
    ("sal_cesfam", "Salud", "N° de CESFAM en la comuna", "N°", "MCESFAM"),
    ("sal_sapu", "Salud", "N° de SAPU en la comuna", "N°", "MSAPU"),
    ("sal_farmacias", "Salud", "N° de farmacias municipales", "N°", "MSFARM"),
    ("sal_consultas_aps", "Salud", "Consultas médicas realizadas en APS", "N°", "GTCM"),
]

PERFIL_VARS = [
    ("per_rural_pct", "Perfil Comunal", "Población rural", "%", "rural_pct"),
    ("per_camaras", "Perfil Comunal", "N° de cámaras de vigilancia", "N°", "seguridad.camaras"),
    ("per_vehiculos_seguridad", "Perfil Comunal", "Vehículos de patrullaje municipal", "N°", "seguridad.vehiculos"),
    ("per_cultura_personal", "Perfil Comunal", "Personal en gestión cultural", "personas", "cultura.personal"),
    ("per_cultura_gasto", "Perfil Comunal", "Gasto en programas culturales", "M$", "cultura.gasto"),
    ("per_areas_verdes_m2hab", "Perfil Comunal", "Áreas verdes con mantención por habitante", "m²", "areas_verdes.m2_hab"),
    ("per_parques", "Perfil Comunal", "N° de parques urbanos", "N°", "areas_verdes.parques"),
    ("per_plazas", "Perfil Comunal", "N° de plazas", "N°", "areas_verdes.plazas"),
    ("per_gasto_jardines", "Perfil Comunal", "Gasto en mantención de jardines", "M$", "areas_verdes.gasto_jardines"),
    ("per_agua_pct", "Perfil Comunal", "Viviendas con conexión a agua potable", "%", "vivienda.agua_pct"),
    ("per_viviendas_censo", "Perfil Comunal", "Viviendas de la comuna (censo)", "N°", "vivienda.viviendas_censo"),
    ("per_permisos_edificacion", "Perfil Comunal", "Permisos de edificación entregados", "N°", "vivienda.permisos"),
    ("per_avaluo", "Perfil Comunal", "Avalúo fiscal de propiedades municipales", "M$", "vivienda.avaluo"),
]

SOCIAL_VARS = [
    ("soc_vulnerabilidad_pct", "Social", "Vulnerabilidad social (RSH 0-40%)", "%", "vulnerabilidad_pct"),
    ("soc_rsh60", "Social", "Adultos mayores (60+) inscritos en RSH", "personas", "rsh60"),
    ("soc_rsh60_pct", "Social", "% de inscritos en RSH con 60 años o más", "%", "rsh60_pct"),
    ("soc_asistencia_directa", "Social", "Asistencia social directa (total)", "M$", "asistencia_directa"),
    ("soc_asistencia_directa_hab", "Social", "Asistencia social directa por habitante", "M$", "asistencia_directa_hab"),
    ("soc_hogares_total", "Social", "Hogares encuestados en el RSH", "hogares", "hogares.total"),
    ("soc_hogares_vulnerables", "Social", "Hogares vulnerables (0-40% RSH)", "hogares", "hogares.vulnerables"),
    ("soc_hogares_medios", "Social", "Hogares de ingreso medio (41-70% RSH)", "hogares", "hogares.medios"),
    ("soc_hogares_medios_altos", "Social", "Hogares medios-altos (71-100% RSH)", "hogares", "hogares.medios_altos"),
    ("soc_org_comunitarias", "Social", "Transferencias a organizaciones comunitarias", "M$", "org_comunitarias"),
    ("soc_gasto_prog_sociales", "Social", "Gasto en programas sociales", "M$", "gasto_prog_sociales"),
    ("soc_gasto_social_total", "Social", "Gasto social total", "M$", "gasto_social_total"),
]

SOURCES = {
    "Administración": (f"{DATA_DIR}/data_administracion.js", "DATA_ADMINISTRACION", ADMIN_VARS),
    "Dotación": (f"{DATA_DIR}/data_dotacion.js", "DATA_DOTACION", DOTACION_VARS),
    "Educación": (f"{DATA_DIR}/data_educacion.js", "DATA_EDUCACION", EDUCACION_VARS),
    "Salud": (f"{DATA_DIR}/data_salud.js", "DATA_SALUD", SALUD_VARS),
    "Perfil Comunal": (f"{DATA_DIR}/data_perfil.js", "DATA_PERFIL", PERFIL_VARS),
    "Social": (f"{DATA_DIR}/data_social.js", "DATA_SOCIAL", SOCIAL_VARS),
}


def build_series_and_ranking(dataset, path, key_mapping):
    series = {}
    all_years = set()
    for comuna, years in dataset.items():
        explorer_key = key_mapping.get(comuna)
        if not explorer_key:
            continue
        ser = {}
        for anio, record in years.items():
            v = get_path(record, path)
            if v is not None:
                ser[anio] = v
                all_years.add(anio)
        if ser:
            series[explorer_key] = ser

    ranking = {}
    for anio in all_years:
        vals = [ser[anio] for ser in series.values() if anio in ser]
        if not vals:
            continue
        ranking[anio] = {
            "mediana_nacional": round(statistics.median(vals), 3),
            "total_comunas": len(vals),
        }
    return series, ranking


def main():
    with open(EXPLORADOR, encoding="utf-8") as f:
        content = f.read()

    idx = content.find("const DB")
    tail_start = content.find(";\n", idx)
    db_str = content[idx + len("const DB = \n"): tail_start]
    db = json.loads(db_str)
    key_mapping = build_key_mapping(db)

    existing_ids = {c["id"] for c in db["catalog"]}
    added = 0
    for area, (path, varname, var_defs) in SOURCES.items():
        dataset = load_js_object(path, varname)
        for var_id, area_label, label, unidad, json_path in var_defs:
            if var_id in existing_ids:
                continue
            series, ranking = build_series_and_ranking(dataset, json_path, key_mapping)
            if not series:
                print(f"AVISO: sin datos para {var_id} ({json_path})")
                continue
            db["catalog"].append({
                "id": var_id, "area": area_label, "label": label,
                "unidad": unidad, "code": json_path,
            })
            db["data"][var_id] = {"series": series, "ranking": ranking}
            added += 1

    new_db_str = json.dumps(db, ensure_ascii=False, separators=(",", ":"))
    new_content = content[:idx] + "const DB = \n" + new_db_str + content[tail_start:]

    with open(EXPLORADOR, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"OK: {added} variables nuevas agregadas ({len(db['catalog'])} en total)")


if __name__ == "__main__":
    main()
