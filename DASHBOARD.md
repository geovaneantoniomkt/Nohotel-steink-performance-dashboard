# Configuração do dashboard — Nohotel

```
GitHub Actions (3x/dia: 06h, 12h, 18h BRT)                 Netlify e/ou Cloudflare Pages
┌────────────────────────────────┐  netlify deploy   ┌──────────────────────────────────┐
│ scripts/fetch_meta.py          │ ────────────────► │ netlify/edge-functions/auth.js   │ ← senha + cabeçalhos
│   META_ACCESS_TOKEN (secret)   │  public/ + data/  │ public/index.html, app.js        │
│   → public/data/meta.json      │ (nunca vai p/ git)│ public/data/*.json               │ ← só com sessão válida
│   → public/data/organic.json   │                   └──────────────────────────────────┘
│ scripts/fetch_google.py        │
│   GOOGLE_ADS_* (secrets)       │
│   → public/data/google.json    │
└────────────────────────────────┘
```

**Por que o deploy não sai do próprio Netlify conectado ao Git:** os dados não estão no repositório.
Eles são gerados na hora pelos coletores e enviados junto com o site. Por isso quem publica é o
GitHub Actions, usando a CLI do Netlify. Não conecte o site ao repositório pela interface do Netlify
— se fizer isso, ele vai publicar o site sem a pasta `data/` e o dashboard aparece vazio.

Princípios de segurança:

- **Os tokens nunca saem do GitHub Actions.** Existem só como *secrets*; o site publicado não contém
  token nenhum e o navegador nunca fala com a API do Meta ou do Google.
- **Os dados nunca entram no git.** `public/data/` está no `.gitignore` — importante porque o
  repositório é público.
- **Tudo atrás de senha**, inclusive os JSONs: a Edge Function intercepta todas as rotas antes de
  qualquer arquivo estático.
- Sessão em cookie assinado (HMAC-SHA256), `HttpOnly`, `Secure`, `SameSite=Strict`, expira em 12 h.
- Comparação de senha em tempo constante, bloqueio de 15 min após 5 erros por IP, proteção CSRF
  (`Sec-Fetch-Site`/`Origin`), sem *open redirect* no `next`.
- CSP estrita (`script-src 'self'`, sem inline), HSTS, `X-Frame-Options: DENY`, `nosniff`,
  `Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex`, `Cache-Control: no-store` nos dados.
- Nenhuma dependência externa no front-end (sem CDN).

---

## 1. Criar o site no Netlify

Gere primeiro o pacote de deploy:

```bash
npm run bundle          # cria ./deploy-netlify (~2 MB, 15 arquivos)
```

1. Entrar no Netlify → **Add new site → Deploy manually** e arrastar a pasta **`deploy-netlify`**.
   **Não** use "Import from Git".
2. Renomear o site em **Site configuration → Site details → Change site name** para
   `nohotel-dashboard` (a URL fica `https://nohotel-dashboard.netlify.app`).
3. Copiar o **Site ID** em *Site configuration → Site details → Site information*.

### Por que uma pasta separada, e não `public/` nem a pasta do projeto

| O que arrastar | O que acontece |
|---|---|
| `public/` sozinha | O site sobe **sem a Edge Function**, ou seja, **sem senha**, com os dados do cliente abertos na internet. Nunca faça isso. |
| A pasta do projeto inteira | Sobe `node_modules` (mais de 1 GB) e os arquivos locais de segredo (`.env`, `.env.google`, `SENHA-LOCAL.txt`). |
| `deploy-netlify` | Só o `netlify.toml`, a Edge Function de senha e a `public/` com os dados. É o que você quer. |

Se subir antes de cadastrar as variáveis do passo 2, o site responde **503** em todas as rotas — de
propósito. É seguro: nada é servido sem senha em nenhum momento.

## 2. Senha do dashboard (variáveis de ambiente do Netlify)

Em **Site configuration → Environment variables → Add a variable**, escopo *All scopes* /
*All deploy contexts*:

| Variável | Valor |
|---|---|
| `DASHBOARD_PASSWORD` | a senha que a equipe vai digitar (use 16+ caracteres) |
| `SESSION_SECRET` | string aleatória longa — assina o cookie de sessão |
| `SESSION_HOURS` | opcional, duração da sessão em horas (padrão 12) |

Para gerar um `SESSION_SECRET`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Trocar o `SESSION_SECRET` derruba todas as sessões abertas. Trocar a senha vale no deploy seguinte
(as variáveis são lidas a cada requisição, então o efeito é praticamente imediato).

