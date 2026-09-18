#!/usr/bin/env python3
"""
Monta uma pasta limpa para subir no Netlify arrastando (deploy manual).

Por que existe: arrastar a pasta do projeto inteira manda junto node_modules (mais de 1 GB) e os
arquivos locais de segredo (.env, .env.google, SENHA-LOCAL.txt). E arrastar só a public/ é pior
ainda — o site sobe SEM a Edge Function, ou seja, sem senha, com os dados do cliente abertos.

Esta pasta leva exatamente o necessário:
    netlify.toml
    netlify/edge-functions/auth.js   (a camada de senha)
    public/                          (site + dados já coletados)

Uso:
    python scripts/bundle_netlify.py            # gera ./deploy-netlify
    python scripts/bundle_netlify.py --out X    # gera em outro lugar

Depois é só arrastar a pasta gerada na tela de deploy do Netlify. Lembre de cadastrar
DASHBOARD_PASSWORD e SESSION_SECRET nas variáveis de ambiente do site — sem elas a Edge Function
responde 503 em tudo, de propósito.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys

ITENS = [
    ("netlify.toml", "arquivo"),
    ("netlify/edge-functions", "pasta"),
    ("netlify/functions", "pasta"),  # vazia, só para o Netlify não avisar que o diretório não existe
    ("public", "pasta"),
]
# nunca copiar, mesmo que apareçam dentro de public/
PROIBIDOS = {".env", ".env.google", ".dev.vars", "senha-local.txt", "node_modules", ".netlify", "__pycache__"}


def limpar(destino: str) -> None:
    """Esvazia a pasta em vez de apagá-la: no Windows, apagar a própria pasta falha se
    algum terminal ainda estiver com ela aberta."""
    os.makedirs(destino, exist_ok=True)
    for nome in os.listdir(destino):
        alvo = os.path.join(destino, nome)
        if os.path.isdir(alvo) and not os.path.islink(alvo):
            shutil.rmtree(alvo, ignore_errors=True)
        else:
            try:
                os.remove(alvo)
            except OSError:
                pass


def ignorar(_dir, nomes):
    return [n for n in nomes if n.lower() in PROIBIDOS or n.endswith(".pyc")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="deploy-netlify")
    args = ap.parse_args()

    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(raiz)

    faltando = [c for c, _ in ITENS if not os.path.exists(c)]
    if faltando:
        print("ERRO: não encontrei", ", ".join(faltando))
        return 2

    destino = os.path.abspath(args.out)
    if os.path.commonpath([destino, os.path.abspath("public")]) == os.path.abspath("public"):
        print("ERRO: a pasta de saída não pode ficar dentro de public/")
        return 2

    limpar(destino)
    for caminho, tipo in ITENS:
        alvo = os.path.join(destino, caminho)
        os.makedirs(os.path.dirname(alvo) or destino, exist_ok=True)
        if tipo == "pasta":
            shutil.copytree(caminho, alvo, ignore=ignorar)
        else:
            shutil.copy2(caminho, alvo)

    arquivos, bytes_ = 0, 0
    dados = 0
    for base, _, nomes in os.walk(destino):
        for n in nomes:
            p = os.path.join(base, n)
            arquivos += 1
            bytes_ += os.path.getsize(p)
            if os.sep + "data" + os.sep in p and n.endswith(".json"):
                dados += 1

    # conferência: a camada de senha precisa estar lá, senão o site sobe aberto
    guarda = os.path.join(destino, "netlify", "edge-functions", "auth.js")
    if not os.path.exists(guarda):
        print("ERRO: a Edge Function não foi copiada — NÃO suba esta pasta.")
        return 3
    vazados = []
    for base, _, nomes in os.walk(destino):
        for n in nomes:
            if n.lower() in PROIBIDOS:
                vazados.append(os.path.relpath(os.path.join(base, n), destino))
    if vazados:
        print("ERRO: arquivo local de segredo entrou no pacote:", ", ".join(vazados))
        return 3

    print(f"Pacote pronto em: {destino}")
    print(f"  {arquivos} arquivos · {bytes_ / 1024 / 1024:.1f} MB · {dados} arquivo(s) de dados")
    print("  camada de senha incluída (netlify/edge-functions/auth.js)")
    print("\nArraste essa pasta na tela de deploy do Netlify.")
    print("Antes de abrir o site, cadastre DASHBOARD_PASSWORD e SESSION_SECRET nas variáveis do site.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
