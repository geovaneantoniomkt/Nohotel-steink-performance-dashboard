#!/usr/bin/env bash
# Confere, depois do deploy, que o site publicado continua atrás de senha.
# Rede de segurança contra a pior falha possível: a camada de senha não subir e o
# dashboard (com os dados do cliente) ficar aberto na internet.
#
# Uso: bash scripts/check_live.sh <url-do-site> "<onde conferir as variáveis>"
set -u
url="${1%/}"
onde="${2:-variáveis de ambiente do destino}"

# O deploy leva alguns segundos para propagar; tenta por até ~1 minuto.
for tentativa in 1 2 3 4 5 6; do
  dados=$(curl -s -o /dev/null -w '%{http_code}' "$url/data/meta.json")
  raiz=$(curl -s -o /dev/null -w '%{http_code}' "$url/")
  echo "[$tentativa] GET /data/meta.json -> $dados (esperado 401) · GET / -> $raiz (esperado 303)"
  if [ "$dados" = "401" ] && { [ "$raiz" = "303" ] || [ "$raiz" = "302" ]; }; then
    echo "Proteção por senha confirmada em $url"
    exit 0
  fi
  sleep 10
done

if [ "$dados" = "503" ] || [ "$raiz" = "503" ]; then
  echo "::error::$url respondeu 503: faltam DASHBOARD_PASSWORD e/ou SESSION_SECRET nas $onde. O site está fechado, mas ninguém consegue entrar."
elif [ "$dados" = "200" ]; then
  echo "::error::$url entregou os dados SEM senha (HTTP 200). Confira as $onde e se a camada de senha foi publicada."
else
  echo "::error::$url não respondeu como esperado (dados $dados, raiz $raiz). Confira as $onde."
fi
exit 1
