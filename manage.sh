#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

HELP_REQUESTED=0
for arg in "$@"; do
  if [[ "$arg" == "--help" || "$arg" == "-h" || "$arg" == "help" ]]; then
    HELP_REQUESTED=1
  fi
done

if [[ "$HELP_REQUESTED" != "1" ]]; then
  echo "Aviso: manage.sh continua funcionando, mas o launcher principal agora e ./vdl.sh."
fi

exec "$ROOT_DIR/vdl.sh" "$@"
