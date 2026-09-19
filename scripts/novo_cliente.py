#!/usr/bin/env python3
"""
Cria o projeto de dashboard de um cliente novo a partir deste (que serve de modelo).

Copia só o código — nunca dados, segredos ou node_modules — e troca tudo que é específico
do cliente: nome, slug, nome do cookie de sessão, chave do localStorage, IDs das contas,
nome do projeto no Netlify e no Cloudflare.

Uso mínimo:
    python scripts/novo_cliente.py --nome "InVet Center" --slug invet-center

Uso completo (quando você já tem os IDs; todos são opcionais e podem ser preenchidos depois
em public/config.json):
    python scripts/novo_cliente.py \
        --nome "InVet Center" \
        --slug invet-center \
        --destino "C:/Users/ADMIN/Desktop/Nova pasta/InVet Center" \
        --repo https://github.com/usuario/InVet-Center-Dashboard.git \
        --segmento "Hospital veterinário 24h" \
        --praca "Limeira e região (SP)" \
        --meta-account 123456789 --meta-business 123 --meta-page 123 --meta-ig 123 \
        --pixel 123 --instagram invetcenter \
        --google-customer 182-911-9223 \
        --desde 2025-01-01

Depois de rodar, abra o COMECAR-AQUI.md que é gerado dentro da pasta nova.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import secrets
import shutil
import string
import sys

# arquivos de código que formam o modelo (nada de dados nem segredos)
TEMPLATE = [
    ".github/workflows/update-dashboard.yml",
    ".gitignore",
    ".claude/launch.json",
    "netlify.toml",
    "netlify/edge-functions/auth.js",
    "netlify/functions/README.md",
    "functions/_middleware.js",
    "wrangler.toml",
    "package.json",
    "public/app.js",
    "public/index.html",
    "public/login.css",
    "public/styles.css",
    "public/robots.txt",
    "public/favicon.svg",
    "public/logo.jpg",
    "public/data/.gitkeep",
    "scripts/fetch_meta.py",
    "scripts/fetch_google.py",
    "scripts/google_oauth.py",
    "scripts/bundle_netlify.py",
    "scripts/segredos_github.py",
    "scripts/novo_cliente.py",
    "tests/auth.test.mjs",
    "PLAYBOOK-NOVO-CLIENTE.md",
]
BINARIOS = {".jpg", ".jpeg", ".png", ".webp", ".ico", ".gif"}
# copiados como estão: falam do processo em geral e citam o projeto-modelo de propósito
SEM_SUBSTITUICAO = {"PLAYBOOK-NOVO-CLIENTE.md"}

# valores do cliente-modelo (Nohotel) que precisam virar os do cliente novo
MODELO = {
    "nome": "Nohotel",
    "nome_legal": "Hotéis Nohotel",
    "slug": "nohotel",
    "cookie": "nh_sess",
    "meta_account": "812845936220210",
    "meta_business": "647998705890215",
    "meta_page": "207987622557413",
    "meta_ig": "17841402216050279",
    "pixel": "405737827091951",
    "instagram": "hoteisnohotel",
    "google_customer": "781-346-4105",
    "desde": "2025-04-01",
}


def prefixo_cookie(slug: str) -> str:
    """invet-center -> ic_sess ; nohotel -> no_sess"""
    partes = [p for p in re.split(r"[^a-z0-9]+", slug.lower()) if p]
    if len(partes) >= 2:
        return "".join(p[0] for p in partes[:3]) + "_sess"
    return (partes[0][:2] if partes else "cl") + "_sess"


def gerar_segredos() -> tuple[str, str]:
    alfabeto = string.ascii_letters + string.digits
    senha = "".join(secrets.choice(alfabeto) for _ in range(16))
    return senha, secrets.token_urlsafe(48)


def main() -> int:
    ap = argparse.ArgumentParser(description="Cria o projeto de dashboard de um cliente novo.")
    ap.add_argument("--nome", required=True, help='Nome do cliente, ex.: "InVet Center"')
    ap.add_argument("--slug", required=True, help='Identificador em minúsculas, ex.: invet-center')
    ap.add_argument("--destino", default=None, help="Pasta a criar (padrão: ../<Nome>)")
    ap.add_argument("--repo", default="", help="URL do repositório git (origin)")
    ap.add_argument("--nome-legal", default="", help="Razão social / nome completo")
    ap.add_argument("--segmento", default="", help='ex.: "Hospital veterinário 24h"')
    ap.add_argument("--praca", default="", help='ex.: "Limeira e região (SP)"')
    ap.add_argument("--meta-account", default="", help="ID da conta de anúncios do Meta (só dígitos)")
    ap.add_argument("--meta-business", default="", help="ID do Business Manager")
    ap.add_argument("--meta-page", default="", help="ID da página do Facebook")
    ap.add_argument("--meta-ig", default="", help="ID da conta do Instagram Business")
    ap.add_argument("--pixel", default="", help="ID do pixel")
    ap.add_argument("--instagram", default="", help="@ do Instagram, sem arroba")
    ap.add_argument("--google-customer", default="", help="ID da conta Google Ads, ex.: 182-911-9223")
    ap.add_argument("--desde", default="", help="Data inicial da série (YYYY-MM-DD). Padrão: 37 meses atrás")
    ap.add_argument("--verba-meta", type=float, default=0, help="Verba mensal do Meta em R$")
    ap.add_argument("--verba-google", type=float, default=0, help="Verba mensal do Google em R$")
    args = ap.parse_args()

    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(raiz)

    slug = re.sub(r"[^a-z0-9-]+", "-", args.slug.lower()).strip("-")
    if not slug:
        print("ERRO: --slug inválido")
        return 2
    destino = os.path.abspath(args.destino or os.path.join(raiz, "..", args.nome))
    if os.path.abspath(destino) == raiz:
        print("ERRO: o destino não pode ser a própria pasta do modelo")
        return 2
    if os.path.exists(destino) and os.listdir(destino):
        print(f"ERRO: {destino} já existe e não está vazia")
        return 2

    faltando = [c for c in TEMPLATE if not os.path.exists(c)]
    if faltando:
        print("ERRO: faltam arquivos no modelo:", ", ".join(faltando))
        return 2

    novo = {
        "nome": args.nome,
        "nome_legal": args.nome_legal or args.nome,
        "slug": slug,
        "cookie": prefixo_cookie(slug),
        "meta_account": args.meta_account or "COLOQUE_O_ID_DA_CONTA",
        "meta_business": args.meta_business or "COLOQUE_O_ID_DO_BUSINESS",
        "meta_page": args.meta_page or "COLOQUE_O_ID_DA_PAGINA",
        "meta_ig": args.meta_ig or "COLOQUE_O_ID_DO_INSTAGRAM",
        "pixel": args.pixel or "COLOQUE_O_ID_DO_PIXEL",
        "instagram": args.instagram or "usuario_do_instagram",
        "google_customer": args.google_customer or "000-000-0000",
        "desde": args.desde or "2025-01-01",
    }

    # ordem importa: os IDs mais longos primeiro, para não trocar pedaço de outro
    trocas = sorted(
        [(MODELO[k], novo[k]) for k in MODELO if MODELO[k] != novo[k]],
        key=lambda p: -len(p[0]),
    )
    # nome do cliente em minúsculas também aparece (nohotel-dashboard, nohotel.targets)
    trocas += [("nohotel", slug), ("NOHOTEL", slug.upper())]

    copiados, substituicoes = 0, 0
    for rel in TEMPLATE:
        alvo = os.path.join(destino, rel)
        os.makedirs(os.path.dirname(alvo), exist_ok=True)
        if os.path.splitext(rel)[1].lower() in BINARIOS or rel in SEM_SUBSTITUICAO:
            shutil.copy2(rel, alvo)
            copiados += 1
            continue
        texto = io.open(rel, encoding="utf-8").read()
        antes = texto
        for velho, novo_valor in trocas:
            texto = texto.replace(velho, novo_valor)
        substituicoes += (antes != texto)
        io.open(alvo, "w", encoding="utf-8", newline="\n").write(texto)
        copiados += 1

    # config.json é gerado do zero, não copiado
    config = {
        "client": {
            "name": args.nome,
            "legal_name": novo["nome_legal"],
            "segment": args.segmento or "PREENCHER: segmento do cliente",
            "market": args.praca or "PREENCHER: praça / região",
            "agency": "Steink Performance",
            "logo": "/logo.jpg",
            "website": "",
        },
        "budget": {"meta_monthly": args.verba_meta, "google_monthly": args.verba_google},
        "_comentario_metas": (
            "PREENCHER depois da primeira coleta: rode os coletores e calcule a mediana do custo por "
            "resultado dos últimos 12 meses. Metas inventadas deixam o dashboard todo vermelho e sem valor."
        ),
        "targets": {
            "cost_per_purchase": 0,
            "cost_per_add_to_cart": 0,
            "cost_per_conversation": 0,
            "cost_per_profile_visit": 1.5,
            "google_cost_per_conversion": 0,
            "cpm_topo_max": 10,
            "ctr_min": 1.0,
            "frequency_max": 2.5,
            "min_spend_for_alert": 30,
        },
        "meta": {
            "ad_account_id": novo["meta_account"],
            "business_id": novo["meta_business"],
            "page_id": novo["meta_page"],
            "ig_user_id": novo["meta_ig"],
            "pixel_id": novo["pixel"],
        },
        "instagram": {"username": novo["instagram"]},
        "google_ads": {
            "enabled": True,
            "customer_id": novo["google_customer"],
            "note": f"Conta Google Ads da {args.nome}. Os dados aparecem quando as credenciais da Google Ads API estiverem cadastradas nos secrets do GitHub.",
        },
    }
    io.open(os.path.join(destino, "public/config.json"), "w", encoding="utf-8", newline="\n").write(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n")

    senha, sessao = gerar_segredos()
    senha = f"{slug}-{senha}"
    io.open(os.path.join(destino, "SENHA-LOCAL.txt"), "w", encoding="utf-8", newline="\n").write(
        f"SEGREDOS DO DASHBOARD {args.nome.upper()} - arquivo local, fora do git.\n"
        + "=" * 70 + "\n\n"
        "Cadastrar no Netlify em Site configuration > Environment variables,\n"
        "com escopo 'All scopes' e SEM marcar 'Contains secret values':\n\n"
        f"   DASHBOARD_PASSWORD={senha}\n"
        f"   SESSION_SECRET={sessao}\n"
        "   SESSION_HOURS=12\n\n"
        "Os mesmos valores servem para o ambiente local (.env e .dev.vars).\n")
    for arq in (".env", ".dev.vars"):
        io.open(os.path.join(destino, arq), "w", encoding="utf-8", newline="\n").write(
            f"DASHBOARD_PASSWORD={senha}\nSESSION_SECRET={sessao}\nSESSION_HOURS=12\n")

    pendencias = [k for k, v in novo.items() if str(v).startswith(("COLOQUE_", "000-000", "usuario_do"))]
    passo2 = ("2. **Preencher os IDs** em `public/config.json`: " + ", ".join(pendencias)
              + " — o playbook mostra como descobrir cada um.") if pendencias else \
             "2. IDs já preenchidos em `public/config.json`. Confira antes de seguir."
    if args.repo:
        bloco_git = "\n".join([
            "```bash", "git init -b main", f"git remote add origin {args.repo}",
            f'git add -A && git commit -m "Dashboard de performance {args.nome}"',
            "git push -u origin main", "```",
        ])
    else:
        bloco_git = "Crie o repositório no GitHub e rode `git init -b main` e `git remote add origin <url>`."
    io.open(os.path.join(destino, "COMECAR-AQUI.md"), "w", encoding="utf-8", newline="\n").write(f"""# {args.nome} — dashboard, por onde começar

