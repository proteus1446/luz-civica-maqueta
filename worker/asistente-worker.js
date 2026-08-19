// worker/asistente-worker.js
// Backend del "Asistente Luz Cívica" — Cloudflare Worker + Workers AI.
//
// Costo: $0 mientras te mantengas dentro de la cuota diaria gratuita de
// Workers AI (plan gratuito de Cloudflare). Si se agota la cuota del día,
// Workers AI simplemente devuelve un error — Cloudflare NO te cobra solo
// por pasarte, salvo que tú mismo hayas activado el plan pagado.
//
// Ver worker/README.md para instrucciones de despliegue (wrangler).

const MODELO = "@cf/meta/llama-3.2-3b-instruct";

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
Tu única función es ayudar a entender los datos que la aplicación te entrega en el mensaje del usuario (bloque "DATOS").

Reglas estrictas:
- Usa EXCLUSIVAMENTE las cifras del bloque DATOS. Nunca inventes números, comparaciones nacionales ni datos de otras comunas u otros años que no estén en ese bloque.
- Si el usuario pide algo que no está en los datos entregados (ej. comparar con otra comuna, otro año, o un indicador ausente), dilo explícitamente: "no tengo ese dato en pantalla" — no lo estimes.
- Distingue con claridad: (1) el dato tal cual, (2) una comparación si hay base para hacerla dentro de los mismos datos, (3) una interpretación en lenguaje simple.
- Nunca calcules un déficit, indicador financiero o metodológico distinto al que ya viene calculado en los datos; solo explica lo que ya está calculado.
- Responde en español de Chile, en 2-5 frases, tono claro y neutral, sin tecnicismos innecesarios.
- Si el bloque DATOS viene vacío o nulo, dile al usuario que seleccione una comuna y año en la página.`;

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

    // Limita el tamaño del bloque de datos que se manda al modelo (evita
    // payloads gigantes y mantiene el consumo de tokens bajo).
    let datosTexto = "null";
    try {
      datosTexto = JSON.stringify(body.datos ?? null).slice(0, 4000);
    } catch {
      datosTexto = "null";
    }

    const contexto = `Tema: ${body.temaLabel || body.tema || "—"}
Comuna: ${body.nombreComuna || body.comuna || "—"}
Año: ${body.anio || "—"}
DATOS (JSON, únicamente lo visible en pantalla): ${datosTexto}

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
