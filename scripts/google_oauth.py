#!/usr/bin/env python3
"""
Gera o GOOGLE_ADS_REFRESH_TOKEN da conta Google Ads (uma vez só).

Como funciona: abre um servidor local em http://localhost:8765/, mostra o link de
autorização do Google, e quando você aprova no navegador ele troca o código pelo
refresh token e mostra o valor na tela.

Uso:
  python scripts/google_oauth.py            # lê CLIENT_ID/SECRET de .env.google
  python scripts/google_oauth.py --port 8765

Pré-requisito no Google Cloud (Credenciais → seu cliente OAuth):
  - Tipo "App para computador" já aceita http://localhost.
  - Se o cliente for do tipo "Aplicativo da Web", adicione em "URIs de redirecionamento
    autorizados": http://localhost:8765/

O refresh token é um segredo: guarde no .env.google (fora do git) e nos Secrets do
repositório no GitHub. Ele não expira enquanto o acesso não for revogado.
"""

from __future__ import annotations

import argparse
import http.server
import io
import json
import os
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

SCOPE = "https://www.googleapis.com/auth/adwords"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
ENV_FILE = ".env.google"


def load_env(path: str = ENV_FILE) -> dict:
    out = {}
    if os.path.exists(path):
        for line in io.open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    for k in ("GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_DEVELOPER_TOKEN"):
        if os.environ.get(k):
            out[k] = os.environ[k]
    return out


def save_env(values: dict, path: str = ENV_FILE) -> None:
    existing = load_env(path)
    existing.update(values)
    order = ["GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET",
             "GOOGLE_ADS_REFRESH_TOKEN", "GOOGLE_ADS_LOGIN_CUSTOMER_ID", "GOOGLE_ADS_CUSTOMER_ID"]
    lines = ["# Credenciais do Google Ads — NUNCA commitar (arquivo está no .gitignore)"]
    for k in order:
        if existing.get(k):
            lines.append(f"{k}={existing[k]}")
    for k, v in existing.items():
        if k not in order:
            lines.append(f"{k}={v}")
    io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")


class Handler(http.server.BaseHTTPRequestHandler):
    result: dict = {}

    def do_GET(self):  # noqa: N802
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" in q or "error" in q:
            Handler.result = {k: v[0] for k, v in q.items()}
            okmsg = "code" in q
            body = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>{'Autorizado' if okmsg else 'Falhou'}</title>
<style>body{{background:#101010;color:#ececea;font:16px/1.5 -apple-system,Segoe UI,sans-serif;display:grid;place-items:center;height:100vh;margin:0}}
div{{background:#18181a;border:1px solid #2a2a2d;border-radius:14px;padding:32px 36px;max-width:460px}}
h1{{font-size:20px;margin:0 0 8px;color:{'#7ad97a' if okmsg else '#ff8a8a'}}}</style></head>
<body><div><h1>{'Autorização concluída' if okmsg else 'Autorização não concluída'}</h1>
<p>{'Pode fechar esta aba e voltar ao terminal — o refresh token já foi gerado.' if okmsg else 'Erro: ' + q.get('error', [''])[0]}</p>
</div></body></html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode())
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):  # silencia o log do servidor
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true", help="só mostra o link, não abre o navegador")
    ap.add_argument("--redirect-uri", default=None, help="usar um redirect já cadastrado no cliente (ex.: https://developers.google.com/oauthplayground)")
    ap.add_argument("--code", default=None, help="trocar um código de autorização já obtido pelo refresh token (pode colar a URL inteira)")
    args = ap.parse_args()

    env = load_env()
    cid, csec = env.get("GOOGLE_ADS_CLIENT_ID"), env.get("GOOGLE_ADS_CLIENT_SECRET")
    if not cid or not csec:
        print("ERRO: defina GOOGLE_ADS_CLIENT_ID e GOOGLE_ADS_CLIENT_SECRET em .env.google")
        return 2

    redirect = args.redirect_uri or f"http://localhost:{args.port}/"
    state = secrets.token_urlsafe(16)

    # ---- modo manual: já tenho o código, só trocar pelo refresh token ---------------------
    if args.code:
        code = args.code.strip()
        if "code=" in code:  # aceita a URL inteira colada
            code = urllib.parse.parse_qs(urllib.parse.urlparse(code).query).get("code", [""])[0]
        code = urllib.parse.unquote(code)
        if not code:
            print("ERRO: não achei o código")
            return 3
        return trocar_codigo(code, cid, csec, redirect)

    if args.redirect_uri:
        # fluxo sem servidor local: o usuário aprova, cai na página do redirect e me manda a URL/código
        url = AUTH_URL + "?" + urllib.parse.urlencode({
            "client_id": cid, "redirect_uri": redirect, "response_type": "code",
            "scope": SCOPE, "access_type": "offline", "prompt": "consent",
        })
        print("\nAbra, aprove e depois rode:  python scripts/google_oauth.py --redirect-uri", redirect, "--code <URL ou código>\n")
        print(url)
        return 0
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": redirect, "response_type": "code",
        "scope": SCOPE, "access_type": "offline", "prompt": "consent", "state": state,
    })

    print("\n" + "=" * 78)
    print("Abra este link no navegador, entre com a conta Google que acessa o Google Ads")
    print("da Nohotel e clique em Permitir:\n")
    print(url)
    print("\nEsperando a autorização... (Ctrl+C cancela)")
    print("=" * 78 + "\n", flush=True)
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    srv = http.server.HTTPServer(("127.0.0.1", args.port), Handler)
    srv.serve_forever()

    res = Handler.result
    if "code" not in res:
        print(f"ERRO: autorização não concluída ({res.get('error', 'sem código')})")
        return 3
    if res.get("state") != state:
        print("ERRO: state não confere — refaça o processo")
        return 3

    return trocar_codigo(res["code"], cid, csec, redirect)


def trocar_codigo(code: str, cid: str, csec: str, redirect: str) -> int:
    body = urllib.parse.urlencode({
        "code": code, "client_id": cid, "client_secret": csec,
        "redirect_uri": redirect, "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=body, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            tok = json.load(resp)
    except urllib.error.HTTPError as e:
        print("ERRO ao trocar o código:", e.read().decode("utf-8", "replace")[:300])
        return 4

    rt = tok.get("refresh_token")
    if not rt:
        print("ERRO: o Google não devolveu refresh_token. Refaça revogando o acesso anterior em")
        print("https://myaccount.google.com/permissions e rode de novo (usamos prompt=consent).")
        return 5

    save_env({"GOOGLE_ADS_REFRESH_TOKEN": rt})
    print("\nRefresh token gerado e salvo em .env.google (fora do git).\n")
    print("Cadastre nos Secrets do repositório (Settings → Secrets and variables → Actions):")
    print(f"  GOOGLE_ADS_REFRESH_TOKEN = {rt}\n")
    print("Agora rode:  python scripts/fetch_google.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