Projeto gerado a partir do modelo em `{os.path.basename(raiz)}`. O passo a passo completo, com os
erros conhecidos e como resolver cada um, está em [`PLAYBOOK-NOVO-CLIENTE.md`](PLAYBOOK-NOVO-CLIENTE.md).

## Já está pronto

- Código do dashboard, coletores, camada de senha e testes, todos renomeados para **{args.nome}**.
- Cookie de sessão: `{novo['cookie']}` · projeto Netlify: `{slug}-dashboard`
- Senha e chave de sessão geradas em `SENHA-LOCAL.txt`, `.env` e `.dev.vars` (fora do git).

## Falta fazer, nesta ordem

1. **Trocar a logo**: substitua `public/logo.jpg` pela logo do cliente (quadrada, 150px+).
{passo2}
3. **Dar acesso ao Usuário do Sistema** do Meta na conta de anúncios, na página e no Instagram
   do cliente. Sem isso o token não enxerga a conta (erro mais comum).
4. **Coletar**: `python scripts/fetch_meta.py` e `python scripts/fetch_google.py`.
5. **Definir as metas** em `public/config.json` a partir do histórico real coletado.
6. **Publicar**: `npm run bundle` e subir a pasta `deploy-netlify` no Netlify.
7. **Automatizar**: cadastrar os segredos no GitHub (`python scripts/segredos_github.py` monta a lista).

## Comandos

```bash
npm install                    # instala netlify-cli
npm test                       # 32 verificações da camada de senha
python scripts/fetch_meta.py   # precisa de META_ACCESS_TOKEN no .env.meta
python scripts/fetch_google.py # lê .env.google
npm run bundle                 # monta deploy-netlify/ para subir
npm run dev                    # http://localhost:8790
```

## Repositório

{bloco_git}
""")

    print(f"Projeto criado em: {destino}")
    print(f"  {copiados} arquivos copiados · {substituicoes} com substituições · cookie {novo['cookie']}")
    if pendencias:
        print(f"  IDs a preencher em public/config.json: {', '.join(pendencias)}")
    print(f"\nAbra: {os.path.join(destino, 'COMECAR-AQUI.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
