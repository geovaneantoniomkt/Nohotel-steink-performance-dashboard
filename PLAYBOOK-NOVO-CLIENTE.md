# Playbook — dashboard de performance para um cliente novo

Como montar, do zero, o mesmo dashboard que está no ar para a Nohotel, para qualquer outro
cliente da Steink Performance. Este documento é o passo a passo completo: APIs usadas, ordem
das etapas, e **todos os erros que aparecem no caminho com a solução de cada um**.

O projeto da Nohotel serve de modelo. Ele está em
[geovaneantoniomkt/Nohotel-steink-performance-dashboard](https://github.com/geovaneantoniomkt/Nohotel-steink-performance-dashboard).

---

## 1. O que é

Um site estático protegido por senha, que mostra Meta Ads, Google Ads e orgânico (Instagram +
Facebook) de um cliente. Ele se atualiza sozinho todo dia às 7h da manhã.

```
GitHub Actions (todo dia 07:00 BRT)                        Netlify
┌────────────────────────────────┐  netlify deploy   ┌──────────────────────────────────┐
│ scripts/fetch_meta.py          │ ────────────────► │ netlify/edge-functions/auth.js   │ ← senha
│   META_ACCESS_TOKEN (secret)   │  public/ + data/  │ public/index.html, app.js        │
│   → public/data/meta.json      │ (nunca vai p/ git)│ public/data/*.json               │ ← só com sessão
│   → public/data/organic.json   │                   └──────────────────────────────────┘
│ scripts/fetch_google.py        │
│   GOOGLE_ADS_* (secrets)       │
│   → public/data/google.json    │
└────────────────────────────────┘
```

Três decisões que explicam o resto:

- **Os dados não ficam no git.** O repositório é público; `public/data/` está no `.gitignore`.
  Os JSONs são gerados na hora do deploy e enviados direto para o Netlify.
- **Por isso quem publica é o GitHub Actions**, com a CLI do Netlify. Nunca conecte o site ao
  repositório pela interface do Netlify: ele publicaria sem a pasta `data/` e o dashboard ficaria vazio.
- **A senha roda numa Edge Function**, que intercepta *todas* as rotas antes de qualquer arquivo,
  inclusive os JSONs. O plano grátis do Netlify já inclui. A proteção nativa do Netlify é paga.

Custo total: **zero**. GitHub Actions, Netlify e as APIs do Meta e do Google são gratuitos nesse volume.

---

## 2. Antes de começar, reúna

| Item | Onde consegue | Observação |
|---|---|---|
| Nome, segmento e praça do cliente | Com você | Aparecem no cabeçalho do dashboard |
| Logo quadrada | Com o cliente | Vira `public/logo.jpg`, 150px ou mais |
| ID da conta de anúncios do Meta | Gerenciador de Anúncios | Só dígitos, sem `act_` |
| ID do Business Manager | Configurações do Business | |
| ID da página do Facebook e do Instagram | Descobertos por API, ver §5 | |
| ID do pixel | Eventos do pixel | Opcional, aparece nas legendas |
| ID da conta Google Ads | Google Ads, canto superior | Formato `123-456-7890` |
| Token do Meta (Usuário do Sistema) | Já existe, reaproveitado | **Precisa ganhar acesso à conta nova**, ver §6 |
| Credenciais da Google Ads API | Já existem, reaproveitadas | Developer token, client ID, client secret |
| Conta no Netlify e no GitHub | Já existem | |

O token do Meta e as credenciais do Google são **os mesmos para todos os clientes**. O que muda a
cada cliente é dar acesso a eles, e isso é o passo que mais trava (§6 e §7).

---

## 3. Criar o projeto (um comando)

Dentro da pasta do projeto modelo:

```bash
python scripts/novo_cliente.py --nome "InVet Center" --slug invet-center --destino "../InVet Center" --repo https://github.com/geovaneantoniomkt/InVet-Center-Steink-Performance-Dashboard.git --segmento "Hospital veterinário 24h" --praca "Limeira e região (SP)" --google-customer 182-911-9223
```

O script copia só o código, nunca dados nem segredos, e troca tudo que é específico do cliente:
nome, slug, nome do cookie de sessão, chave do `localStorage`, IDs, nome do projeto no Netlify.
Também gera a senha e a chave de sessão em `SENHA-LOCAL.txt`, `.env` e `.dev.vars`, e escreve um
`COMECAR-AQUI.md` com o que ainda falta.

Os IDs que você ainda não tiver podem ficar em branco e ser preenchidos depois em
`public/config.json`.

Em seguida:

```bash
cd "../InVet Center"
npm install
npm test          # 32 verificações da camada de senha, precisa passar antes de qualquer coisa
```

---

## 4. Token do Meta

Um **Usuário do Sistema** no Business Manager, com token sem expiração e estes escopos:

```
ads_read · business_management · pages_read_engagement · pages_show_list
read_insights · instagram_basic · instagram_manage_insights
```

Guarde em `.env.meta` na raiz do projeto (o `.gitignore` já cobre):

```
META_ACCESS_TOKEN=EAAxxxxx...
```

### ⚠️ Armadilha 1 — o token não enxerga a conta do cliente novo

Este é o erro mais comum e o que mais confunde, porque o token "funciona" em outros clientes.

Um token de Usuário do Sistema só acessa as contas às quais **aquele usuário** recebeu acesso.
Criar o dashboard não dá acesso nenhum. Confirme antes de perder tempo:

```bash
python - <<'PY'
import json, urllib.request, urllib.parse, io
T = dict(l.strip().split("=",1) for l in io.open(".env.meta", encoding="utf-8") if "=" in l)["META_ACCESS_TOKEN"]
url = "https://graph.facebook.com/v23.0/me/adaccounts?" + urllib.parse.urlencode(
    {"fields": "id,name", "limit": 200, "access_token": T})
for c in json.load(urllib.request.urlopen(url))["data"]:
    print(c["id"].replace("act_", ""), "|", c["name"])
PY
```

Se a conta do cliente não aparecer na lista: Business Manager → Usuários → **Usuários do Sistema** →
selecione o usuário → **Adicionar ativos** → marque a conta de anúncios, a página e o Instagram do
cliente, com permissão de leitura. Rode o comando de novo até a conta aparecer.

---

## 5. Descobrir a página e o Instagram do cliente

Com o token já enxergando a conta:

```bash
python - <<'PY'
import json, urllib.request, urllib.parse, io
T = dict(l.strip().split("=",1) for l in io.open(".env.meta", encoding="utf-8") if "=" in l)["META_ACCESS_TOKEN"]
CONTA = "SUBSTITUA_PELO_ID_DA_CONTA"
def api(path, **p):
    p["access_token"] = T
    return json.load(urllib.request.urlopen(
        f"https://graph.facebook.com/v23.0/{path}?" + urllib.parse.urlencode(p), timeout=60))
for pg in api(f"act_{CONTA}/promote_pages", fields="id,name")["data"]:
    d = api(pg["id"], fields="id,name,followers_count,instagram_business_account{id,username}")
    ig = d.get("instagram_business_account") or {}
    print("página:", d["id"], d["name"], "| seguidores:", d.get("followers_count"))
    print("instagram:", ig.get("id"), "@" + str(ig.get("username")))
PY
```

Preencha `public/config.json` com os IDs, o segmento e a praça.

---

## 6. Google Ads — a parte que mais trava

São **duas** chaves obrigatórias, e não existe caminho com só uma:

1. **Developer token do MCC** — identifica o aplicativo. Você já tem.
2. **Refresh token OAuth** — diz a quais contas o aplicativo pode acessar. Nasce de um clique
   em *Permitir*, logado com a conta Google dona do MCC.

Guarde em `.env.google` (fora do git):

```
GOOGLE_ADS_DEVELOPER_TOKEN=...
GOOGLE_ADS_CLIENT_ID=...apps.googleusercontent.com
GOOGLE_ADS_CLIENT_SECRET=GOCSPX-...
GOOGLE_ADS_CUSTOMER_ID=182-911-9223
```

Gere o refresh token (vale para **todos** os clientes, faça uma vez só):

```bash
python scripts/google_oauth.py
```

### ⚠️ Armadilha 2 — `redirect_uri_mismatch`

Se o cliente OAuth no Google Cloud for do tipo **Aplicativo da Web**, ele só aceita voltar para
endereços cadastrados. Duas saídas:

- Adicionar `http://localhost:8765/` em *URIs de redirecionamento autorizados*, **ou**
- Usar um endereço que já esteja lá:

```bash
python scripts/google_oauth.py --redirect-uri https://developers.google.com/oauthplayground
# aprove, copie a URL inteira da página que abrir, e rode:
python scripts/google_oauth.py --redirect-uri https://developers.google.com/oauthplayground --code "<URL colada>"
```

### ⚠️ Armadilha 3 — `Google Ads API has not been used in project ... or it is disabled`

A API precisa estar ligada **no projeto do Google Cloud**, não no Google Ads. Abra
`https://console.cloud.google.com/apis/api/googleads.googleapis.com/overview?project=<ID_DO_PROJETO>`
e clique em **Ativar**. O ID do projeto são os dígitos iniciais do client ID.

### ⚠️ Armadilha 4 — `The Google Cloud project is only approved for use with test accounts`

**Mudou em 2025 e é o que mais engana:** o nível de acesso deixou de ser do MCC e passou a ser do
projeto do Google Cloud. O Google Ads até avisa isso na tela da API Center. Um projeto recém-criado
começa em **Teste**, e conta de teste não vê conta real.

Na mesma página da armadilha 3 → cartão **Níveis de acesso** → **Gerenciar** → abra
**Fazer upgrade do nível de acesso** → **Inscrever-se para receber acesso** (Explorer).

O Explorer é liberado na hora e dá 2.880 operações por dia em contas reais. O dashboard usa umas 12
por dia. **Não precisa do Basic**, que exige verificação de marca e análise de dias.

### ⚠️ Armadilha 5 — `User doesn't have permission to access customer`

Conta de cliente gerenciada por MCC exige o cabeçalho `login-customer-id` com o ID do MCC.
O coletor descobre isso sozinho: ele chama `listAccessibleCustomers`, percorre cada MCC acessível
procurando a conta do cliente e fixa o cabeçalho. Se mesmo assim falhar, a conta não está vinculada
ao MCC — vincule no Google Ads.

Confirme com:

```bash
python scripts/fetch_google.py   # tem que terminar com "google.json: N campanhas, ..."
```

---

## 7. Coletar e definir as metas

```bash
python scripts/fetch_meta.py     # gera meta.json e organic.json
python scripts/fetch_google.py   # gera google.json
```

### ⚠️ Armadilha 6 — metas inventadas deixam o dashboard inútil

Se você chutar "R$ 150 por reserva" sem olhar o histórico, tudo fica vermelho e o cliente ignora o
painel. Tire as metas do histórico da própria conta. Para o Google:

```bash
python - <<'PY'
import json, collections, statistics
g = json.load(open("public/data/google.json", encoding="utf-8"))
m = collections.defaultdict(lambda: [0.0, 0.0])
for r in g["daily"]:
    m[r["date"][:7]][0] += r["cost"]; m[r["date"][:7]][1] += r["conversions"]
cpas = [c/v for c, v in m.values() if v]
for k in sorted(m):
    c, v = m[k]; print(f"  {k}: R$ {c:8.2f} | conv {v:5.1f} | {('R$ %.2f' % (c/v)) if v else '—'}")
print("mediana:", round(statistics.median(cpas), 2), "| melhor mês:", round(min(cpas), 2))
PY
```

Use a **mediana** como meta, não a média nem o melhor mês. No Meta, o mesmo raciocínio com
`meta.json`, separando campanhas de conversão das de topo de funil.

Preencha `public/config.json` em `targets` e escreva em `_comentario_metas` de onde saiu cada número.

---

## 8. Publicar no Netlify

```bash
npm run bundle    # cria deploy-netlify/ com ~15 arquivos
```

Netlify → **Add new site → Deploy manually** → arraste a pasta **`deploy-netlify`**.
Depois renomeie o site em *Site configuration → Site details* e copie o **Site ID**.

### ⚠️ Armadilha 7 — arrastar a pasta errada publica o dashboard SEM senha

| O que arrastar | O que acontece |
|---|---|
| `public/` sozinha | Site sobe **sem a Edge Function**, ou seja, **sem senha**, com os dados do cliente abertos na internet |
| A pasta do projeto inteira | Sobe `node_modules` (mais de 1 GB) e os arquivos locais de segredo |
| **`deploy-netlify`** | Só o `netlify.toml`, a camada de senha e a `public/` com os dados |

### ⚠️ Armadilha 8 — `hugo: command not found`

Se o `netlify.toml` tiver `command = ""`, o Netlify trata como "não informado", tenta adivinhar o
framework e, como a pasta publicada se chama `public`, conclui que é um site Hugo. O modelo já vem
com um comando explícito que não faz nada. Se o erro aparecer, apague também o campo *Build command*
nas configurações do site pela interface, que sobrescreve o arquivo.

### Senha

Em *Site configuration → Environment variables*, escopo **All scopes**:

| Variável | Valor |
|---|---|
| `DASHBOARD_PASSWORD` | a senha da equipe, 16+ caracteres |
| `SESSION_SECRET` | string aleatória longa |
| `SESSION_HOURS` | opcional, padrão 12 |

Os dois primeiros já foram gerados em `SENHA-LOCAL.txt`.

### ⚠️ Armadilha 9 — variável marcada como "secret" não chega na Edge Function

Se você marcar **Contains secret values** (o cadeado), o Netlify não entrega o valor para Edge
Functions e o site responde **503 em tudo**. Deixe desmarcado.

### ⚠️ Armadilha 10 — variável nova só vale no próximo deploy

Depois de cadastrar ou editar, **publique de novo**. O 503 do modelo é autoexplicativo: ele diz qual
variável não chegou e quantas a função enxerga.

Se preferir resolver tudo por linha de comando, sem cliques:

```bash
npx netlify login
npx netlify link --id <SITE_ID>
npx netlify env:set DASHBOARD_PASSWORD "..."
npx netlify env:set SESSION_SECRET "..."
npx netlify deploy --prod --dir public
```

---

## 9. Automatizar a atualização diária

```bash
python scripts/segredos_github.py   # monta SEGREDOS-GITHUB.txt com os valores prontos
```

Cadastre em **Settings → Secrets and variables → Actions**:

| Secret | De onde vem |
|---|---|
| `NETLIFY_AUTH_TOKEN` | Netlify → User settings → Applications → Personal access tokens |
| `NETLIFY_SITE_ID` | Site ID do passo 8 |
| `META_ADS_TOKEN` | `.env.meta` |
| `GOOGLE_ADS_DEVELOPER_TOKEN` | `.env.google` |
| `GOOGLE_ADS_CLIENT_ID` | `.env.google` |
| `GOOGLE_ADS_CLIENT_SECRET` | `.env.google` |
| `GOOGLE_ADS_REFRESH_TOKEN` | `.env.google` |

`DASHBOARD_PASSWORD` e `SESSION_SECRET` **não** vão para o GitHub: eles vivem no Netlify.

Rode em **Actions → Atualizar dashboard → Run workflow**. O workflow roda os testes da camada de
senha antes de publicar e, depois de publicar, confere na URL que os dados respondem 401 sem sessão.
Se a proteção não subir, o job falha em vez de deixar os dados abertos.

---

## 10. APIs usadas

### Meta Marketing API — `graph.facebook.com/v23.0`

| Endpoint | Para quê |
|---|---|
| `act_<id>` | nome, moeda, fuso, saldo, limite de gasto |
| `act_<id>/campaigns`, `/adsets`, `/ads` | estrutura, status, orçamentos, criativos |
| `act_<id>/insights` `level=ad` `time_increment=1` | série diária por anúncio |
| `act_<id>/insights` com `date_preset` | totais exatos (alcance não soma entre dias) |
| `act_<id>/insights` com `breakdowns` | idade/gênero, região, posicionamento |
| `<page_id>/insights`, `/published_posts` | orgânico do Facebook |
| `<ig_id>/insights`, `/media` | orgânico do Instagram |

O que conta como "resultado" sai de `adset.optimization_goal` + `promoted_object.custom_event_type`:
compra vira reserva, carrinho vira adição, WhatsApp vira conversa.

### Google Ads API — `googleads.googleapis.com/v23`

Tudo via `POST customers/<id>/googleAds:searchStream` com consultas GAQL. Recursos usados:
`customer`, `campaign`, `ad_group`, `keyword_view`, `search_term_view`, `ad_group_ad`,
`geographic_view`, `customer_client`.

Cabeçalhos: `Authorization: Bearer <access_token>`, `developer-token`, `login-customer-id`.

### ⚠️ Armadilha 11 — campos que a API aposenta

A v23 removeu `campaign.start_date`, `campaign.end_date` e `metrics.video_views`. Uma consulta com
campo desconhecido falha inteira com `INVALID_ARGUMENT`. O coletor lê o nome do campo rejeitado na
mensagem de erro, remove do `SELECT` e repete — o resto dos dados continua vindo. Se você adicionar
campos novos, esse mecanismo já cobre.

### ⚠️ Armadilha 12 — métricas de Página do Facebook descontinuadas

`page_impressions`, `page_impressions_unique`, `page_fans`, `page_daily_follows_total` e
`page_fan_adds` não existem mais. As que ainda funcionam: `page_post_engagements`,
`page_daily_follows_unique`, `page_follows`, `page_views_total`, `page_total_actions`,
`page_video_views`. O coletor tenta uma lista de candidatas e usa a primeira que responder.

### ⚠️ Armadilha 13 — série diária do Instagram vem zerada

As métricas `profile_views`, `accounts_engaged` e `views` com `metric_type=total_value` usam janela
meio-aberta. Com `since=d&until=d` a API devolve vazio. O certo é `since=d&until=d+1`.
Além disso, a janela dessas métricas não pode passar de 30 dias.

---

## 11. Estrutura do projeto

```
public/                    site estático: index.html, app.js, styles.css, config.json, logo.jpg
public/data/               JSONs gerados — ignorados pelo git
netlify/edge-functions/    auth.js — senha, sessão e cabeçalhos de segurança
netlify.toml               configuração do Netlify
scripts/fetch_meta.py      coletor do Meta Ads + orgânico
scripts/fetch_google.py    coletor do Google Ads
scripts/google_oauth.py    gera o refresh token (uma vez só, serve para todos os clientes)
scripts/bundle_netlify.py  monta deploy-netlify/ para o deploy manual
scripts/segredos_github.py monta a lista de secrets para colar no GitHub
scripts/novo_cliente.py    cria o projeto de um cliente novo a partir deste
tests/auth.test.mjs        32 verificações da camada de senha
.github/workflows/         update-dashboard.yml — coleta + testes + deploy diário
functions/, wrangler.toml  mesma proteção em formato Cloudflare Pages (caminho alternativo)
```

Os coletores usam **só a biblioteca padrão do Python**. O front-end não tem nenhuma dependência
externa, nem CDN. Isso é proposital: menos coisa para quebrar e CSP estrita.

### Segurança da camada de senha

Sessão em cookie assinado com HMAC-SHA256, `HttpOnly` + `Secure` + `SameSite=Strict`, 12 h.
Comparação de senha em tempo constante, bloqueio de 15 min após 5 erros por IP, proteção CSRF,
sem *open redirect*. CSP estrita sem `unsafe-inline`, HSTS, `X-Frame-Options: DENY`, `noindex`.
Sem as variáveis de senha, responde 503 em vez de servir o site aberto.

`npm test` roda as 32 verificações contra as duas implementações (Netlify e Cloudflare), que
precisam se comportar igual.

---

## 12. Outros tropeços que não são de API

- **Push negado no GitHub (403)**: a máquina pode estar autenticada com outra conta. Ou adicione
  essa conta como colaboradora do repositório, ou troque a credencial no Gerenciador de Credenciais
  do Windows, procurando por `git:https://github.com`.
- **Limite de gasto da conta do Meta**: `spend_cap` perto do `amount_spent` faz a entrega parar sem
  aviso. O dashboard mostra isso como alerta na visão executiva. Vale conferir na primeira coleta.
- **Acentos no console do Windows**: o terminal usa cp1252 e quebra com `→` ou emoji. Use
  `PYTHONIOENCODING=utf-8` ou evite esses caracteres nos `print`.

---

## 13. Checklist final

- [ ] `npm test` passa (32 de 32)
- [ ] Logo trocada em `public/logo.jpg`
- [ ] `public/config.json` com os IDs reais e as metas tiradas do histórico
- [ ] `python scripts/fetch_meta.py` sem avisos
- [ ] `python scripts/fetch_google.py` termina com `configured: true`
- [ ] Site no ar: raiz redireciona, `/data/meta.json` responde 401 sem sessão
- [ ] Login com a senha de produção abre o painel com dados
- [ ] Secrets cadastrados no GitHub e workflow rodado com sucesso
- [ ] Repositório sem nenhum segredo: `git ls-files | grep -Ei "\.env|dev\.vars|SENHA|data/.*json"` não retorna nada