> Sem essas duas variáveis a Edge Function devolve **503** em tudo, de propósito: é melhor o site sair
> do ar do que ficar aberto sem senha.

## 3. Segredos do GitHub

Em **Settings → Secrets and variables → Actions → New repository secret**:

| Nome | O que é |
|---|---|
| `NETLIFY_AUTH_TOKEN` | Netlify → foto do perfil → **User settings → Applications → Personal access tokens → New access token** |
| `NETLIFY_SITE_ID` | o Site ID copiado no passo 1 |
| `META_ADS_TOKEN` | token de usuário do sistema do Business Nohotel (`647998705890215`) |
| `GOOGLE_ADS_DEVELOPER_TOKEN` | token de desenvolvedor do MCC |
| `GOOGLE_ADS_CLIENT_ID` | client ID do OAuth (Google Cloud → Credenciais) |
| `GOOGLE_ADS_CLIENT_SECRET` | client secret do OAuth |
| `GOOGLE_ADS_REFRESH_TOKEN` | gerado por `python scripts/google_oauth.py` |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | ID da conta administradora (MCC), só dígitos — opcional, o coletor descobre sozinho |

Variáveis opcionais (aba *Variables*): `META_API_VERSION` (padrão `v23.0`),
`GOOGLE_ADS_CUSTOMER_ID` (padrão `781-346-4105`), `META_SINCE` / `GOOGLE_SINCE` (padrão `2025-04-01`).

O workflow é `.github/workflows/update-dashboard.yml`. Ele roda **3x por dia (06:17, 12:17 e 18:17
Brasília)**, manualmente em **Actions → Atualizar dashboard → Run workflow**, e a cada push na `main`
que altere `public/`, `netlify/`, `functions/` ou `scripts/`.

Ele publica em **todo destino configurado**: Netlify (com `NETLIFY_AUTH_TOKEN` + `NETLIFY_SITE_ID`) e
Cloudflare Pages (com `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID`). Um endereço cujo destino não
tem os secrets **não é atualizado** — foi o que deixou o `.netlify.app` parado no deploy manual de
18/09/2026. Depois de cada deploy, `scripts/check_live.sh` confere que o site continua atrás de senha.

As imagens dos criativos e posts são baixadas por `scripts/cache_images.py` e publicadas em
`/data/img/` (os links do Meta expiram e nem sempre abrem fora do Facebook). Se a última coleta tiver
mais de 30 horas, o dashboard mostra uma faixa vermelha de **dados desatualizados**.

O repositório é público, e o GitHub desliga workflows agendados de repositórios públicos após 60 dias
sem commits. O passo "Manter o agendamento ativo" reativa o workflow pela API a cada execução para a
coleta não parar em silêncio.

Se o Google Ads ainda não estiver configurado, o passo dele falha de forma controlada
(`continue-on-error`), grava `google.json` com `configured: false` e o dashboard mostra o passo a
passo de integração no lugar dos dados. O resto continua funcionando.

## 4. Token do Meta

Usuário do Sistema no Business Manager da Nohotel (`647998705890215`), com acesso à conta de
anúncios, à Página e ao Instagram, e token sem expiração com os escopos:

`ads_read` · `business_management` · `pages_read_engagement` · `pages_show_list` · `read_insights` ·
`instagram_basic` · `instagram_manage_insights`

Sem os escopos de Página/Instagram o coletor continua funcionando para o Meta Ads e registra o motivo
em "Avisos da última coleta" dentro do dashboard.

## 5. Google Ads

1. **MCC**: vincular a conta `781-346-4105` ao MCC da Steink e pegar o **token de desenvolvedor**
   em Ferramentas → Configuração da API.
2. **Google Cloud**: criar projeto, ativar a **Google Ads API** e criar credencial OAuth do tipo
   **App para computador** (se for do tipo "Aplicativo da Web", adicionar
   `http://localhost:8765/` nos URIs de redirecionamento autorizados).
3. **Refresh token**: preencher `.env.google` (fora do git) e rodar:

   ```bash
   python scripts/google_oauth.py
   ```

   O script abre um servidor local, mostra o link de autorização, e ao aprovar salva o
   `GOOGLE_ADS_REFRESH_TOKEN` no `.env.google`.
4. **Conferir**: `python scripts/fetch_google.py` — deve gerar `public/data/google.json` com
   `configured: true`.
