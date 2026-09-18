Pasta reservada para Netlify Functions.

Está vazia de propósito: o dashboard não usa funções serverless, só a Edge Function de
senha em `netlify/edge-functions/auth.js`.

Ela existe porque o `netlify.toml` aponta `[functions] directory` para cá. Esse apontamento
evita que o Netlify tente empacotar a pasta `functions/` da raiz, que é do Cloudflare Pages
(formato Workers) e não compila como Netlify Function.
