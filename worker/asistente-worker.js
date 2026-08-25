// worker/asistente-worker.js
// Backend del "Asistente Luz Cívica" — Cloudflare Worker + Workers AI.
//
// Costo: $0 mientras te mantengas dentro de la cuota diaria gratuita de
// Workers AI (plan gratuito de Cloudflare). Si se agota la cuota del día,
// Workers AI simplemente devuelve un error — Cloudflare NO te cobra solo
// por pasarte, salvo que tú mismo hayas activado el plan pagado.
//
// Ver worker/README.md para instrucciones de despliegue (wrangler).

// 8B en vez de 3B: en pruebas, el modelo chico se equivocaba leyendo JSON
// largo (ej. el historial multi-año). El 8B cuesta más "neuronas" por
// respuesta pero sigue siendo gratis dentro de la cuota diaria — una
// respuesta corta como estas usa ~13 neuronas.
const MODELO = "@cf/meta/llama-3.1-8b-instruct-fp8";

// Cambia esto por el dominio real donde publiques el sitio (GitHub Pages,
// dominio propio, etc.). Puedes poner varios separados por coma.
const ORIGENES_PERMITIDOS = [
  "https://proteus1446.github.io",
  "http://localhost:8756", // para probar en local con python -m http.server
];

function corsHeaders(origin) {
  const permitido = ORIGENES_PERMITIDOS.includes(origin) ? origin : ORIGENES_PERMITIDOS[0];
  return {
    "Access-Control-Allow-Origin": permitido,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  };
}

const SYSTEM_PROMPT = `Eres el Asistente de Luz Cívica, una plataforma chilena de transparencia municipal.
Tu única función es ayudar a entender los datos que la aplicación te entrega en el mensaje del usuario (bloques "GLOSARIO", "DATOS" y, si vienen, "HISTORIAL" y "RANKING").

Reglas estrictas:
- Usa EXCLUSIVAMENTE las cifras de los bloques DATOS/HISTORIAL/RANKING. Nunca inventes números, ni datos de otra comuna/año que no estén en esos bloques.
- El bloque GLOSARIO te explica qué significa cada campo del JSON (nombres técnicos como "deficit", "lim40", "casen_pct"). Úsalo para interpretar los datos, pero nunca lo cites como si fuera un dato.
- Si el usuario pide algo que no está en ningún bloque entregado (ej. un año que no aparece en HISTORIAL, o comparar comunas cuando no viene RANKING), dilo explícitamente: "no tengo ese dato en pantalla" — no lo estimes.
- Cuando el mensaje incluya un bloque HISTORIAL con varios años, ÚSALO para describir la evolución/tendencia en el tiempo (subió, bajó, se mantuvo estable, con qué cifras).
- Cuando el mensaje incluya un bloque RANKING (comparación real, ya calculada, entre TODAS las comunas para el año seleccionado — trae el top 5 y los últimos 5 de cada campo), ÚSALO para responder preguntas del tipo "qué comuna tiene más/menos X" o "qué alcalde gana más" — es la ÚNICA fuente válida para comparar entre comunas. Nombra la comuna y la cifra exacta del RANKING; si el campo que preguntan no está en RANKING, dilo.
- Si no viene ni HISTORIAL ni RANKING y te preguntan por evolución en el tiempo o comparación entre comunas, responde solo con el bloque DATOS y aclara que no tienes ese detalle cargado para esta pregunta.
- Distingue con claridad: (1) el dato tal cual, (2) una comparación si hay base para hacerla dentro de los mismos datos, (3) una interpretación en lenguaje simple.
- Nunca calcules un déficit, indicador financiero o metodológico distinto al que ya viene calculado en los datos; solo explica lo que ya está calculado.
- Para las unidades de cada cifra (pesos, miles de $, %, etc.), usa EXACTAMENTE la unidad indicada en el GLOSARIO para ese campo. No multipliques, no dividas ni conviertas de escala (ej. no transformes "miles de $" en "millones" salvo que el GLOSARIO lo pida explícitamente) — copia el número tal cual viene en DATOS/HISTORIAL, solo agregándole la unidad correspondiente.
- IMPORTANTE sobre decimales: los números en DATOS/HISTORIAL vienen en formato JSON, con PUNTO como separador decimal (ej. 664.297 significa "664 coma 297", NO "664 mil 297"). En español de Chile el punto se usa para separar miles, así que mostrar ese número tal cual con un punto confundiría al lector. Por eso, al presentar cifras al usuario, REDONDEA a entero (sin decimales) los montos en pesos/miles de $ y las cantidades (ej. "664", "46.745.454"), y usa como máximo 1 decimal con COMA (ej. "17,3%") en los porcentajes.
- Responde en español de Chile, en 2-5 frases, tono claro y neutral, sin tecnicismos innecesarios.
- Si el bloque DATOS viene vacío o nulo, dile al usuario que seleccione una comuna y año en la página.`;