5. **Publicar**: cadastrar os quatro segredos `GOOGLE_ADS_*` no GitHub e rodar o workflow.

Na conta do Google Ads, marcar como **conversão principal** só o que é reserva/contato de verdade —
o custo por conversão do dashboard usa `conversions` (principais) e mostra `all_conversions` como
referência.

## 6. Camadas extras recomendadas

- **Domínio próprio**: Netlify → Domain management → Add domain (ex. `dash.nohotel.com.br`). O HTTPS
  é automático.
- **Netlify Identity / SSO** (opcional, pago nos planos maiores): permite login por e-mail individual
  em vez de senha compartilhada, com revogação por pessoa.
- Trocar `DASHBOARD_PASSWORD` sempre que alguém sair do projeto.
- O bloqueio por tentativas é por *isolate* da edge — é uma primeira barreira, não um rate limiter
  global. Para força bruta séria, combine com um domínio atrás de Cloudflare ou com o Netlify
  Firewall Traffic Rules.

## 7. Rodar localmente

```bash
# 1) coletar (o .env.google é lido automaticamente pelo fetch_google.py)
set META_ACCESS_TOKEN=EAAB...      # PowerShell: $env:META_ACCESS_TOKEN="EAAB..."
python scripts/fetch_meta.py
python scripts/fetch_google.py

# 2) subir o site com a mesma camada de senha da produção
npm run dev                        # http://localhost:8790
```

`netlify dev` lê a senha do arquivo `.env` na raiz (`DASHBOARD_PASSWORD`, `SESSION_SECRET`), que está
no `.gitignore`.

## 8. Arquivos locais que nunca vão para o git

| Arquivo | Conteúdo |
|---|---|
| `.env` | senha e chave de sessão usadas pelo `netlify dev` |
| `.dev.vars` | mesmas variáveis, para o `wrangler` (Cloudflare) |
| `.env.google` | credenciais da Google Ads API |
| `SENHA-LOCAL.txt` | lembrete da senha local de teste |
| `public/data/*.json` | dados coletados |

## 9. Se o build falhar com "hugo: command not found"

Significa que o `netlify.toml` não chegou ao Netlify, ou que o comando de build do site (em
*Site configuration → Build & deploy → Build settings*) está sobrescrevendo o do arquivo. Sem um
comando explícito, o Netlify tenta adivinhar o framework e, como a pasta publicada se chama
`public`, ele conclui que é um site Hugo.

O `netlify.toml` do repositório já traz um comando explícito que não faz nada:

```toml
[build]
  command = "echo 'Sem etapa de build: public/ ja vem pronto do coletor.'"
```

Se o erro persistir, apague o campo *Build command* nas configurações do site pela interface, para
o valor do arquivo voltar a valer.

## 10. Alternativa: Cloudflare Pages

O repositório também traz a mesma proteção em `functions/_middleware.js` (formato Cloudflare Pages
Functions) e o `wrangler.toml`. O workflow publica no Cloudflare sempre que os segredos dele
existirem (em paralelo ao Netlify, se este também estiver configurado). Para usar esse caminho, cadastre `CLOUDFLARE_API_TOKEN` e `CLOUDFLARE_ACCOUNT_ID` no
GitHub e as variáveis `DASHBOARD_PASSWORD` / `SESSION_SECRET` no painel do Cloudflare Pages. Os
comandos locais ficam em `npm run dev:cloudflare` e `npm run deploy:cloudflare`.

## 11. Checklist de segurança executado

- [x] `/data/*.json` sem sessão → 401; `/` sem sessão → redireciona para `/login`
- [x] Senha errada → 401 com atraso; 5 erros → bloqueio de 15 min por IP
- [x] `next` malicioso (`//evil.com`, `https://evil.com`, `/\evil.com`) → redireciona para `/`
- [x] POST com `Sec-Fetch-Site: cross-site` ou `Origin` de outro host → 403
- [x] Cookie `HttpOnly; Secure; SameSite=Strict`, assinado
- [x] CSP sem `unsafe-inline`; nenhum script/CSS externo; imagens só via `https:`
- [x] Tokens nunca aparecem em log (URLs e mensagens de erro são higienizadas nos dois coletores)
- [x] Dados, `.env`, `.dev.vars` e `.env.google` no `.gitignore`
- [x] Sem as variáveis de senha, a Edge Function devolve 503 em vez de servir o site aberto
