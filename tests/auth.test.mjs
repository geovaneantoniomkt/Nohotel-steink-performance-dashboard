/**
 * Testes da camada de senha do dashboard.
 *
 * Roda as duas implementações — a Edge Function do Netlify e o middleware do Cloudflare
 * Pages — contra a mesma bateria, porque elas precisam se comportar igual.
 *
 *   npm test
 *
 * Não precisa de rede nem de CLI: as APIs usadas (crypto.subtle, btoa/atob,
 * Request/Response/Headers) são padrão da Web e existem no Node 20+, no Deno do Netlify
 * e no runtime do Cloudflare.
 */

import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

const PASSWORD = "senha-de-teste-bem-longa-123";
const SECRET = "segredo-de-sessao-com-mais-de-16-chars";
const SITE = "https://nohotel-dashboard.netlify.app";

const env = { DASHBOARD_PASSWORD: PASSWORD, SESSION_SECRET: SECRET, SESSION_HOURS: "12" };

/** Cada alvo expõe a mesma interface: chama(request, {ip}) -> Response. */
const targets = [
  {
    name: "Netlify Edge Function (netlify/edge-functions/auth.js)",
    load: async () => {
      globalThis.Netlify = { env: { get: (k) => env[k] } };
      const mod = await import(pathToFileURL(resolve("netlify/edge-functions/auth.js")).href + "?t=" + Date.now());
      return (request, { ip, onServe }) => mod.default(request, { ip, next: onServe });
    },
  },
  {
    name: "Cloudflare Pages middleware (functions/_middleware.js)",
    load: async () => {
      const mod = await import(pathToFileURL(resolve("functions/_middleware.js")).href + "?t=" + Date.now());
      return (request, { ip, onServe }) => {
        const req = new Request(request, { headers: new Headers(request.headers) });
        req.headers.set("cf-connecting-ip", ip);
        return mod.onRequest({ request: req, env, next: onServe });
      };
    },
  },
];

let failures = 0;

