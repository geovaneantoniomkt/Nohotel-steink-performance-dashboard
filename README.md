# Nohotel × Steink Performance — Dashboard de performance

Dashboard protegido por senha com os dados de **Meta Ads**, **Google Ads** e **orgânico** (Instagram +
Facebook) da Nohotel. Atualiza sozinho todo dia às 7h da manhã e publica no **Netlify**.

| Item | Valor |
|---|---|
| Conta Meta Ads | `812845936220210` — "Nohotel" (Business `647998705890215`) |
| Conta Google Ads | `781-346-4105` |
| Página do Facebook | `207987622557413` — "Hotéis Nohotel" |
| Instagram | [@hoteisnohotel](https://instagram.com/hoteisnohotel) (`17841402216050279`) |
| Pixel | `405737827091951` |
| Praça | Nova Odessa, Americana, Limeira, Campinas e região (SP) |

## Seções

| Seção | O que mostra |
|---|---|
| Visão executiva | Verba do mês por plataforma, ritmo e projeção de gasto, KPIs com variação vs. período anterior, gráficos diários, histórico mês a mês desde abr/2025, melhores criativos, dinheiro parado e **alertas priorizados por dinheiro em jogo** |
| Meta Ads | Campanhas com status, orçamento, resultado, custo por resultado vs. meta e ação recomendada; conjuntos por campanha; idade/gênero, região e posicionamento (30 dias) |
| Google Ads | Campanhas, grupos de anúncios, palavras-chave com índice de qualidade, termos de pesquisa (com sugestão de negativação), anúncios, conversões por ação, dispositivos e localidades |
| Criativos | Cards por anúncio com miniatura, gasto, resultados, custo, CTR, CPM e link para o anúncio publicado |
| Orgânico | Instagram (seguidores, alcance, visitas ao perfil, contas engajadas, publicações) e Facebook (seguidores, engajamento, visitas à página) |
| Legendas | O que significa cada métrica, status e regra de qualidade |

## Acesso

O site inteiro fica atrás de senha, inclusive os arquivos de dados. Quem cuida disso é uma **Edge
Function do Netlify** (`netlify/edge-functions/auth.js`): ela intercepta todas as rotas, mostra a tela
de login e só deixa passar quem tem um cookie de sessão assinado. A senha fica na variável de
ambiente `DASHBOARD_PASSWORD` do Netlify — não existe nenhuma senha dentro do código.

## O que conta como resultado

O dashboard lê o objetivo de cada conjunto de anúncios e o evento otimizado no pixel, e usa isso para
decidir o que é "resultado" em cada campanha:

| Campanha otimiza | Resultado exibido | Meta padrão |
|---|---|---|
| Compra (pixel `PURCHASE`) | Reservas / compras | R$ 400 |
| Carrinho (pixel `ADD_TO_CART`) | Adições ao carrinho | R$ 120 |
| Conversa no WhatsApp | Conversas iniciadas | R$ 12 |
| Visita ao perfil do Instagram | Visitas ao perfil | R$ 1,50 |
| Alcance / reconhecimento | Alcance | CPM até R$ 10 |
| Google Ads | Conversões principais | R$ 60 |

As metas saíram do histórico da própria conta entre abr/2025 e set/2026: mediana de **R$ 481 por
reserva** (melhor mês R$ 253), **R$ 153 por carrinho** (melhor R$ 85) e **R$ 7,50 por conversa** no
período em que as campanhas de WhatsApp rodaram. São editáveis no menu lateral do dashboard (ficam
salvas só no navegador de quem editou) e o padrão fica em `public/config.json`.

## Estrutura

```
public/                    site estático (index.html, app.js, styles.css, config.json, logo.jpg)
public/data/               JSONs gerados pelos coletores — ignorados pelo git
netlify/edge-functions/    auth.js — senha, sessão e cabeçalhos de segurança
netlify.toml               configuração do Netlify
scripts/                   fetch_meta.py, fetch_google.py e google_oauth.py
.github/workflows/         update-dashboard.yml (coleta + deploy diário)
functions/, wrangler.toml  mesma proteção em formato Cloudflare Pages (caminho alternativo)
```

Configuração completa, segredos e checklist de segurança em [`DASHBOARD.md`](DASHBOARD.md).

## Rodar local

```bash
python scripts/fetch_meta.py     # precisa de META_ACCESS_TOKEN
python scripts/fetch_google.py   # lê .env.google (fora do git)
npm run dev                      # http://localhost:8790
```

> Este repositório é público. Nenhum token, senha ou dado do cliente entra no git: os JSONs de dados
> são gerados na hora do deploy e enviados direto para o Netlify.