// Explica qué significa cada campo del JSON, por tema. Definiciones tomadas
// de las fórmulas reales en scripts/build_*.py (que a su vez usan los
// códigos oficiales SINIM) — no son suposiciones por nombre de campo.
const GLOSARIO = {
  // Usado SOLO dentro del Panel Comunal — ahí administracion es la versión
  // simplificada (solo estos 3 campos). La página dedicada de Administración
  // (tema="administracion") tiene una estructura mucho más completa, ver
  // GLOSARIO.administracion más abajo.
  administracion_panel:
    "deficit: superávit(+)/déficit(-) presupuestario municipal, dato oficial reportado a Contraloría, en miles de $ · delta_pct: variación % del déficit vs. año anterior · gasto_hab: gasto municipal (excluyendo lo transferido a educación y salud) por habitante, EN PESOS (no en miles)",
  // Página dedicada de Administración (maqueta_administracion.html).
  administracion:
    "poblacion: población total de la comuna · deficit: superávit(+)/déficit(-) presupuestario municipal, dato oficial reportado a Contraloría, en miles de $ · situacion: texto \"Superávit\" o \"Déficit\" (mismo signo que deficit) · deuda_flotante: deuda flotante municipal a fin de año, en miles de $ (obligaciones pendientes de pago) · deuda_flotante_pagado: parte de esa deuda flotante que ya fue pagada, en miles de $ · kpis.dependencia_fcm: % de los ingresos municipales que provienen del Fondo Común Municipal (FCM) — mientras más alto, más depende la comuna de la redistribución nacional y menos de ingresos propios · kpis.ejecucion: % del presupuesto vigente que efectivamente se gastó/ejecutó en el año (ejecución presupuestaria) · kpis.eficiencia_cobro: % de eficiencia en el cobro de ingresos propios (permisos, patentes, impuesto territorial, etc.) · kpis.deuda_flotante_pagado_pct: % de la deuda flotante que fue pagada durante el año (100% si no había deuda) · ingresos.ipp: ingresos propios permanentes (patentes, permisos, impuesto territorial), en miles de $ · ingresos.fcm_recibido: monto recibido del Fondo Común Municipal, en miles de $ · ingresos.transferencias: transferencias de otras instituciones públicas, en miles de $ · ingresos.otros: otros ingresos no clasificados en las categorías anteriores, en miles de $ · ingresos.total: ingresos municipales totales, en miles de $ · gastos.personal: gasto en remuneraciones de personal municipal, en miles de $ · gastos.bienes_servicios: gasto en bienes y servicios de consumo, en miles de $ · gastos.salud/educacion: gasto municipal transferido a los sectores salud/educación, en miles de $ · gastos.inversion: gasto en inversión (obras, equipamiento), en miles de $ · gastos.fcm: aporte que la comuna hace AL Fondo Común Municipal (distinto de ingresos.fcm_recibido, que es lo que recibe DE vuelta), en miles de $ · gastos.otros: otros gastos no clasificados, en miles de $ · gastos.total: gasto municipal total, en miles de $",
  // Usado SOLO dentro del Panel Comunal.
  educacion_panel:
    "deficit: ingresos menos gastos del área educación municipal, en miles de $ · delta_pct: variación % vs. año anterior · admin_tipo: quién administra los establecimientos (DAEM, Corporación municipal, Depto./Dirección) · cobertura: % de cobertura de matrícula municipal (indicador SINIM IEDU009) · gasto_alumno_mensual: gasto mensual por alumno, en miles de $ · alumnos_docente: cantidad de alumnos por cada docente",
  // Página dedicada de Educación (maqueta_educacion.html).
  educacion:
    "activa: si el área educación tuvo gasto/actividad ese año (true/false) · admin_tipo: quién administra los establecimientos (DAEM, Corporación municipal, Depto./Dirección) · edad_escolar: cantidad de niños/jóvenes en edad escolar en la comuna · cobertura_pct: % de cobertura de matrícula municipal sobre la población en edad escolar (indicador SINIM IEDU009) · asistencia_pct: % de asistencia escolar comunal (indicador SINIM IEDU005) · matricula: cantidad total de alumnos matriculados en establecimientos municipales · establecimientos: número de establecimientos de educación municipal, rurales y urbanos (IEDU002) · docentes_aula: cantidad de docentes de aula · alumnos_por_docente: cantidad de alumnos por cada docente de aula · gasto_alumno_anual/gasto_alumno_mensual: gasto anual/mensual por alumno, en miles de $ · dependencia_subvencion_pct: % que representa la subvención del MINEDUC sobre el ingreso total del sector educación (IEDU019) · ingresos.subvencion: subvención escolar recibida del MINEDUC, en miles de $ (IEDU018) · ingresos.aporte_municipal: aporte que el propio municipio pone al área educación, en miles de $ (IEDU020) · ingresos.total: ingresos totales del área educación, en miles de $ (IEDU999) · gastos.personal: gasto en personal del sector educación, en miles de $ (IEDU026) · gastos.operacional: gastos de funcionamiento del sector educación, en miles de $ (IEDU029) · gastos.inversion: inversión real (obras/equipamiento) del sector educación, en miles de $ (IEDU031) · gastos.total: gasto total devengado del área educación, en miles de $ (IEDU025) · personal_contrato.planta/contrata/cdt/honorarios: cantidad de personal de educación por tipo de contrato (IEDU040/042/041/043) · ingreso_municipal_total: ingresos municipales totales de TODA la comuna (no solo educación), en miles de $, para dar contexto de cuánto representa el aporte municipal a educación · aporte_municipal_pct_ingreso_muni: % que el aporte municipal a educación representa sobre el ingreso municipal total",
  // Usado SOLO dentro del Panel Comunal — ahí salud es la versión
  // simplificada. La página dedicada de Salud (tema="salud") guarda los
  // campos con sus códigos SINIM originales sin traducir, ver GLOSARIO.salud.
  salud_panel:
    "deficit: ingresos menos gastos totales del sector salud municipal (atención primaria), en miles de $ · delta_pct: variación % vs. año anterior · medicos_1000: médicos equivalente jornada completa por cada 1.000 inscritos validados en el sistema municipal · inscritos_fonasa: población inscrita validada en el sistema de salud municipal (no es todo FONASA, solo la red municipal) · gasto_inscrito: gasto anual en salud por cada persona inscrita, en miles de $",
  // Página dedicada de Salud (maqueta_salud.html). Guarda los campos con
  // los códigos SINIM originales (sin renombrar) — definiciones tomadas
  // del diccionario oficial SINIM, no adivinadas.
  salud:
    "GTCM: consultas médicas realizadas en atención primaria (APS) en el año, cantidad · HPISM: población inscrita validada en el sistema de salud municipal (FONASA), cantidad de personas · ISAL005: % de cobertura de salud primaria municipal · ISAL009: ingresos totales percibidos por el área salud, en miles de $ · ISAL010: ingresos del área salud descontando lo transferido por el propio municipio, en miles de $ · ISAL012: % que representa el aporte per cápita del MINSAL sobre el ingreso total del sector salud · ISAL013: aporte municipal al sector salud, en miles de $ · ISAL015: % que representa el aporte municipal sobre el ingreso total percibido por salud · ISAL018: gasto total devengado del área salud, en miles de $ · ISAL019: gasto en personal del sector salud, en miles de $ · ISAL021: gasto de funcionamiento (no personal) del sector salud, en miles de $ · ISAL023: inversión real (obras/equipamiento) del sector salud, en miles de $ · ISAL025: gasto en capacitación de personal de salud, en miles de $ · ISAL029/ISAL031/ISAL032: gasto en personal de planta/contrata/honorarios del sector salud, en miles de $ · ISAL23: gasto anual del área salud por cada habitante inscrito validado, en miles de $ (es el mismo campo que gasto_inscrito en el Panel Comunal) · MAMBUL/MCECOF/MCESFAM/MCOSAM/MDENTAL/MNCGR/MNCGU/MNPR/MSAPU/MSFARM/MSOPT: cantidad de cada tipo de establecimiento o recurso de salud en la comuna (ambulancias, CECOF, CESFAM, COSAM, clínicas dentales móviles, consultorios rurales, consultorios urbanos, postas rurales, SAPU, farmacias municipales, ópticas municipales, respectivamente) · MPSCC/MPSCDT/MPSH/MPSOC/MPSP: cantidad de personal de salud por tipo de contrato (contrata, código del trabajo, honorarios, otro tipo/programas, planta, respectivamente) · MTFCE/MTFCM/MTFFOND/MTFGER/MTFKINE/MTFMATRO/MTFNUTRI/MTFODON/MTFPSICO/MTFPSIQ/MTFTECENF/MTFTECMED: cantidad de profesionales de salud contratados al 31 de diciembre, por especialidad (enfermeras, médicos, fonoaudiólogos, geriatras, kinesiólogos, matronas, nutricionistas, odontólogos, psicólogos, psiquiatras, técnicos en enfermería, tecnólogos médicos, respectivamente) · MTAS: tipo de administración del sistema de salud municipal (texto) · MASM: si el municipio administra servicio de salud primaria (Sí/No)",
  // Usado SOLO dentro del Panel Comunal (ver GLOSARIO.panel más abajo): ahí
  // dotacion.municipal/educacion/salud son números simples (cantidad de
  // funcionarios). OJO: en la página dedicada de Dotación (tema="dotacion"),
  // "municipal" es un OBJETO con desglose — ver GLOSARIO.dotacion, son
  // estructuras distintas aunque compartan nombre de campo.
  dotacion_panel:
    "total: dotación total de funcionarios municipales (todas las áreas) · municipal: cantidad TOTAL de funcionarios del área municipal propiamente tal (no educación/salud) · municipal_detalle.planta/contrata/honorarios/comunitarios: desglose de esos mismos funcionarios municipales por tipo de contrato (los 4 valores suman 'municipal') · educacion/salud: funcionarios de los establecimientos de esas áreas dependientes del municipio · gasto_personal: gasto total consolidado en remuneraciones de personal, en miles de $ · planta_pct: % de la dotación que está en calidad de planta (v/s contrata, honorarios, código del trabajo) · lim40: gasto en personal a contrata como % del límite legal (40% del gasto en personal de planta) — un valor >100% indica que se excede el límite legal",
  // Página dedicada de Dotación (maqueta_dotacion.html). Estructura real y
  // más detallada que la del Panel Comunal.
  dotacion:
    "poblacion: población total de la comuna · profesionalizacion_pct/participacion_femenina_pct: % de funcionarios profesionales / % de mujeres en la dotación · municipal_total: cantidad TOTAL de funcionarios SOLO del área municipal (no incluye educación ni salud) · municipal: desglose de esos mismos funcionarios municipales por tipo de contrato — municipal.planta/contrata/honorarios/comunitarios (los 4 valores SUMAN municipal_total) · educacion_total/salud_total: cantidad de funcionarios de los establecimientos de educación/salud dependientes del municipio (no confundir con municipal_total, son áreas separadas) · consolidado_total: TODOS los funcionarios de las 3 áreas juntas (municipal + educación + salud) = municipal_total + educacion_total + salud_total · consolidado: desglose por tipo de contrato pero MEZCLANDO las 3 áreas juntas (no solo municipal) — usa 'municipal' en vez de 'consolidado' si preguntan específicamente por el área municipal · gasto.planta/contrata/honorarios/comunitarios/total: gasto en remuneraciones por tipo de contrato, en miles de $, sumando las 3 áreas · limites.lim42: gasto en personal como % del límite legal general (tope 42% de ingresos propios permanentes) · limites.lim40: gasto en personal a contrata como % del límite legal (tope 40% del gasto en personal de planta) · limites.lim10: gasto en honorarios como % del límite legal (tope 10% del gasto en personal de planta, Ley 19.280 Art.13) — en limites, un valor por encima de 100% indica que se excede el límite legal respectivo · gasto_por_area.municipal/educacion/salud: gasto en personal de cada área por separado, en miles de $",
  // Usado SOLO dentro del Panel Comunal.
  social_panel:
    "casen_pct: % de personas en situación de pobreza según la encuesta CASEN (indicador SINIM ISOC001) · vulnerabilidad_pct: % de hogares clasificados como vulnerables en el Registro Social de Hogares (tramos 40% más vulnerable) · hogares.vulnerables/medios/medios_altos: cantidad de hogares del Registro Social de Hogares por tramo socioeconómico · asistencia_hab: gasto en asistencia social directa a personas, por habitante, en miles de $ · rshnp: cantidad de personas registradas en el Registro Social de Hogares",
  // Página dedicada de Social (maqueta_social.html).
  social:
    "casen_pct: % de personas en situación de pobreza según la última encuesta CASEN vigente (ISOC001) · rshnp: cantidad total de personas inscritas en el Registro Social de Hogares (RSH) · rsh60: cantidad de personas de 60 años o más inscritas en el RSH · rsh60_pct: % que representan esas personas mayores sobre el total de inscritos en el RSH · asistencia_directa: gasto total en asistencia social directa a personas, en miles de $ · asistencia_directa_hab: ese mismo gasto de asistencia social, por habitante, en miles de $ · asistencia_rm_avg: promedio de gasto en asistencia social por habitante en las comunas de la Región Metropolitana, para comparar (referencia regional, no es un dato de esta comuna en particular) · vulnerabilidad_pct: % de hogares clasificados como vulnerables en el Registro Social de Hogares (tramos de 0-40% de ingresos) · hogares.total: cantidad total de hogares encuestados en el Registro Social de Hogares (RSH) de la comuna · hogares.vulnerables: hogares del RSH en el tramo 0-40% de ingresos (los de mayor vulnerabilidad) · hogares.medios: hogares del RSH en tramos 41-70% de ingresos · hogares.medios_altos: hogares del RSH en tramos 71-100% de ingresos (los de mayores ingresos) · org_comunitarias: transferencias corrientes municipales a organizaciones comunitarias, en miles de $ (IADM87) · gasto_prog_sociales: gasto municipal en programas sociales, en miles de $ · gasto_social_total: gasto social total de la comuna (asistencia social + programas sociales + organizaciones comunitarias), en miles de $",
  // Usado SOLO dentro del Panel Comunal — ahí perfil solo trae densidad,
  // areas_verdes_hab y cementerio (mucho más simple que la página dedicada).
  perfil_panel:
    "densidad: habitantes por km² (Censo/INE) · areas_verdes_hab: metros cuadrados de áreas verdes por habitante · cementerio: si el municipio administra o no cementerio",
  // Página dedicada de Perfil (maqueta_perfil.html).
  perfil:
    "densidad: habitantes por km² (Censo/INE, ICAR007) · poblacion: población total estimada por el INE (ICAR004) · rural_pct: % de población que vive en zonas rurales (ICAR008) · seguridad.gasto_vigilancia: gasto municipal en servicios de vigilancia, en miles de $ · seguridad.camaras/vehiculos: cantidad de cámaras de seguridad / vehículos destinados a seguridad municipal · seguridad.consejo: si la comuna tiene o no Consejo de Seguridad Pública constituido · cultura.gasto: gasto municipal en programas culturales, en miles de $ (BGMAPCUL) · cultura.gasto_pct_total: % que ese gasto en cultura representa sobre el gasto municipal total · cultura.admin: cómo se administra el área cultura · cultura.personal: cantidad de personas contratadas para gestión cultural municipal · areas_verdes.m2_hab: metros cuadrados de áreas verdes CON mantenimiento por habitante (ITER009) · areas_verdes.parques: número de parques urbanos en la comuna · areas_verdes.plazas: número de plazas en la comuna · areas_verdes.gasto_jardines: gasto en mantención de jardines/áreas verdes, en miles de $ (ITER008) · vivienda.agua_conexion: cantidad de viviendas con conexión a red de agua potable, según el último Censo · vivienda.viviendas_censo: cantidad total de viviendas de la comuna, según el último Censo · vivienda.agua_pct: % de viviendas con conexión formal a agua potable (agua_conexion/viviendas_censo) · vivienda.permisos: número de permisos de edificación entregados en el año · vivienda.recepcion_def: número de construcciones con recepción definitiva durante el año · vivienda.avaluo: avalúo fiscal de las propiedades de dominio municipal (edificios municipales, no de todas las viviendas de la comuna), en miles de $ (ITER012)",
};
// El panel comunal mezcla los 6 temas en un solo JSON por año (más
// 'alcalde'), así que recibe el glosario completo de todos los temas.
GLOSARIO.panel =
  "Cada año trae sub-objetos: administracion, educacion, salud, dotacion, social, perfil, y 'alcalde' (nombre/partido). Significado de cada campo por sub-objeto — " +
  "administracion: {" + GLOSARIO.administracion_panel + "} · " +
  "educacion: {" + GLOSARIO.educacion_panel + "} · " +
  "salud: {" + GLOSARIO.salud_panel + "} · " +
  "dotacion: {" + GLOSARIO.dotacion_panel + "} · " +
  "social: {" + GLOSARIO.social_panel + "} · " +
  "perfil: {" + GLOSARIO.perfil_panel + "} · " +
  "alcalde: {nombre: nombre del alcalde en ejercicio · mediana: remuneración BRUTA MEDIANA mensual del alcalde durante el año — este es el valor correcto para responder \"cuánto gana\" o \"quién gana más/menos\" · min/max: remuneración bruta mínima/máxima registrada en algún mes de ese año (pueden incluir bonos, aguinaldos u otros pagos puntuales de un solo mes — NO son el sueldo habitual, no los uses para \"cuánto gana\" salvo que pregunten específicamente por el mes de mayor/menor pago) · grado: grado de la Escala Única de Sueldos (EUS) que determina el sueldo base del alcalde. La escala oficial va de 1 a 6, y funciona AL REVÉS de lo intuitivo: grado 1 es el sueldo MÁS ALTO (comunas grandes/capitales regionales), grado 6 es el MÁS BAJO (comunas pequeñas). Lo fija la ley según población y presupuesto de la comuna — no cambia con los años en el cargo ni lo decide la municipalidad. Muy ocasionalmente aparece grado 7 u 8 en los datos: es un error puntual de un solo año en la fuente oficial (SINIM), no un grado real — si te preguntan por uno de esos casos, acláralo así en vez de inventar una explicación}";

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders(origin) });
    }
    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return new Response(JSON.stringify({ error: "JSON inválido" }), {
        status: 400,
        headers: { "Content-Type": "application/json", ...corsHeaders(origin) },
      });
    }

    const pregunta = String(body.pregunta || "").slice(0, 500);
    if (!pregunta) {
      return new Response(JSON.stringify({ error: "Falta 'pregunta'" }), {
        status: 400,
        headers: { "Content-Type": "application/json", ...corsHeaders(origin) },
      });
    }

    // Limita el tamaño de los bloques que se mandan al modelo (evita
    // payloads gigantes y mantiene el consumo de tokens bajo).
    let datosTexto = "null";
    try {
      datosTexto = JSON.stringify(body.datos ?? null).slice(0, 4000);
    } catch {
      datosTexto = "null";
    }

    let historialTexto = "";
    if (body.historial) {
      try {
        historialTexto = JSON.stringify(body.historial).slice(0, 6000);
      } catch {
        historialTexto = "";
      }
    }

    let rankingTexto = "";
    if (body.ranking) {
      try {
        rankingTexto = JSON.stringify(body.ranking).slice(0, 9000);
      } catch {
        rankingTexto = "";
      }
    }

    const glosario = GLOSARIO[body.tema] || "";

    const contexto = `Tema: ${body.temaLabel || body.tema || "—"}
Comuna: ${body.nombreComuna || body.comuna || "—"}
Año: ${body.anio || "—"}
GLOSARIO (qué significa cada campo, no es un dato): ${glosario || "no disponible"}
DATOS (JSON, únicamente lo visible en pantalla): ${datosTexto}
${historialTexto ? `HISTORIAL (JSON por año, para preguntas de evolución/tendencia): ${historialTexto}\n` : ""}${rankingTexto ? `RANKING (comparación real entre TODAS las comunas para el año ${body.anio || "—"}; por cada campo trae "top" = 5 comunas con el valor más alto y "ultimos" = 5 con el valor más bajo): ${rankingTexto}\n` : ""}
Pregunta del usuario: ${pregunta}`;

    try {
      const respuestaIA = await env.AI.run(MODELO, {
        messages: [
          { role: "system", content: SYSTEM_PROMPT },
          { role: "user", content: contexto },
        ],
        max_tokens: 400,
      });

      const texto =
        (respuestaIA && (respuestaIA.response || respuestaIA.result)) ||
        "No pude generar una respuesta.";

      return new Response(JSON.stringify({ respuesta: texto }), {
        headers: { "Content-Type": "application/json", ...corsHeaders(origin) },
      });
    } catch (err) {
      console.error("Error llamando a Workers AI:", err && err.message, err && err.stack);
      return new Response(
        JSON.stringify({
          error: "El modelo no está disponible en este momento (posible cuota diaria agotada).",
        }),
        { status: 502, headers: { "Content-Type": "application/json", ...corsHeaders(origin) } }
      );
    }
  },
};