for (const target of targets) {
  // cada alvo recebe um módulo novo, para o bloqueio por IP não vazar entre eles
  for (const k of Object.keys(env)) env[k] = { DASHBOARD_PASSWORD: PASSWORD, SESSION_SECRET: SECRET, SESSION_HOURS: "12" }[k];
  const call = await target.load();

  let served = 0;
  const onServe = async () => {
    served++;
    return new Response("<!doctype html><title>dash</title>", {
      status: 200,
      headers: { "Content-Type": "text/html; charset=utf-8", "Netlify-Vary": "header=x" },
    });
  };
  const get = (path, headers = {}, ip = "1.2.3.4") =>
    call(new Request(SITE + path, { headers }), { ip, onServe });
  const post = (path, fields, headers = {}, ip = "1.2.3.4") =>
    call(new Request(SITE + path, {
      method: "POST",
      body: new URLSearchParams(fields),
      headers: { "Content-Type": "application/x-www-form-urlencoded", "Sec-Fetch-Site": "same-origin", ...headers },
    }), { ip, onServe });

  const results = [];
  const check = (name, cond, extra = "") => results.push({ name, ok: !!cond, extra });
  const cookieOf = (res) => ((res.headers.get("set-cookie") || "").match(/nh_sess=([^;]*)/) || [])[1] || null;

  /* --------------------------------------------------------------- sem sessão */
  let r = await get("/");
  check("GET / sem sessão redireciona para /login", r.status === 303 && r.headers.get("location") === "/login", `${r.status} -> ${r.headers.get("location")}`);

  r = await get("/data/meta.json");
  check("GET /data/meta.json sem sessão devolve 401 JSON", r.status === 401 && (r.headers.get("content-type") || "").includes("json"), `status ${r.status}`);

  r = await get("/criativos");
  check("rota interna sem sessão preserva o destino no next", r.headers.get("location") === "/login?next=%2Fcriativos", r.headers.get("location"));

  r = await get("/login");
  check("GET /login mostra a tela de senha", r.status === 200 && (await r.clone().text()).includes("Senha de acesso"), `status ${r.status}`);

  r = await get("/login.css");
  check("arquivos públicos passam sem senha (login.css)", r.status === 200 && served > 0, `status ${r.status}`);
  r = await get("/logo.jpg");
  check("logo.jpg é público (aparece na tela de login)", r.status === 200, `status ${r.status}`);

  /* ------------------------------------------------------------------ headers */
  const csp = r.headers.get("content-security-policy") || "";
  check("CSP com script-src 'self' e sem unsafe-inline", csp.includes("script-src 'self'") && !csp.includes("unsafe-inline"), csp.slice(0, 60));
  check("X-Frame-Options DENY", r.headers.get("x-frame-options") === "DENY");
  check("X-Robots-Tag noindex", (r.headers.get("x-robots-tag") || "").includes("noindex"));
  check("HSTS de 1 ano", (r.headers.get("strict-transport-security") || "").includes("max-age=31536000"));

  /* -------------------------------------------------------------------- login */
  r = await post("/login", { password: "errada", next: "/" });
  check("senha errada devolve 401", r.status === 401, `status ${r.status}`);

  r = await post("/login", { password: PASSWORD, next: "/" });
  const sess = cookieOf(r);
  check("senha certa devolve 303 com cookie de sessão", r.status === 303 && !!sess, `status ${r.status}`);
  const sc = r.headers.get("set-cookie") || "";
  check("cookie HttpOnly + Secure + SameSite=Strict", sc.includes("HttpOnly") && sc.includes("Secure") && sc.includes("SameSite=Strict"), sc);

  /* --------------------------------------------------------------- com sessão */
  const auth = { cookie: `nh_sess=${sess}` };
  r = await get("/", auth);
  check("GET / com sessão serve o dashboard", r.status === 200, `status ${r.status}`);
  check("HTML com sessão vai com no-store", (r.headers.get("cache-control") || "").includes("no-store"), r.headers.get("cache-control"));

  r = await get("/data/meta.json", auth);
  check("GET /data/meta.json com sessão passa", r.status === 200, `status ${r.status}`);

  r = await get("/login", auth);
  check("quem já tem sessão e abre /login vai para /", r.status === 303 && r.headers.get("location") === "/", r.headers.get("location"));

  r = await get("/logout", auth);
  check("logout limpa o cookie", (r.headers.get("set-cookie") || "").includes("Max-Age=0"), r.headers.get("set-cookie"));

  /* ------------------------------------------------------------ cookie forjado */
  const [payload, signature] = sess.split(".");
  r = await get("/", { cookie: `nh_sess=${payload}.assinaturaFalsa` });
  check("assinatura inválida é rejeitada", r.status === 303, `status ${r.status}`);

  const forjado = Buffer.from(JSON.stringify({ iat: Date.now(), exp: Date.now() + 9e9, v: 1 })).toString("base64url");
  r = await get("/", { cookie: `nh_sess=${forjado}.${signature}` });
  check("payload trocado invalida a sessão", r.status === 303, `status ${r.status}`);

  const expirado = Buffer.from(JSON.stringify({ iat: 1, exp: Date.now() - 1000, v: 1 })).toString("base64url");
  r = await get("/", { cookie: `nh_sess=${expirado}.${signature}` });
  check("sessão expirada é rejeitada", r.status === 303, `status ${r.status}`);

  /* ----------------------------------------------------------- open redirect */
  for (const bad of ["//evil.com", "https://evil.com", "/\\evil.com", "/login", "/logout"]) {
    const rr = await post("/login", { password: PASSWORD, next: bad });
    check(`next malicioso "${bad}" cai para /`, rr.headers.get("location") === "/", rr.headers.get("location"));
  }
  r = await post("/login", { password: PASSWORD, next: "/criativos" });
  check("next legítimo é respeitado", r.headers.get("location") === "/criativos", r.headers.get("location"));

  /* -------------------------------------------------------------------- CSRF */
  r = await post("/login", { password: PASSWORD }, { "Sec-Fetch-Site": "cross-site" });
  check("POST cross-site é bloqueado (403)", r.status === 403, `status ${r.status}`);

  /* ------------------------------------------------------- bloqueio por IP */
  const ip = "9.9.9.9";
  for (let i = 0; i < 5; i++) await post("/login", { password: "errada" }, {}, ip);
  r = await post("/login", { password: PASSWORD }, {}, ip);
  check("5 erros bloqueiam o IP por 15 min, mesmo com a senha certa", r.status === 429, `status ${r.status}`);
  r = await post("/login", { password: PASSWORD }, {}, "8.8.8.8");
  check("o bloqueio não afeta outro IP", r.status === 303, `status ${r.status}`);

  /* ------------------------------------------------- sem senha configurada */
  const saved = env.DASHBOARD_PASSWORD;
  env.DASHBOARD_PASSWORD = "";
  r = await get("/");
  check("sem DASHBOARD_PASSWORD o site responde 503 (não fica aberto)", r.status === 503, `status ${r.status}`);
  env.DASHBOARD_PASSWORD = saved;
  env.SESSION_SECRET = "curto";
  r = await get("/");
  check("SESSION_SECRET curto demais também dá 503", r.status === 503, `status ${r.status}`);
  env.SESSION_SECRET = SECRET;

  /* ---------------------------------------------------------------- relatório */
  const bad = results.filter((x) => !x.ok);
  failures += bad.length;
  console.log(`\n${target.name}`);
  console.log("─".repeat(target.name.length));
  for (const x of results) console.log(`${x.ok ? "  ok  " : " FALHA"}  ${x.name}${x.ok ? "" : "   [" + x.extra + "]"}`);
  console.log(`  ${results.length - bad.length}/${results.length} passaram`);
}

console.log(failures ? `\n${failures} verificação(ões) falharam` : "\nTudo certo nas duas implementações.");
process.exit(failures ? 1 : 0);
