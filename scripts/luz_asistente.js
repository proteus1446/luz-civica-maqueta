// scripts/luz_asistente.js
// Widget de chat "Pregúntale a Luz Cívica" — V1
//
// Uso en cada página: antes de este <script>, definir
//   window.LUZ_ASISTENTE_CONFIG = { tema: "educacion", temaLabel: "Educación" };
// El widget lee en vivo el <select id="sel-comuna">, <select id="sel-anio">,
// el objeto global `DATA` (DATA[comuna][anio]) y `NOMBRES_COMUNAS` de la
// página anfitriona — no requiere tocar el resto del código de cada maqueta.
//
// El backend (Cloudflare Worker, ver /worker) recibe SOLO los datos que el
// usuario ya está viendo en pantalla, nunca el dataset completo, y tiene
// instrucciones estrictas de no inventar cifras.
(function () {
  "use strict";

  const CFG = Object.assign(
    {
      endpoint: "", // URL del Worker, ej: "https://luz-civica-asistente.TU-CUENTA.workers.dev/asistente"
      tema: "general",
      temaLabel: "Luz Cívica",
      limiteDiario: 8,
      faq: null, // opcional: array de {texto, incluirHistorial?, incluirRanking?} para reemplazar las preguntas por defecto de esta página
    },
    window.LUZ_ASISTENTE_CONFIG || {}
  );

  // Por defecto (páginas que no definen su propio `faq`): evolución en el
  // tiempo + comparación entre comunas del tema actual. Cada página puede
  // reemplazar esto con preguntas más específicas (ver LUZ_ASISTENTE_CONFIG.faq
  // en panel_comunal.html para el ejemplo con alcalde/gasto por habitante).
  const FAQ = CFG.faq || [
    { texto: "¿Cómo evolucionó esta comuna en el tiempo?", incluirHistorial: true },
    { texto: `¿Qué comuna tiene el valor más alto en ${CFG.temaLabel}?`, incluirRanking: true },
  ];

  // Preguntas escritas a mano que también deberían disparar el ranking
  // entre comunas (ej. "qué alcalde gana más", "qué comuna tiene mayor
  // dotación"), aunque no se use el botón de FAQ.
  const PATRON_COMPARATIVA =
    /(qu[ée]\s+comuna|cu[áa]l\s+comuna|m[áa]s\s+alt[oa]|m[áa]s\s+baj[oa]|mayor\b|menor\b|ranking|compar|todas\s+las\s+comunas|qu[ée]\s+alcalde|cu[áa]l\s+alcalde)/i;

  function hoyKey() {
    const d = new Date();
    return "lc_asist_uso_" + d.toISOString().slice(0, 10);
  }
  function usosHoy() {
    return parseInt(localStorage.getItem(hoyKey()) || "0", 10);
  }
  function registrarUso() {
    localStorage.setItem(hoyKey(), String(usosHoy() + 1));
  }

  // Nota: en las páginas anfitrionas, DATA / NOMBRES_COMUNAS se declaran con
  // `const` a nivel superior de un <script>. Eso las hace visibles como
  // identificadores globales para OTROS <script> del mismo documento, pero
  // NO las agrega como propiedades de `window` (a diferencia de `var`).
  // Por eso acá se accede a los identificadores directamente (con typeof
  // por si la página no los define) en vez de `window.DATA`.
  function datosGlobal() {
    try {
      return typeof DATA !== "undefined" ? DATA : null;
    } catch (e) {
      return null;
    }
  }
  function nombresGlobal() {
    try {
      if (typeof NOMBRES !== "undefined") return NOMBRES;
      if (typeof NOMBRES_COMUNAS !== "undefined") return NOMBRES_COMUNAS;
    } catch (e) {}
    return {};
  }

  function contextoActual() {
    const selComuna = document.getElementById("sel-comuna");
    const selAnio = document.getElementById("sel-anio");
    const comuna = selComuna ? selComuna.value : null;
    const anio = selAnio ? selAnio.value : null;
    const nombres = nombresGlobal();
    const nombre = (comuna && nombres[comuna]) || comuna;
    const dataObj = datosGlobal();
    let datos = null;
    if (dataObj && comuna && anio && dataObj[comuna]) {
      datos = dataObj[comuna][anio] || null;
    }
    return { comuna, nombre, anio, tema: CFG.tema, temaLabel: CFG.temaLabel, datos };
  }

  // Historial multi-año de la comuna seleccionada, para preguntas de
  // evolución/tendencia. Se recorta automáticamente (empezando por los años
  // más antiguos) hasta caber en LIMITE_HISTORIAL_CHARS, para no mandar
  // payloads enormes al modelo.
  const LIMITE_HISTORIAL_CHARS = 6000;
  function historialComuna(comuna) {
    const dataObj = datosGlobal();
    if (!dataObj || !comuna || !dataObj[comuna]) return null;
    const anios = Object.keys(dataObj[comuna]).sort(); // ascendente
    let usados = anios.slice();
    while (usados.length > 1) {
      const serie = {};
      usados.forEach((a) => (serie[a] = dataObj[comuna][a]));
      const texto = JSON.stringify(serie);
      if (texto.length <= LIMITE_HISTORIAL_CHARS) return serie;
      usados = usados.slice(1); // descarta el año más antiguo restante
    }
    return null;
  }

  // Aplana un objeto en pares "ruta.punteada": valor, solo para valores
  // numéricos (para poder rankear cualquier campo sin tener que listarlos
  // a mano por página). Ej: {alcalde:{mediana:123}} -> {"alcalde.mediana":123}
  function aplanarNumeros(obj, prefijo) {
    let out = {};
    if (!obj || typeof obj !== "object") return out;
    Object.keys(obj).forEach((k) => {
      const v = obj[k];
      const ruta = prefijo ? prefijo + "." + k : k;
      if (typeof v === "number" && isFinite(v)) {
        out[ruta] = v;
      } else if (v && typeof v === "object" && !Array.isArray(v)) {
        Object.assign(out, aplanarNumeros(v, ruta));
      }
    });
    return out;
  }

  function obtenerRuta(obj, ruta) {
    return ruta.split(".").reduce((o, k) => (o && typeof o === "object" ? o[k] : undefined), obj);
  }

  // Averigua qué campos numéricos existen para un año, revisando varias
  // comunas (no solo la seleccionada) — si la comuna actual tiene ese campo
  // en null (ej. sin alcalde registrado ese año), igual se detecta el campo
  // gracias a otra comuna que sí lo tenga.
  const MUESTRA_CAMPOS = 25;
  function camposDisponibles(anio, plantilla) {
    const dataObj = datosGlobal();
    let campos = {};
    Object.assign(campos, aplanarNumeros(plantilla));
    if (dataObj) {
      const comunas = Object.keys(dataObj).slice(0, MUESTRA_CAMPOS);
      comunas.forEach((k) => {
        const anioObj = dataObj[k] && dataObj[k][anio];
        if (anioObj) Object.assign(campos, aplanarNumeros(anioObj));
      });
    }
    return Object.keys(campos);
  }

  function sinAcentos(s) {
    return (s || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "");
  }

  // Filtra a solo los campos relevantes para la pregunta (evita mandar los
  // ~30 campos posibles cuando el usuario solo pregunta por uno). Si algún
  // segmento del nombre del campo aparece en la pregunta, se incluye.
  // Si nada calza, usa los campos que ya están en pantalla (o, en último
  // caso, un puñado cualquiera) — nunca deja el ranking vacío.
  const MAX_CAMPOS_RANKING = 6;
  function filtrarCampos(campos, pregunta, plantilla) {
    const preguntaNorm = sinAcentos(pregunta);
    const coincidentes = campos.filter((c) =>
      c.split(".").some((seg) => seg.length > 3 && preguntaNorm.includes(sinAcentos(seg)))
    );
    let elegidos = coincidentes.length ? coincidentes : Object.keys(aplanarNumeros(plantilla));
    if (!elegidos.length) elegidos = campos;

    // Desambiguación: si dentro de un mismo grupo (ej. "alcalde.mediana",
    // "alcalde.min", "alcalde.max") hay una variante "mediana" y la
    // pregunta no pidió explícitamente el mínimo/máximo puntual, nos
    // quedamos SOLO con "mediana" — evita que el modelo (que a veces se
    // confunde) elija "max" para preguntas genéricas de "cuánto gana".
    const pidioMin = /\bm[íi]nim/.test(preguntaNorm);
    const pidioMax = /\bm[áa]xim/.test(preguntaNorm);
    if (!pidioMin && !pidioMax) {
      const grupos = {};
      elegidos.forEach((c) => {
        const partes = c.split(".");
        const ultimo = partes[partes.length - 1];
        const padre = partes.slice(0, -1).join(".");
        if (!grupos[padre]) grupos[padre] = [];
        grupos[padre].push({ campo: c, ultimo });
      });
      const filtrados = [];
      Object.values(grupos).forEach((grupo) => {
        const tieneMediana = grupo.some((g) => g.ultimo === "mediana");
        grupo.forEach((g) => {
          if (tieneMediana && (g.ultimo === "min" || g.ultimo === "max")) return; // descarta min/max
          filtrados.push(g.campo);
        });
      });
      elegidos = filtrados;
    }

    return elegidos.slice(0, MAX_CAMPOS_RANKING);
  }

  // Ranking real (calculado en JS, no por el modelo) entre TODAS las
  // comunas para el año seleccionado. Top 5 y últimos 5, solo de los
  // campos relevantes a la pregunta (para no exceder el tamaño permitido).
  const TOPE_COMUNAS_RANKING = 5;
  function rankingComparativo(anio, plantilla, pregunta) {
    const dataObj = datosGlobal();
    const nombres = nombresGlobal();
    if (!dataObj || !anio) return null;
    const disponibles = camposDisponibles(anio, plantilla);
    if (!disponibles.length) return null;
    const campos = filtrarCampos(disponibles, pregunta, plantilla);
    if (!campos.length) return null;

    const resultado = {};
    campos.forEach((campo) => {
      const filas = [];
      Object.keys(dataObj).forEach((comunaKey) => {
        const anioObj = dataObj[comunaKey] && dataObj[comunaKey][anio];
        if (!anioObj) return;
        const valor = obtenerRuta(anioObj, campo);
        if (typeof valor === "number" && isFinite(valor)) {
          filas.push({ comuna: nombres[comunaKey] || comunaKey, valor });
        }
      });
      if (filas.length < 2) return;
      filas.sort((a, b) => b.valor - a.valor);
      resultado[campo] = {
        top: filas.slice(0, TOPE_COMUNAS_RANKING),
        ultimos: filas.slice(-TOPE_COMUNAS_RANKING).reverse(),
      };
    });
    return resultado;
  }

  // ---- estilos (con prefijo lc-asist- para no chocar con la página) ----
  const css = `
  .lc-asist-btn{position:fixed;right:20px;bottom:20px;z-index:9999;display:flex;align-items:center;gap:8px;
    background:linear-gradient(135deg,#0F2A5F,#1A4A9C);color:#fff;border:0;border-radius:999px;
    padding:12px 18px;font:600 14px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;
    box-shadow:0 6px 20px rgba(15,42,95,.35);cursor:pointer;transition:transform .15s ease;}
  .lc-asist-btn:hover{transform:translateY(-2px);}
  .lc-asist-panel{position:fixed;right:20px;bottom:84px;z-index:9999;width:360px;max-width:calc(100vw - 32px);
    max-height:70vh;background:#fff;border-radius:16px;box-shadow:0 12px 40px rgba(15,42,95,.25);
    display:none;flex-direction:column;overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;}
  .lc-asist-panel.open{display:flex;}
  .lc-asist-head{background:linear-gradient(135deg,#0F2A5F,#1A4A9C);color:#fff;padding:14px 16px;}
  .lc-asist-head b{font-size:14px;}
  .lc-asist-head .lc-ctx{font-size:12px;opacity:.85;margin-top:2px;}
  .lc-asist-close{position:absolute;top:10px;right:12px;background:none;border:0;color:#fff;font-size:18px;cursor:pointer;opacity:.8;}
  .lc-asist-body{flex:1;overflow-y:auto;padding:12px 14px;background:#F5F7FB;}
  .lc-msg{margin-bottom:10px;font-size:13.5px;line-height:1.45;}
  .lc-msg.user{text-align:right;}
  .lc-msg.user span{background:#1A4A9C;color:#fff;border-radius:12px 12px 2px 12px;padding:8px 12px;display:inline-block;max-width:85%;text-align:left;}
  .lc-msg.bot span{background:#fff;color:#1D1D1F;border-radius:12px 12px 12px 2px;padding:8px 12px;display:inline-block;max-width:90%;box-shadow:0 1px 3px rgba(0,0,0,.08);}
  .lc-msg.sys span{background:transparent;color:#6B7280;font-size:12px;display:block;}
  .lc-faq{display:flex;flex-wrap:wrap;gap:6px;padding:0 14px 10px;background:#F5F7FB;}
  .lc-faq button{font-size:11.5px;background:#EBF2FC;color:#1A4A9C;border:1px solid #d7e4f7;border-radius:999px;
    padding:5px 10px;cursor:pointer;}
  .lc-faq button:hover{background:#dce9fa;}
  .lc-asist-foot{display:flex;gap:8px;padding:10px 12px;border-top:1px solid #eee;background:#fff;}
  .lc-asist-foot textarea{flex:1;resize:none;border:1px solid #ddd;border-radius:10px;padding:8px 10px;
    font:13px/1.3 inherit;height:38px;max-height:90px;}
  .lc-asist-foot button{background:#0F2A5F;color:#fff;border:0;border-radius:10px;padding:0 14px;cursor:pointer;font-weight:600;}
  .lc-asist-foot button:disabled{opacity:.5;cursor:default;}
  `;
  const styleTag = document.createElement("style");
  styleTag.textContent = css;
  document.head.appendChild(styleTag);

  // ---- DOM ----
  const btn = document.createElement("button");
  btn.className = "lc-asist-btn";
  btn.innerHTML = "✦ Pregúntale a Luz Cívica";

  const panel = document.createElement("div");
  panel.className = "lc-asist-panel";
  panel.innerHTML = `
    <div class="lc-asist-head" style="position:relative;">
      <button class="lc-asist-close" aria-label="Cerrar">×</button>
      <b>Asistente Luz Cívica</b>
      <div class="lc-ctx" id="lc-ctx-line">Sin comuna seleccionada</div>
    </div>
    <div class="lc-asist-body" id="lc-body"></div>
    <div class="lc-faq" id="lc-faq"></div>
    <div class="lc-asist-foot">
      <textarea id="lc-input" placeholder="Escribe tu pregunta sobre estos datos…"></textarea>
      <button id="lc-send">Enviar</button>
    </div>
  `;

  document.body.appendChild(btn);
  document.body.appendChild(panel);

  const body = panel.querySelector("#lc-body");
  const faqBox = panel.querySelector("#lc-faq");
  const ctxLine = panel.querySelector("#lc-ctx-line");
  const input = panel.querySelector("#lc-input");
  const sendBtn = panel.querySelector("#lc-send");

  FAQ.forEach((q) => {
    const b = document.createElement("button");
    b.textContent = q.texto;
    b.onclick = () =>
      enviar(q.texto, { incluirHistorial: !!q.incluirHistorial, incluirRanking: !!q.incluirRanking });
    faqBox.appendChild(b);
  });

  function addMsg(texto, tipo) {
    const div = document.createElement("div");
    div.className = "lc-msg " + tipo;
    const span = document.createElement("span");
    span.textContent = texto;
    div.appendChild(span);
    body.appendChild(div);
    body.scrollTop = body.scrollHeight;
    return span;
  }

  function refrescarContexto() {
    const c = contextoActual();
    ctxLine.textContent = c.comuna
      ? `Viendo ${c.temaLabel} · ${c.nombre} · ${c.anio || "—"}`
      : `Viendo ${c.temaLabel}`;
    return c;
  }

  let abierto = false;
  let iniciado = false;

  function toggle() {
    abierto = !abierto;
    panel.classList.toggle("open", abierto);
    if (abierto) {
      refrescarContexto();
      if (!iniciado) {
        iniciado = true;
        addMsg(
          "Puedo explicarte los datos de esta comuna, o comparar entre todas las comunas (ej. \"qué comuna tiene mayor dotación\", \"qué alcalde gana más\"). No invento cifras: si algo no está disponible, te lo digo. Solo veo los datos de la página en la que estás — si buscas algo de otro tema (ej. Remuneraciones estando en Educación), prueba abrir esa página específica. Verifica siempre las fuentes oficiales para decisiones importantes.",
          "sys"
        );
      }
    }
  }
  btn.onclick = toggle;
  panel.querySelector(".lc-asist-close").onclick = toggle;

  async function enviar(preguntaForzada, opts) {
    const pregunta = (preguntaForzada || input.value || "").trim();
    if (!pregunta) return;
    const incluirHistorial = !!(opts && opts.incluirHistorial);
    const incluirRanking = !!(opts && opts.incluirRanking) || PATRON_COMPARATIVA.test(pregunta);

    if (!CFG.endpoint) {
      addMsg(pregunta, "user");
      addMsg(
        "El asistente todavía no tiene backend configurado (falta desplegar el Cloudflare Worker y setear LUZ_ASISTENTE_CONFIG.endpoint). Mientras tanto revisa el glosario de indicadores de la página.",
          "sys"
      );
      input.value = "";
      return;
    }

    if (usosHoy() >= CFG.limiteDiario) {
      addMsg(pregunta, "user");
      addMsg(
        `Llegaste al límite de ${CFG.limiteDiario} preguntas por hoy. Vuelve mañana o revisa las fuentes oficiales (SINIM / Contraloría) citadas en cada indicador.`,
        "sys"
      );
      input.value = "";
      return;
    }

    const ctx = refrescarContexto();
    addMsg(pregunta, "user");
    input.value = "";
    sendBtn.disabled = true;
    const pending = addMsg("Pensando…", "bot");

    const historial = incluirHistorial ? historialComuna(ctx.comuna) : null;
    const ranking = incluirRanking ? rankingComparativo(ctx.anio, ctx.datos, pregunta) : null;

    try {
      const resp = await fetch(CFG.endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pregunta,
          comuna: ctx.comuna,
          nombreComuna: ctx.nombre,
          anio: ctx.anio,
          tema: ctx.tema,
          temaLabel: ctx.temaLabel,
          datos: ctx.datos,
          historial: historial,
          ranking: ranking,
        }),
      });
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      const data = await resp.json();
      pending.textContent = data.respuesta || "No obtuve respuesta. Intenta de nuevo.";
      registrarUso();
    } catch (err) {
      pending.textContent =
        "No pude conectar con el asistente en este momento. Intenta más tarde.";
    } finally {
      sendBtn.disabled = false;
    }
  }

  sendBtn.onclick = () => enviar();
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      enviar();
    }
  });
})();
