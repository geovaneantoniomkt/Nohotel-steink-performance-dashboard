#!/usr/bin/env python3
"""
Baixa as imagens do Meta (criativos, posts, perfil) e publica junto com o dashboard.

Os links que a API do Meta devolve (scontent-*.fbcdn.net, external-*.fbcdn.net,
*.cdninstagram.com) são assinados, expiram em poucos dias e nem sempre abrem quando
embutidos em outro site. Este script roda logo depois do fetch_meta.py, baixa cada
imagem para public/data/img/ e troca a URL no JSON pelo caminho local (/data/img/...).
Assim as miniaturas saem do próprio site, atrás da mesma senha dos dados.

Se uma imagem não puder ser baixada, a URL original fica no JSON (melhor esforço).

Uso:
  python scripts/cache_images.py            # depois de scripts/fetch_meta.py

Variáveis de ambiente:
  OUT_DIR   (padrão public/data)

Sem dependências externas (apenas biblioteca padrão).
"""

from __future__ import annotations

import concurrent.futures as cf
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request

OUT_DIR = os.environ.get("OUT_DIR", "public/data")
IMG_DIR = os.path.join(OUT_DIR, "img")
PUBLIC_PREFIX = "/data/img/"
FILES = ("meta.json", "organic.json")

# campos que guardam imagem nos JSONs gerados pelo fetch_meta.py
IMAGE_KEYS = {"image_url", "thumbnail_url", "thumbnail", "picture", "full_picture", "profile_picture_url"}
HOST_SUFFIXES = (".fbcdn.net", ".cdninstagram.com")
EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
MAX_BYTES = 5 * 1024 * 1024
MAX_IMAGES = 1500


def is_meta_image(value) -> bool:
    if not isinstance(value, str) or not value.startswith("https://"):
        return False
    host = (urllib.parse.urlsplit(value).hostname or "").lower()
    return host.endswith(HOST_SUFFIXES)


def collect(node, found: set) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k in IMAGE_KEYS and is_meta_image(v):
                found.add(v)
            else:
                collect(v, found)
    elif isinstance(node, list):
        for v in node:
            collect(v, found)


def replace(node, mapping: dict):
    if isinstance(node, dict):
        return {k: (mapping.get(v, v) if k in IMAGE_KEYS and isinstance(v, str) else replace(v, mapping)) for k, v in node.items()}
    if isinstance(node, list):
        return [replace(v, mapping) for v in node]
    return node


def download(url: str) -> str | None:
    """Baixa uma imagem e devolve o caminho público, ou None se falhar."""
    name = hashlib.sha1(url.encode("utf-8")).hexdigest()[:20]
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (dashboard-nohotel)", "Accept": "image/*"})
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            ctype = (res.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            ext = EXT.get(ctype)
            if not ext:
                return None
            data = res.read(MAX_BYTES + 1)
    except Exception:  # noqa: BLE001 — melhor esforço: fica a URL original
        return None
    if not data or len(data) > MAX_BYTES:
        return None
    with open(os.path.join(IMG_DIR, name + ext), "wb") as f:
        f.write(data)
    return PUBLIC_PREFIX + name + ext


def main() -> int:
    docs = {}
    for fn in FILES:
        path = os.path.join(OUT_DIR, fn)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                docs[fn] = json.load(f)
    if not docs:
        print("Nenhum JSON do Meta encontrado; nada a fazer.")
        return 0

    urls: set = set()
    for doc in docs.values():
        collect(doc, urls)
    urls = sorted(urls)[:MAX_IMAGES]
    os.makedirs(IMG_DIR, exist_ok=True)

    mapping = {}
    with cf.ThreadPoolExecutor(max_workers=8) as pool:
        for url, local in zip(urls, pool.map(download, urls)):
            if local:
                mapping[url] = local

    for fn, doc in docs.items():
        with open(os.path.join(OUT_DIR, fn), "w", encoding="utf-8") as f:
            json.dump(replace(doc, mapping), f, ensure_ascii=False, separators=(",", ":"))

    print(f"Imagens: {len(mapping)} de {len(urls)} baixadas para {IMG_DIR}")
    if urls and not mapping:
        print("AVISO: nenhuma imagem pôde ser baixada; o dashboard vai usar os links originais do Meta.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
