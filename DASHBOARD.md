# Configuração do dashboard — Nohotel

```
GitHub Actions (todo dia 07:00 BRT)                  Cloudflare Pages
┌────────────────────────────────┐  wrangler deploy  ┌──────────────────────────────┐
│ scripts/fetch_meta.py          │ ────────────────► │ functions/_middleware.js     │ ← senha + cabeçalhos
│   META_ACCESS_TOKEN (secret)   │  public/ + data/  │ public/index.html, app.js    │
│   → public/data/meta.json      │  (nunca vai p/ git)│ public/data/*.json          │ ← só com sessão válida
│   → public/data/organic.json   │                   └──────────────────────────────┘
│ scripts/fetch_google.py        │
│   GOOGLE_ADS_* (secrets)       │
│   → public/data/google.json    │
└────────────────────────────────┘
```

Princípios de segurança:

- **Os tokens nunca saem do GitHub Actions.** Existem só como *secrets*; o site publicado não contém
  token nenhum e o navegador nunca fala com a API do Meta ou do Google.
- **Os dados nunca entram no git.** `public/data/` está no `.gitignore` — importante porque o
  repositório é público.
- **Tudo atrás de senha**, inclusive os JSONs: o middleware roda antes de qualquer arquivo estático.
- Sessão em cookie assinado (HMAC-SHA256), `HttpOnly`, `Secure`, `SameSite=Strict`, expira em 12 h.
- Comparação de senha em tempo constante, bloqueio de 15 min após 5 erros por IP, proteção CSRF
  (`Sec-Fetch-Site`/`Origin`), sem *open redirect* no `next`.
- CSP estrita (`script-src 'self'`, sem inline), HSTS, `X-Frame-Options: DENY`, `nosniff`,
  `Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex`, `Cache-Control: no-store` nos dados.
- Nenhuma dependência externa no front-end (sem CDN).

---

## 1. Segredos do GitHub

Em **Settings → Secrets and variables → Actions → New repository secret**:

| Nome | O que é |
|---|---|
| `META_ADS_TOKEN` (ou `META_ACCESS_TOKEN`) | Token de usuário do sistema do Business Nohotel (`647998705890215`) |
| `CLOUDFLARE_API_TOKEN` | Token da API do Cloudflare com permissão **Cloudflare Pages: Edit** |
| `CLOUDFLARE_ACCOUNT_ID` | ID da conta Cloudflare (barra lateral do painel) |
| `GOOGLE_ADS_DEVELOPER_TOKEN` | Token de desenvolvedor do MCC |
| `GOOGLE_ADS_CLIENT_ID` | Client ID do OAuth (Google Cloud → Credenciais) |
| `GOOGLE_ADS_CLIENT_SECRET` | Client secret do OAuth |
| `GOOGLE_ADS_REFRESH_TOKEN` | Gerado por `python scripts/google_oauth.py` |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | ID da conta administradora (MCC), só dígitos — opcional, o coletor descobre sozinho |

Variáveis opcionais (aba *Variables*): `CF_PAGES_PROJECT` (padrão `nohotel-dashboard`),
`META_API_VERSION` (padrão `v23.0`), `GOOGLE_ADS_CUSTOMER_ID` (padrão `781-346-4105`),
`META_SINCE` / `GOOGLE_SINCE` (padrão `2025-04-01`).

O workflow é `.github/workflows/update-dashboard.yml`. Ele roda todo dia às **10:00 UTC (07:00
Brasília)**, manualmente em **Actions → Atualizar dashboard → Run workflow**, e a cada push na `main`
que altere `public/`, `functions/` ou `scripts/`.

Se o Google Ads ainda não estiver configurado, o passo dele falha de forma controlada
(`continue-on-error`), grava `google.json` com `configured: false` e o dashboard mostra o passo a
passo de integração no lugar dos dados. O resto do dashboard continua funcionando normalmente.

## 2. Token do Meta

Usuário do Sistema no Business Manager da Nohotel (`647998705890215`), com acesso à conta de
anúncios, à Página e ao Instagram, e token sem expiração com os escopos:

`ads_read` · `business_management` · `pages_read_engagement` · `pages_show_list` · `read_insights` ·
`instagram_basic` · `instagram_manage_insights`

Sem os escopos de Página/Instagram o coletor continua funcionando para o Meta Ads e registra o motivo
em "Avisos da última coleta" dentro do dashboard.

## 3. Google Ads

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

## 4. Cloudflare Pages

1. Painel Cloudflare → **Workers & Pages → Create → Pages → Upload assets**.
   Nome do projeto: `nohotel-dashboard`. Pode subir qualquer arquivo só para criar o projeto — o
   Actions substitui no primeiro deploy.
2. **Settings → Environment variables → Production**, adicionar como **Secret**:
   - `DASHBOARD_PASSWORD` — a senha de acesso (16+ caracteres).
   - `SESSION_SECRET` — string aleatória longa. Trocar essa chave derruba todas as sessões.
   - `SESSION_HOURS` (opcional) — duração da sessão em horas (padrão 12).
3. Criar o token da API em **My Profile → API Tokens → Create Token → "Edit Cloudflare Workers"**
   e guardar em `CLOUDFLARE_API_TOKEN` no GitHub.
4. Rodar o workflow. A URL fica em `https://nohotel-dashboard.pages.dev`.

### Camadas extras recomendadas (gratuitas)

- **Rate limit no WAF**: Security → WAF → Rate limiting rules → `URI Path equals /login` e método
  `POST`, máx. 10 requisições / 1 min por IP → *Block*.
- **Cloudflare Access (Zero Trust)** como segunda camada: cada pessoa entra com o próprio e-mail
  (OTP) e o acesso pode ser revogado individualmente.
- Trocar `DASHBOARD_PASSWORD` sempre que alguém sair do projeto.

## 5. Rodar localmente

```bash
# 1) coletar (o .env.google é lido automaticamente pelo fetch_google.py)
set META_ACCESS_TOKEN=EAAB...      # PowerShell: $env:META_ACCESS_TOKEN="EAAB..."
python scripts/fetch_meta.py
python scripts/fetch_google.py

# 2) subir o site com a camada de senha (.dev.vars, fora do git)
npm run dev                        # http://localhost:8790
```

`.dev.vars` precisa de `DASHBOARD_PASSWORD` e `SESSION_SECRET` (mínimo 16 caracteres).

## 6. Arquivos locais que nunca vão para o git

| Arquivo | Conteúdo |
|---|---|
| `.dev.vars` | senha e chave de sessão do ambiente local |
| `.env.google` | credenciais da Google Ads API |
| `SENHA-LOCAL.txt` | lembrete da senha local de teste |
| `public/data/*.json` | dados coletados |

## 7. Checklist de segurança executado

- [x] `/data/*.json` sem sessão → 401; `/` sem sessão → redireciona para `/login`
- [x] Senha errada → 401 com atraso; 5 erros → bloqueio de 15 min por IP
- [x] `next` malicioso (`//evil.com`, `https://evil.com`, `/\evil.com`) → redireciona para `/`
- [x] POST com `Sec-Fetch-Site: cross-site` ou `Origin` de outro host → 403
- [x] Cookie `HttpOnly; Secure; SameSite=Strict`, assinado
- [x] CSP sem `unsafe-inline`; nenhum script/CSS externo; imagens só via `https:`
- [x] Tokens nunca aparecem em log (URLs e mensagens de erro são higienizadas nos dois coletores)
- [x] Dados, `.dev.vars` e `.env.google` no `.gitignore`
