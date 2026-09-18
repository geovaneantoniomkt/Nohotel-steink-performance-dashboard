/**
 * Camada de proteção do dashboard — Netlify Edge Functions (Deno).
 *
 * Porte do functions/_middleware.js (Cloudflare Pages). Mesma lógica:
 * - Exige senha (DASHBOARD_PASSWORD) para qualquer rota, inclusive /data/*.json.
 * - Sessão em cookie assinado com HMAC-SHA256 (SESSION_SECRET), HttpOnly + Secure + SameSite=Strict.
 * - Comparação de senha em tempo constante; limite de tentativas por IP; atraso em falhas.
 * - Cabeçalhos de segurança (CSP estrita, HSTS, no-sniff, no-referrer, sem indexação, sem cache de dados).
 *
 * Variáveis obrigatórias (Netlify > Site configuration > Environment variables):
 *   DASHBOARD_PASSWORD  senha de acesso (use uma senha longa)
 *   SESSION_SECRET      string aleatória (>= 16 caracteres) para assinar as sessões
 * Opcional:
 *   SESSION_HOURS       duração da sessão em horas (padrão 12)
 */

const COOKIE = "nh_sess";
const PUBLIC_PATHS = new Set(["/login.css", "/favicon.svg", "/logo.jpg", "/robots.txt"]);
const MAX_FAILS = 5;            // tentativas antes do bloqueio
const LOCK_MS = 15 * 60 * 1000; // 15 minutos
const enc = new TextEncoder();

// memória por isolate — melhor esforço, igual ao Cloudflare
const attempts = new Map();

function envVar(name) {
  try {
    if (typeof Netlify !== "undefined" && Netlify.env) return Netlify.env.get(name);
  } catch { /* ignore */ }
  try {
    return Deno.env.get(name);
  } catch {
    return undefined;
  }
}

/* ------------------------------------------------------------------ crypto */

function b64url(bytes) {
  let s = "";
  for (const b of new Uint8Array(bytes)) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function b64urlDecode(str) {
  const pad = "=".repeat((4 - (str.length % 4)) % 4);
  const bin = atob(str.replace(/-/g, "+").replace(/_/g, "/") + pad);
  return new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)));
}
async function hmac(secret, data) {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return b64url(await crypto.subtle.sign("HMAC", key, enc.encode(data)));
}
async function sha256(data) {
  return new Uint8Array(await crypto.subtle.digest("SHA-256", enc.encode(data)));
}
/** Comparação em tempo constante (compara hashes de tamanho fixo). */
async function safeEqual(a, b) {
  const [ha, hb] = await Promise.all([sha256(String(a)), sha256(String(b))]);
  let diff = 0;
  for (let i = 0; i < ha.length; i++) diff |= ha[i] ^ hb[i];
  return diff === 0;
}

/* ----------------------------------------------------------------- session */

async function createSession(secret, hours) {
  const now = Date.now();
  const payload = b64url(enc.encode(JSON.stringify({ iat: now, exp: now + hours * 3600 * 1000, v: 1 })));
  const sig = await hmac(secret, payload);
  return `${payload}.${sig}`;
}
async function verifySession(secret, token) {
  if (!token || typeof token !== "string" || token.length > 512) return false;
  const [payload, sig] = token.split(".");
  if (!payload || !sig) return false;
  const expected = await hmac(secret, payload);
  if (!(await safeEqual(sig, expected))) return false;
  try {
    const data = JSON.parse(b64urlDecode(payload));
    return typeof data.exp === "number" && data.exp > Date.now();
  } catch {
    return false;
  }
}
function parseCookies(header) {
  const out = {};
  for (const part of (header || "").split(";")) {
    const i = part.indexOf("=");
    if (i > 0) out[part.slice(0, i).trim()] = part.slice(i + 1).trim();
  }
  return out;
}
function sessionCookie(value, maxAgeSec) {
  return `${COOKIE}=${value}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${maxAgeSec}`;
}

/* ----------------------------------------------------------------- headers */

const CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self'",
  "img-src 'self' https: data:",
  "font-src 'self'",
  "connect-src 'self'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
  "upgrade-insecure-requests",
].join("; ");

function withSecurityHeaders(res, { noStore = false } = {}) {
  const h = new Headers(res.headers);
  h.set("Content-Security-Policy", CSP);
  h.set("Strict-Transport-Security", "max-age=31536000; includeSubDomains");
  h.set("X-Content-Type-Options", "nosniff");
  h.set("X-Frame-Options", "DENY");
  h.set("Referrer-Policy", "no-referrer");
  h.set("X-Robots-Tag", "noindex, nofollow, noarchive");
  h.set("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()");
  h.set("Cross-Origin-Opener-Policy", "same-origin");
  h.set("Cross-Origin-Resource-Policy", "same-origin");
  // dados/HTML nunca ficam em cache; demais estáticos sempre revalidam
  h.set("Cache-Control", noStore ? "no-store, max-age=0" : "no-cache");
  h.delete("Netlify-Vary");
  return new Response(res.body, { status: res.status, statusText: res.statusText, headers: h });
}

