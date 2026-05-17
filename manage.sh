#!/usr/bin/env bash
set -euo pipefail
BASE="docker-compose.yml"
GLUE="docker-compose.gluetun.yml"
CMD="${1:-}"
OPT="${2:-}"
# cookie.txt é OPCIONAL: só é necessário se você for fazer download
# autenticado. Para uso só com subtitles ou processamento local, pode
# subir os containers sem ele. VDL_TOKEN exportado também é aceito.
COOKIE_FILE="./data/cookie.txt"
if [[ -f "$COOKIE_FILE" ]]; then
  export VDL_TOKEN="$(cat "$COOKIE_FILE" | base64 | tr -d '\n')"
elif [[ -n "${VDL_TOKEN:-}" ]]; then
  export VDL_TOKEN
else
  echo "Aviso: nem ./data/cookie.txt nem VDL_TOKEN encontrados."
  echo "       Containers sobem, mas downloads autenticados não funcionarão."
  export VDL_TOKEN=""
fi
if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
else
  echo "Erro: nem 'docker compose' nem 'docker-compose' encontrados"
  exit 1
fi
case "$CMD" in
  up)
    if [[ "$OPT" == "--without-vpn" ]]; then
      $COMPOSE -f "$BASE" up -d
    else
      $COMPOSE -f "$GLUE" up -d
    fi
    ;;
  down)
    if [[ "$OPT" == "--without-vpn" ]]; then
      $COMPOSE -f "$BASE" down --remove-orphans || true
    else
      $COMPOSE -f "$GLUE" down --remove-orphans || true
      $COMPOSE -f "$BASE" down --remove-orphans || true
      docker rm -f gluetun >/dev/null 2>&1 || true
    fi
    ;;
  rebuild)
    if [[ "$OPT" == "--without-vpn" ]]; then
      $COMPOSE -f "$BASE" build --no-cache
      $COMPOSE -f "$BASE" up -d
    else
      $COMPOSE -f "$GLUE" build --no-cache
      $COMPOSE -f "$GLUE" up -d
    fi
    ;;
  *)
    echo "Uso: ./manage.sh [up|down|rebuild] [--without-vpn]"
    exit 1
    ;;
esac
