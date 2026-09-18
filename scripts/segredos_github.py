#!/usr/bin/env python3
"""
Monta o arquivo SEGREDOS-GITHUB.txt com tudo que precisa ser cadastrado em
GitHub → Settings → Secrets and variables → Actions, já com os valores prontos para copiar.

Lê dos arquivos locais (todos fora do git):
    .env.meta     META_ACCESS_TOKEN
    .env.google   GOOGLE_ADS_DEVELOPER_TOKEN, GOOGLE_ADS_CLIENT_ID, GOOGLE_ADS_CLIENT_SECRET,
                  GOOGLE_ADS_REFRESH_TOKEN, GOOGLE_ADS_LOGIN_CUSTOMER_ID (opcional)
    .netlify/state.json   siteId (NETLIFY_SITE_ID)

Uso:
    python scripts/segredos_github.py

O arquivo gerado também está no .gitignore. Rode de novo sempre que um valor mudar
(por exemplo, depois de gerar o refresh token do Google).
"""

from __future__ import annotations

import io
import json
import os
import sys

SAIDA = "SEGREDOS-GITHUB.txt"


def ler_env(caminho: str) -> dict:
    out: dict = {}
    if not os.path.exists(caminho):
        return out
    for linha in io.open(caminho, encoding="utf-8"):
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        k, v = linha.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def site_id() -> str:
    try:
        return json.load(open(os.path.join(".netlify", "state.json"), encoding="utf-8")).get("siteId", "")
    except Exception:
        return ""


def main() -> int:
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(raiz)

    meta = ler_env(".env.meta")
    goog = ler_env(".env.google")

    itens = [
        # (nome no GitHub, valor, de onde vem / o que fazer se estiver vazio)
        ("NETLIFY_AUTH_TOKEN", "", "Netlify → foto do perfil → User settings → Applications → Personal access tokens → New access token. Copie o token gerado."),
        ("NETLIFY_SITE_ID", site_id(), "ID do site no Netlify (Site configuration → Site details)."),
        ("META_ADS_TOKEN", meta.get("META_ACCESS_TOKEN", ""), "Token de usuário do sistema do Meta (.env.meta)."),
        ("GOOGLE_ADS_DEVELOPER_TOKEN", goog.get("GOOGLE_ADS_DEVELOPER_TOKEN", ""), "Token de desenvolvedor do MCC (.env.google)."),
        ("GOOGLE_ADS_CLIENT_ID", goog.get("GOOGLE_ADS_CLIENT_ID", ""), "Client ID do OAuth (.env.google)."),
        ("GOOGLE_ADS_CLIENT_SECRET", goog.get("GOOGLE_ADS_CLIENT_SECRET", ""), "Client secret do OAuth (.env.google)."),
        ("GOOGLE_ADS_REFRESH_TOKEN", goog.get("GOOGLE_ADS_REFRESH_TOKEN", ""), "Gerado por: python scripts/google_oauth.py (precisa autorizar no navegador)."),
        ("GOOGLE_ADS_LOGIN_CUSTOMER_ID", goog.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID", ""), "Opcional. ID do MCC só com dígitos; o coletor descobre sozinho se ficar vazio."),
    ]

    prontos = [i for i in itens if i[1]]
    faltando = [i for i in itens if not i[1] and i[0] != "GOOGLE_ADS_LOGIN_CUSTOMER_ID"]

    linhas = [
        "SEGREDOS PARA O GITHUB — Nohotel dashboard",
        "Onde cadastrar: repositório → Settings → Secrets and variables → Actions → New repository secret",
        "Arquivo local, fora do git. Não compartilhe.",
        "",
        "=" * 78,
        "PRONTOS PARA COPIAR (nome exato do secret = valor)",
        "=" * 78,
    ]
    for nome, valor, _ in prontos:
        linhas += [f"{nome}", f"{valor}", ""]
    linhas += ["=" * 78, "AINDA FALTAM", "=" * 78]
    if faltando:
        for nome, _, dica in faltando:
            linhas += [f"{nome}", f"  → {dica}", ""]
    else:
        linhas += ["Nenhum. Cadastre os de cima e rode Actions → Atualizar dashboard → Run workflow.", ""]
    linhas += [
        "=" * 78,
        "NÃO PRECISAM ESTAR NO GITHUB (se estiverem, pode apagar ou deixar)",
        "=" * 78,
        "DASHBOARD_PASSWORD, SESSION_SECRET, SESSION_HOURS → ficam no Netlify (já cadastrados).",
        "CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID → só para o caminho alternativo (Cloudflare Pages).",
        "  O robô usa o Netlify sempre que NETLIFY_AUTH_TOKEN existir.",
        "",
    ]
    io.open(SAIDA, "w", encoding="utf-8", newline="\n").write("\n".join(linhas))
    print(f"{SAIDA} gerado: {len(prontos)} valor(es) prontos, {len(faltando)} faltando"
          + (": " + ", ".join(n for n, _, _ in faltando) if faltando else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
