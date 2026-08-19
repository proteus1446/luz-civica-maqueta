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
    },
    window.LUZ_ASISTENTE_CONFIG || {}
  );

  const FAQ = [
    "¿Por qué importa este indicador?",
    "¿Esta cifra es alta o baja?",
    "¿Cómo evolucionó esta comuna en el tiempo?",
    "Explícamelo en lenguaje simple",
  ];

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
    b.textContent = q;
    b.onclick = () => enviar(q);
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
          "Puedo explicarte los indicadores que estás viendo, usando solo los datos de esta página. No invento cifras: si algo no está disponible, te lo digo. Verifica siempre las fuentes oficiales para decisiones importantes.",
          "sys"
        );
      }
    }
  }
  btn.onclick = toggle;
  panel.querySelector(".lc-asist-close").onclick = toggle;

  async function enviar(preguntaForzada) {
    const pregunta = (preguntaForzada || input.value || "").trim();
    if (!pregunta) return;

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
