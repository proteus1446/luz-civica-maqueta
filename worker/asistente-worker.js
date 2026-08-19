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
Tu única función es ayudar a entender los datos que la aplicación te entrega en el mensaje del usuario (bloques "GLOSARIO", "DATOS" y, si viene, "HISTORIAL").

Reglas estrictas:
- Usa EXCLUSIVAMENTE las cifras de los bloques DATOS/HISTORIAL. Nunca inventes números, comparaciones nacionales ni datos de otras comunas u otros años que no estén en esos bloques.
- El bloque GLOSARIO te explica qué significa cada campo del JSON (nombres técnicos como "deficit", "lim40", "casen_pct"). Úsalo para interpretar los datos, pero nunca lo cites como si fuera un dato.
- Si el usuario pide algo que no está en los datos entregados (ej. comparar con otra comuna, o un año que no aparece en HISTORIAL), dilo explícitamente: "no tengo ese dato en pantalla" — no lo estimes.
- Cuando el mensaje del usuario incluya un bloque HISTORIAL con varios años, ÚSALO para describir la evolución o tendencia en el tiempo (por ejemplo: subió, bajó, se mantuvo estable, y con qué cifras). Cuando ese bloque no esté presente en el mensaje, responde solo con el bloque DATOS.
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
  administracion:
    "deficit: superávit(+)/déficit(-) presupuestario municipal, dato oficial reportado a Contraloría, en miles de $ · delta_pct: variación % del déficit vs. año anterior · gasto_hab: gasto municipal (excluyendo lo transferido a educación y salud) por habitante, EN PESOS (no en miles)",
  educacion:
    "deficit: ingresos menos gastos del área educación municipal, en miles de $ · delta_pct: variación % vs. año anterior · admin_tipo: quién administra los establecimientos (DAEM, Corporación municipal, Depto./Dirección) · cobertura: % de cobertura de matrícula municipal (indicador SINIM IEDU009) · gasto_alumno_mensual: gasto mensual por alumno, en miles de $ · alumnos_docente: cantidad de alumnos por cada docente",
  salud:
    "deficit: ingresos menos gastos totales del sector salud municipal (atención primaria), en miles de $ · delta_pct: variación % vs. año anterior · medicos_1000: médicos equivalente jornada completa por cada 1.000 inscritos validados en el sistema municipal · inscritos_fonasa: población inscrita validada en el sistema de salud municipal (no es todo FONASA, solo la red municipal) · gasto_inscrito: gasto anual en salud por cada persona inscrita, en miles de $",
  dotacion:
    "total: dotación total de funcionarios municipales (todas las áreas) · municipal: funcionarios del área municipal propiamente tal (no educación/salud) · educacion/salud: funcionarios de los establecimientos de esas áreas dependientes del municipio · gasto_personal: gasto total consolidado en remuneraciones de personal, en miles de $ · planta_pct: % de la dotación que está en calidad de planta (v/s contrata, honorarios, código del trabajo) · lim40: gasto en personal a contrata como % del límite legal (40% del gasto en personal de planta) — un valor >100% indica que se excede el límite legal",
  social:
    "casen_pct: % de personas en situación de pobreza según la encuesta CASEN (indicador SINIM ISOC001) · vulnerabilidad_pct: % de hogares clasificados como vulnerables en el Registro Social de Hogares (tramos 40% más vulnerable) · hogares.vulnerables/medios/medios_altos: cantidad de hogares del Registro Social de Hogares por tramo socioeconómico · asistencia_hab: gasto en asistencia social directa a personas, por habitante, en miles de $ · rshnp: cantidad de personas registradas en el Registro Social de Hogares",
  perfil:
    "densidad: habitantes por km² (Censo/INE) · poblacion: población total (Censo/INE) · rural_pct: % de población que vive en zonas rurales · seguridad.gasto_vigilancia/camaras/vehiculos: recursos municipales destinados a seguridad pública · cultura.gasto/gasto_pct_total: gasto municipal en cultura, y su % sobre el gasto municipal total · areas_verdes.m2_hab: metros cuadrados de áreas verdes por habitante · vivienda.agua_pct: % de viviendas con conexión formal a agua potable · vivienda.avaluo: avalúo fiscal total de las viviendas de la comuna",
};
// El panel comunal mezcla los 6 temas en un solo JSON por año (más
// 'alcalde'), así que recibe el glosario completo de todos los temas.
GLOSARIO.panel =
  "Cada año trae sub-objetos: administracion, educacion, salud, dotacion, social, perfil, y 'alcalde' (nombre/partido). Significado de cada campo por sub-objeto — " +
  "administracion: {" + GLOSARIO.administracion + "} · " +
  "educacion: {" + GLOSARIO.educacion + "} · " +
  "salud: {" + GLOSARIO.salud + "} · " +
  "dotacion: {" + GLOSARIO.dotacion + "} · " +
  "social: {" + GLOSARIO.social + "} · " +
  "perfil: {" + GLOSARIO.perfil + ", areas_verdes_hab: metros cuadrados de áreas verdes por habitante}";

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

    const glosario = GLOSARIO[body.tema] || "";

    const contexto = `Tema: ${body.temaLabel || body.tema || "—"}
Comuna: ${body.nombreComuna || body.comuna || "—"}
Año: ${body.anio || "—"}
GLOSARIO (qué significa cada campo, no es un dato): ${glosario || "no disponible"}
DATOS (JSON, únicamente lo visible en pantalla): ${datosTexto}
${historialTexto ? `HISTORIAL (JSON por año, para preguntas de evolución/tendencia): ${historialTexto}\n` : ""}
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