/* -------------------------------------------------------------- login page */

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function loginPage({ error = "", next = "/" } = {}, status = 200) {
  const html = `<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Acesso restrito · Nohotel</title>
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/login.css">
</head>
<body>
<main class="login">
  <form method="post" action="/login" autocomplete="off">
    <img class="logo" src="/logo.jpg" alt="Nohotel" width="72" height="72">
    <p class="brand">Nohotel · Steink Performance</p>
    <h1>Dashboard de performance</h1>
    <p class="sub">Acesso restrito à equipe Nohotel e Steink Performance.</p>
    ${error ? `<p class="error" role="alert">${escapeHtml(error)}</p>` : ""}
    <label for="password">Senha de acesso</label>
    <input id="password" name="password" type="password" required autofocus autocomplete="current-password" maxlength="200">
    <input type="hidden" name="next" value="${escapeHtml(next)}">
    <button type="submit">Entrar</button>
    <p class="foot">Sessão expira automaticamente. Não compartilhe a senha.</p>
  </form>
</main>
</body>
</html>`;
  return withSecurityHeaders(
    new Response(html, { status, headers: { "Content-Type": "text/html; charset=utf-8" } }),
    { noStore: true },
  );
}

function redirect(location, extraHeaders = {}) {
  const h = new Headers({ Location: location, "Cache-Control": "no-store" });
  for (const [k, v] of Object.entries(extraHeaders)) h.append(k, v);
  return withSecurityHeaders(new Response(null, { status: 303, headers: h }), { noStore: true });
}

function safeNext(raw) {
  // só aceita caminhos relativos do próprio site (evita open redirect)
  if (typeof raw !== "string" || !raw.startsWith("/") || raw.startsWith("//") || raw.includes("\\") || /[\x00-\x20\x7f]/.test(raw)) return "/";
  if (raw.startsWith("/login") || raw.startsWith("/logout")) return "/";
  return raw.slice(0, 300);
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/* -------------------------------------------------------------- handler */

export default async function handler(request, context) {
  const url = new URL(request.url);
  const path = url.pathname;

  const password = envVar("DASHBOARD_PASSWORD");
  const secret = envVar("SESSION_SECRET");
  const hours = Math.max(1, Math.min(24 * 7, Number(envVar("SESSION_HOURS")) || 12));

  if (!password || !secret || String(secret).length < 16) {
    return withSecurityHeaders(
      new Response("Dashboard não configurado: defina DASHBOARD_PASSWORD e SESSION_SECRET (>= 16 caracteres) nas variáveis de ambiente do Netlify.", {
        status: 503,
        headers: { "Content-Type": "text/plain; charset=utf-8" },
      }),
      { noStore: true },
    );
  }

  // arquivos públicos (css da tela de login, favicon, logo, robots)
  if (PUBLIC_PATHS.has(path)) {
    return withSecurityHeaders(await context.next());
  }

  if (path === "/logout") {
    return redirect("/login", { "Set-Cookie": sessionCookie("", 0) });
  }

  const cookies = parseCookies(request.headers.get("cookie"));
  const authed = await verifySession(secret, cookies[COOKIE]);

  if (path === "/login") {
    if (request.method === "POST") {
      // proteção CSRF: navegadores modernos enviam Sec-Fetch-Site; senão, Origin/Referer devem ser do próprio site
      const sfs = (request.headers.get("sec-fetch-site") || "").toLowerCase();
      if (sfs) {
        if (sfs === "cross-site") return loginPage({ error: "Requisição inválida." }, 403);
      } else {
        const origin = request.headers.get("origin") || request.headers.get("referer") || "";
        const host = request.headers.get("host") || url.host;
        if (origin) {
          try {
            const oh = new URL(origin).host;
            if (oh !== host && oh !== url.host) return loginPage({ error: "Requisição inválida." }, 403);
          } catch {
            return loginPage({ error: "Requisição inválida." }, 403);
          }
        }
      }
      const ip = context?.ip || request.headers.get("x-nf-client-connection-ip") || request.headers.get("x-forwarded-for") || "unknown";
      const rec = attempts.get(ip);
      if (rec && rec.until > Date.now()) {
        return loginPage({ error: "Muitas tentativas. Aguarde 15 minutos e tente novamente." }, 429);
      }
      let form;
      try {
        form = await request.formData();
      } catch {
        return loginPage({ error: "Requisição inválida." }, 400);
      }
      const typed = String(form.get("password") || "").slice(0, 200);
      const nextPath = safeNext(form.get("next"));

      if (typed && (await safeEqual(typed, password))) {
        attempts.delete(ip);
        const token = await createSession(secret, hours);
        return redirect(nextPath, { "Set-Cookie": sessionCookie(token, hours * 3600) });
      }

      const count = (rec ? rec.count : 0) + 1;
      attempts.set(ip, { count, until: count >= MAX_FAILS ? Date.now() + LOCK_MS : 0 });
      await sleep(400 + Math.floor(Math.random() * 400));
      return loginPage({ error: "Senha incorreta.", next: nextPath }, 401);
    }
    if (authed) return redirect("/");
    return loginPage({ next: safeNext(url.searchParams.get("next")) });
  }

  if (!authed) {
    if (path.startsWith("/data/") || path.startsWith("/api/")) {
      return withSecurityHeaders(
        new Response(JSON.stringify({ error: "não autenticado" }), { status: 401, headers: { "Content-Type": "application/json" } }),
        { noStore: true },
      );
    }
    const nextParam = path === "/" ? "" : `?next=${encodeURIComponent(path)}`;
    return redirect(`/login${nextParam}`);
  }

  const res = await context.next();
  const isData = path.startsWith("/data/") || path.endsWith(".json") || path === "/" || path.endsWith(".html");
  return withSecurityHeaders(res, { noStore: isData });
}

export const config = { path: "/*" };
