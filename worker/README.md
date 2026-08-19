# Asistente Luz Cívica — despliegue del backend (gratis)

Este Worker recibe la pregunta del usuario + los datos que ya está viendo en
pantalla, y le pide a un modelo de **Workers AI** (cuota diaria gratuita en
el plan gratuito de Cloudflare) que la responda usando *solo* esos datos.

## 1. Requisitos

- Una cuenta gratuita de Cloudflare: https://dash.cloudflare.com/sign-up
- Node.js instalado (para usar `wrangler`, la CLI de Cloudflare)

## 2. Instalar wrangler y autenticarte

```bash
npm install -g wrangler
wrangler login
```

Esto abre el navegador para autorizar tu cuenta de Cloudflare.

## 3. Editar el dominio permitido (CORS)

Abre `asistente-worker.js` y reemplaza `ORIGENES_PERMITIDOS` con el dominio
real donde publiques el sitio (por ejemplo tu GitHub Pages):

```js
const ORIGENES_PERMITIDOS = [
  "https://tu-usuario.github.io",
  "http://localhost:8756",
];
```

## 4. Desplegar

Desde la carpeta `worker/`:

```bash
wrangler deploy
```

Al terminar, wrangler imprime una URL del tipo:

```
https://luz-civica-asistente.tu-cuenta.workers.dev
```

Esa es tu `endpoint`. El endpoint real que usará el frontend es esa URL
+ `/asistente` — es decir:

```
https://luz-civica-asistente.tu-cuenta.workers.dev/asistente
```

(El Worker responde en cualquier ruta, así que también funciona sin el
sufijo si prefieres simplificar — pero usa la misma URL consistentemente
en el frontend.)

## 5. Conectar el frontend

En cada página HTML que incluya `scripts/luz_asistente.js`, define el
endpoint antes de cargarlo:

```html
<script>
  window.LUZ_ASISTENTE_CONFIG = {
    endpoint: "https://luz-civica-asistente.tu-cuenta.workers.dev/asistente",
    tema: "educacion",
    temaLabel: "Educación",
  };
</script>
<script src="scripts/luz_asistente.js"></script>
```

## 6. Sobre el costo

- Workers AI en el plan gratuito de Cloudflare incluye una cuota diaria de
  "neuronas" gratis (suficiente para varios cientos de respuestas cortas
  por día, según el modelo). Al agotarse, las requests fallan con un error
  — **no se te cobra automáticamente**, salvo que tú mismo actives el plan
  de pago de Workers AI.
- El widget del frontend ya limita a 8 preguntas por visitante por día
  (guardado en `localStorage`) como buena práctica, pero eso es solo del
  lado del navegador — no es una protección de seguridad real, es para
  repartir el uso.
- Si más adelante quieres subir de calidad, puedes cambiar `MODELO` en
  `asistente-worker.js` por otro modelo de Workers AI, o apuntar a la API
  de Anthropic/OpenAI (ya no gratis, pero muy barato para este volumen).

## 7. Probar en local antes de desplegar

```bash
wrangler dev
```

Te da una URL local (`http://localhost:8787/asistente`) que puedes usar
temporalmente en `LUZ_ASISTENTE_CONFIG.endpoint` mientras pruebas.
