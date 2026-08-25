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
- Si el usuario pide algo que no está en ningún bloque entregado (ej. un año que no aparece en HISTORIAL, comparar comunas cuando no viene RANKING, o un tema totalmente distinto — como preguntar por remuneraciones de funcionarios estando en la página de Educación), dilo explícitamente: "no tengo ese dato en esta página" — no lo estimes. Solo ves los datos de la página actual (Tema, arriba), no los de todo el sitio. Si la pregunta suena a que pertenece a OTRO tema de Luz Cívica (administración, educación, salud, dotación, social, perfil, panel comunal), sugiérele en una frase que abra esa página específica del sitio para preguntar ahí.
- Cuando el mensaje incluya un bloque HISTORIAL con varios años, ÚSALO para describir la evolución/tendencia en el tiempo (subió, bajó, se mantuvo estable, con qué cifras).
- Cuando el mensaje incluya un bloque RANKING (comparación real, ya calculada, entre TODAS las comunas para el año seleccionado — trae el top 5 y los últimos 5 de cada campo), ÚSALO para responder preguntas del tipo "qué comuna tiene más/menos X" o "qué alcalde gana más" — es la ÚNICA fuente válida para comparar entre comunas. Nombra la comuna y la cifra exacta del RANKING; si el campo que preguntan no está en RANKING, dilo.
- Si no viene ni HISTORIAL ni RANKING y te preguntan por evolución en el tiempo o comparación entre comunas, responde solo con el bloque DATOS y aclara que no tienes ese detalle cargado para esta pregunta.
- Distingue con claridad: (1) el dato tal cual, (2) una comparación si hay base para hacerla dentro de los mismos datos, (3) una interpretación en lenguaje simple.
- Nunca calcules un déficit, indicador financiero o metodológico distinto al que ya viene calculado en los datos; solo explica lo que ya está calculado.
- Para las unidades de cada cifra (pesos, miles de $, %, etc.), usa EXACTAMENTE la unidad indicada en el GLOSARIO para ese campo. No multipliques, no dividas ni conviertas de escala (ej. no transformes "miles de $" en "millones" salvo que el GLOSARIO lo pida explícitamente) — copia el número tal cual viene en DATOS/HISTORIAL, solo agregándole la unidad correspondiente.
- IMPORTANTE sobre decimales: los números en DATOS/HISTORIAL vienen en formato JSON, con PUNTO como separador decimal (ej. 664.297 significa "664 coma 297", NO "664 mil 297"). En español de Chile el punto se usa para separar miles, así que mostrar ese número tal cual con un punto confundiría al lector. Por eso, al presentar cifras al usuario, REDONDEA a entero (sin decimales) las cantidades (ej. "664"), y usa como máximo 1 decimal con COMA (ej. "17,3%") en los porcentajes.
- IMPORTANTE sobre montos grandes en pesos: para que los leas bien, cualquier monto que en la fuente original estaba en "miles de $" y era muy grande (100.000 o más) YA VIENE DIVIDIDO POR 1.000 en los datos que recibes — es decir, ya está en MILLONES de $, no en miles. Ejemplo: si ves "202885.4" en un campo que el glosario describe como "miles de $", son en realidad $202.885,4 millones (no 202 mil, no 202 millones exactos) — di "$202.885 millones" o redondea a "$202.885 millones" (con 0-1 decimal). Los montos que quedaron con pocos dígitos (menores a 100.000) SÍ siguen en miles de $ tal como dice el glosario. Los porcentajes y conteos de personas NUNCA se reescalan.
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
    "deficit: superávit(+)/déficit(-) municipal (Contraloría), miles de $ · delta_pct: variación % vs. año anterior · gasto_hab: gasto municipal por habitante, EN PESOS (no miles) · dependencia_fcm: % de ingresos que vienen del FCM · deuda_flotante_pagado_pct: % de deuda flotante pagada en el año · ingresos.ipp/fcm_recibido/transferencias/otros/total: ingresos municipales por categoría, miles de $ · gastos.personal/bienes_servicios/salud/educacion/inversion/fcm/otros/total: gastos municipales por categoría, miles de $ (gastos.fcm = aporte AL FCM, distinto de ingresos.fcm_recibido)",
  // Página dedicada de Administración (maqueta_administracion.html).
  administracion:
    "poblacion: población total de la comuna · deficit: superávit(+)/déficit(-) presupuestario municipal, dato oficial reportado a Contraloría, en miles de $ · situacion: texto \"Superávit\" o \"Déficit\" (mismo signo que deficit) · deuda_flotante: deuda flotante municipal a fin de año, en miles de $ (obligaciones pendientes de pago) · deuda_flotante_pagado: parte de esa deuda flotante que ya fue pagada, en miles de $ · kpis.dependencia_fcm: % de los ingresos municipales que provienen del Fondo Común Municipal (FCM) — mientras más alto, más depende la comuna de la redistribución nacional y menos de ingresos propios · kpis.ejecucion: % del presupuesto vigente que efectivamente se gastó/ejecutó en el año (ejecución presupuestaria) · kpis.eficiencia_cobro: % de eficiencia en el cobro de ingresos propios (permisos, patentes, impuesto territorial, etc.) · kpis.deuda_flotante_pagado_pct: % de la deuda flotante que fue pagada durante el año (100% si no había deuda) · ingresos.ipp: ingresos propios permanentes (patentes, permisos, impuesto territorial), en miles de $ · ingresos.fcm_recibido: monto recibido del Fondo Común Municipal, en miles de $ · ingresos.transferencias: transferencias de otras instituciones públicas, en miles de $ · ingresos.otros: otros ingresos no clasificados en las categorías anteriores, en miles de $ · ingresos.total: ingresos municipales totales, en miles de $ · gastos.personal: gasto en remuneraciones de personal municipal, en miles de $ · gastos.bienes_servicios: gasto en bienes y servicios de consumo, en miles de $ · gastos.salud/educacion: gasto municipal transferido a los sectores salud/educación, en miles de $ · gastos.inversion: gasto en inversión (obras, equipamiento), en miles de $ · gastos.fcm: aporte que la comuna hace AL Fondo Común Municipal (distinto de ingresos.fcm_recibido, que es lo que recibe DE vuelta), en miles de $ · gastos.otros: otros gastos no clasificados, en miles de $ · gastos.total: gasto municipal total, en miles de $",
  // Usado SOLO dentro del Panel Comunal.
  educacion_panel:
    "deficit: ingresos menos gastos del área educación municipal, en miles de $ · delta_pct: variación % vs. año anterior · admin_tipo: quién administra los establecimientos (DAEM, Corporación municipal, Depto./Dirección) · cobertura: % de cobertura de matrícula municipal (indicador SINIM IEDU009) · gasto_alumno_mensual: gasto mensual por alumno, en miles de $ · alumnos_docente: cantidad de alumnos por cada docente",
  // Página dedicada de Educación (maqueta_educacion.html).
  educacion:
    "edad_escolar: población en edad escolar de la comuna · matricula: alumnos matriculados en establecimientos municipales · ingresos.total: ingresos totales del área educación, miles de $ (IEDU999) · gastos.total: gasto total del área educación, miles de $ (IEDU025) · gastos.personal: gasto en personal/sueldos del área educación, miles de $ (IEDU026) · personal_contrato.planta/contrata/cdt/honorarios: cantidad de personal de educación por tipo de contrato",
  // Usado SOLO dentro del Panel Comunal — ahí salud es la versión
  // simplificada. La página dedicada de Salud (tema="salud") guarda los
  // campos con sus códigos SINIM originales sin traducir, ver GLOSARIO.salud.
  salud_panel:
    "deficit: ingresos menos gastos totales del sector salud municipal (atención primaria), en miles de $ · delta_pct: variación % vs. año anterior · medicos_1000: médicos equivalente jornada completa por cada 1.000 inscritos validados en el sistema municipal · inscritos_fonasa: población inscrita validada en el sistema de salud municipal (no es todo FONASA, solo la red municipal) · gasto_inscrito: gasto anual en salud por cada persona inscrita, en miles de $",
  // Página dedicada de Salud (maqueta_salud.html). Guarda los campos con
  // los códigos SINIM originales (sin renombrar) — definiciones tomadas
  // del diccionario oficial SINIM, no adivinadas.
  // Recortado a lo esencial (la maqueta no necesita explicar los ~40
  // códigos de infraestructura/personal por especialidad de salud).
  salud:
    "HPISM: población inscrita validada en el sistema de salud municipal · ISAL009: ingresos totales del área salud, miles de $ · ISAL018: gasto total del área salud, miles de $ · ISAL019: gasto en personal/sueldos del área salud, miles de $ · ISAL029/ISAL031/ISAL032: gasto en personal de planta/contrata/honorarios del área salud, miles de $ · ISAL23: gasto anual del área salud por habitante inscrito, miles de $",
  // Usado SOLO dentro del Panel Comunal (ver GLOSARIO.panel más abajo): ahí
  // dotacion.municipal/educacion/salud son números simples (cantidad de
  // funcionarios). OJO: en la página dedicada de Dotación (tema="dotacion"),
  // "municipal" es un OBJETO con desglose — ver GLOSARIO.dotacion, son
  // estructuras distintas aunque compartan nombre de campo.
  dotacion_panel:
    "total/municipal/educacion/salud: cantidad de funcionarios, total y por área · {área}_detalle.planta/contrata/honorarios/cdt/comunitarios: desglose por tipo de contrato de cada área (suman el total de esa área) · gasto_personal: gasto en personal, miles de $ · planta_pct: % de la dotación en calidad de planta · lim40: gasto en contrata como % del límite legal (>100% excede el límite)",
  // Página dedicada de Dotación (maqueta_dotacion.html). Estructura real y
  // más detallada que la del Panel Comunal.
  dotacion:
    "poblacion: población total de la comuna · profesionalizacion_pct/participacion_femenina_pct: % de funcionarios profesionales / % de mujeres en la dotación · municipal_total/educacion_total/salud_total: cantidad TOTAL de funcionarios de cada área POR SEPARADO (municipal propiamente tal, establecimientos de educación, establecimientos de salud — son 3 áreas distintas, no se solapan) · municipal/educacion/salud: para cada una de esas 3 áreas, el desglose de sus funcionarios por tipo de contrato — {área}.planta/contrata/honorarios/cdt/comunitarios (cdt = contrato Código del Trabajo; los valores de cada área SUMAN el _total de esa misma área, ej. municipal.planta+municipal.contrata+municipal.honorarios+municipal.comunitarios = municipal_total). Si preguntan 'cuántos de contrata hay por sector/área', da los 3 números por separado: municipal.contrata, educacion.contrata, salud.contrata — NO restes ni calcules a partir de 'consolidado' · consolidado_total: TODOS los funcionarios de las 3 áreas juntas = municipal_total + educacion_total + salud_total · consolidado: desglose por tipo de contrato pero MEZCLANDO las 3 áreas juntas (municipal+educación+salud sumados) — solo útil si preguntan por el total general, NUNCA lo uses para responder sobre un área específica, para eso usa 'municipal'/'educacion'/'salud' · gasto.planta/contrata/honorarios/comunitarios/total: gasto en remuneraciones por tipo de contrato, en miles de $, sumando las 3 áreas · limites.lim42: gasto en personal como % del límite legal general (tope 42% de ingresos propios permanentes) · limites.lim40: gasto en personal a contrata como % del límite legal (tope 40% del gasto en personal de planta) · limites.lim10: gasto en honorarios como % del límite legal (tope 10% del gasto en personal de planta, Ley 19.280 Art.13) — en limites, un valor por encima de 100% indica que se excede el límite legal respectivo · gasto_por_area.municipal/educacion/salud: gasto en personal de cada área por separado, en miles de $",
  // Usado SOLO dentro del Panel Comunal.
  social_panel:
    "casen_pct: % de personas en situación de pobreza según la encuesta CASEN (indicador SINIM ISOC001) · vulnerabilidad_pct: % de hogares clasificados como vulnerables en el Registro Social de Hogares (tramos 40% más vulnerable) · hogares.vulnerables/medios/medios_altos: cantidad de hogares del Registro Social de Hogares por tramo socioeconómico · asistencia_hab: gasto en asistencia social directa a personas, por habitante, en miles de $ · rshnp: cantidad de personas registradas en el Registro Social de Hogares",
  // Página dedicada de Social (maqueta_social.html).
  social:
    "casen_pct: % de personas en situación de pobreza (encuesta CASEN) · rshnp: personas inscritas en el Registro Social de Hogares (población relacionada) · gasto_social_total: gasto social total de la comuna, miles de $ · asistencia_directa: gasto en asistencia social directa a personas, miles de $",
  // Usado SOLO dentro del Panel Comunal — ahí perfil solo trae densidad,
  // areas_verdes_hab y cementerio (mucho más simple que la página dedicada).
  perfil_panel:
    "densidad: habitantes por km² (Censo/INE) · areas_verdes_hab: metros cuadrados de áreas verdes por habitante · cementerio: si el municipio administra o no cementerio",
  // Página dedicada de Perfil (maqueta_perfil.html).
  perfil:
    "densidad: habitantes por km² · poblacion: población total de la comuna (Censo/INE) · rural_pct: % de población rural · cultura.gasto: gasto municipal en cultura, miles de $ · areas_verdes.gasto_jardines: gasto en mantención de áreas verdes, miles de $",
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

    // El modelo (chico, gratis) lee mal números de 8-9 dígitos — pero los
    // conteos de personas y porcentajes (números cortos) los lee bien. Los
    // montos grandes en pesos casi siempre vienen en "miles de $"; acá se
    // reescalan a "millones de $" (menos dígitos) ANTES de mandarlos al
    // modelo. No toca porcentajes ni conteos, que ya son números cortos —
    // EXCEPTO los campos de esta lista, que NO son dinero pero pueden ser
    // grandes igual (ej. población de comunas grandes) y NUNCA deben
    // reescalarse aunque superen el umbral.
    const UMBRAL_REESCALA = 100000;
    const CAMPOS_NO_MONETARIOS = new Set([
      "poblacion", "matricula", "edad_escolar", "establecimientos",
      "docentes_aula", "rshnp", "rsh60", "rsh60_pct", "HPISM", "GTCM",
      "consolidado_total", "municipal_total", "educacion_total", "salud_total",
      "grado", "anio", "año",
    ]);
    function reescalarMontos(v, key) {
      if (typeof v === "number") {
        if (key && CAMPOS_NO_MONETARIOS.has(key)) return v;
        if (Math.abs(v) >= UMBRAL_REESCALA) return Math.round((v / 1000) * 10) / 10;
        return v;
      }
      if (Array.isArray(v)) return v.map((x) => reescalarMontos(x, key));
      if (v && typeof v === "object") {
        const out = {};
        for (const k of Object.keys(v)) out[k] = reescalarMontos(v[k], k);
        return out;
      }
      return v;
    }

    // Limita el tamaño de los bloques que se mandan al modelo (evita
    // payloads gigantes y mantiene el consumo de tokens bajo).
    let datosTexto = "null";
    try {
      datosTexto = JSON.stringify(reescalarMontos(body.datos ?? null)).slice(0, 4000);
    } catch {
      datosTexto = "null";
    }

    let historialTexto = "";
    if (body.historial) {
      try {
        historialTexto = JSON.stringify(reescalarMontos(body.historial)).slice(0, 6000);
      } catch {
        historialTexto = "";
      }
    }

    // El ranking viene como { "ruta.del.campo": { top:[{comuna,valor}], ... } }
    // — "valor" no dice nada por sí solo, así que hay que usar la ruta del
    // campo (la llave de más afuera) para saber si es monetario o no. No se
    // reusa reescalarMontos() genérico porque ahí perdería ese contexto al
    // bajar por "top"/"ultimos"/"valor" (ninguno es el nombre real del campo).
    function reescalarValor(v) {
      if (typeof v !== "number") return v;
      if (Math.abs(v) >= UMBRAL_REESCALA) return Math.round((v / 1000) * 10) / 10;
      return v;
    }
    function reescalarRanking(ranking) {
      const out = {};
      for (const campo of Object.keys(ranking || {})) {
        const ultimoSegmento = campo.split(".").pop();
        const esMonetario = !CAMPOS_NO_MONETARIOS.has(ultimoSegmento);
        const grupo = ranking[campo] || {};
        out[campo] = {
          top: (grupo.top || []).map((f) => ({
            comuna: f.comuna,
            valor: esMonetario ? reescalarValor(f.valor) : f.valor,
          })),
          ultimos: (grupo.ultimos || []).map((f) => ({
            comuna: f.comuna,
            valor: esMonetario ? reescalarValor(f.valor) : f.valor,
          })),
        };
      }
      return out;
    }

    let rankingTexto = "";
    if (body.ranking) {
      try {
        rankingTexto = JSON.stringify(reescalarRanking(body.ranking)).slice(0, 9000);
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
