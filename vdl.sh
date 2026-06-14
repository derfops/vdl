#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

BASE_COMPOSE="docker-compose.yml"
WINDSCRIBE_COMPOSE="docker-compose.windscribe.yml"
NOVPN_COMPOSE="docker-compose.novpn.yml"
STUDIO_COMPOSE="docker-compose.studio.yml"
PYTHON_BIN="${PYTHON_BIN:-python3}"

show_help() {
  cat <<'EOF'
VDL Studio launcher

Uso:
  ./vdl.sh                  abre o menu interativo
  ./vdl.sh <comando>        executa uma acao direta
  ./vdl.sh --help           mostra este help

Comandos principais:
  studio, up-studio        sobe o VDL Studio Web em http://localhost:8787
  down-studio              derruba o VDL Studio Web
  rebuild-studio           recompila e sobe o VDL Studio Web

  up-novpn                 sobe o VDL sem VPN
  down-novpn               derruba o stack sem VPN
  rebuild-novpn            recompila e sobe o stack sem VPN

  up, up-cyberghost         sobe o VDL com CyberGhost/OpenVPN (padrao)
  down, down-cyberghost     derruba o stack CyberGhost
  rebuild, rebuild-cyberghost
                             recompila e sobe o stack CyberGhost

  up-windscribe             sobe o VDL com Windscribe/WireGuard
  down-windscribe           derruba o stack Windscribe
  rebuild-windscribe        recompila e sobe o stack Windscribe

Operacao e diagnostico:
  status                    mostra status dos stacks Docker
  ip                        testa o IP de saida dos containers VDL
  logs, logs-cyberghost     mostra logs recentes do Gluetun CyberGhost
  logs-windscribe           mostra logs recentes do Gluetun Windscribe
  logs-novpn                mostra logs recentes do worker sem VPN
  shell, shell-cyberghost   abre bash no container VDL/CyberGhost
  shell-novpn               abre bash no container VDL sem VPN
  shell-windscribe          abre bash no container VDL/Windscribe
  cli-cyberghost            abre o VDL Studio CLI no container CyberGhost
  cli-novpn                 abre o VDL Studio CLI no container sem VPN
  cli-windscribe            abre o VDL Studio CLI no container Windscribe
  python-help               mostra o --help do CLI Python vdl

Arquivos esperados:
  CyberGhost:  .env + glutenn_openvpn.zip ou gluetun/openvpn.ovpn
  Windscribe:  Windscribe-StaticIP-WG.conf
  Cookie:      ./data/cookie.txt ou VDL_TOKEN no ambiente

Notas:
  - O stack padrao usa CyberGhost via docker-compose.yml.
  - O Windscribe usa docker-compose.windscribe.yml.
  - O Studio Web usa docker-compose.studio.yml.
  - manage.sh continua disponivel como alias de compatibilidade.
EOF
}

is_help_arg() {
  [[ "${1:-}" == "-h" || "${1:-}" == "--help" || "${1:-}" == "help" ]]
}

show_command_help() {
  local command="$1"

  case "$command" in
    menu)
      cat <<'EOF'
Uso: ./vdl.sh

Abre o menu interativo para operar os stacks CyberGhost e Windscribe.
EOF
      ;;
    up|up-cyberghost)
      cat <<'EOF'
Uso: ./vdl.sh up

Sobe o stack padrao CyberGhost/OpenVPN:
  - prepara gluetun/openvpn.ovpn a partir de glutenn_openvpn.zip quando preciso
  - carrega ./data/cookie.txt ou VDL_TOKEN, se existir
  - executa docker compose -f docker-compose.yml up -d
EOF
      ;;
    studio|up-studio)
      cat <<'EOF'
Uso: ./vdl.sh studio
Uso: ./vdl.sh up-studio

Sobe o VDL Studio Web:
  - frontend em http://localhost:8787
  - API local em http://localhost:8788
  - a API orquestra os runtimes sem VPN, CyberGhost e Windscribe
EOF
      ;;
    down-studio)
      cat <<'EOF'
Uso: ./vdl.sh down-studio

Derruba os containers do VDL Studio Web.
EOF
      ;;
    rebuild-studio)
      cat <<'EOF'
Uso: ./vdl.sh rebuild-studio

Recompila e sobe novamente frontend e API do VDL Studio Web.
EOF
      ;;
    up-novpn)
      cat <<'EOF'
Uso: ./vdl.sh up-novpn

Sobe o worker VDL sem VPN. Use apenas quando o download/processamento nao
precisar sair por CyberGhost ou Windscribe.
EOF
      ;;
    down-novpn)
      cat <<'EOF'
Uso: ./vdl.sh down-novpn

Derruba o worker VDL sem VPN.
EOF
      ;;
    rebuild-novpn)
      cat <<'EOF'
Uso: ./vdl.sh rebuild-novpn

Recompila a imagem VDL sem cache e sobe novamente o worker sem VPN.
EOF
      ;;
    down|down-cyberghost)
      cat <<'EOF'
Uso: ./vdl.sh down

Derruba o stack CyberGhost e remove containers orfaos relacionados.
EOF
      ;;
    rebuild|rebuild-cyberghost)
      cat <<'EOF'
Uso: ./vdl.sh rebuild

Recompila a imagem VDL sem cache e sobe novamente o stack CyberGhost.
EOF
      ;;
    up-windscribe)
      cat <<'EOF'
Uso: ./vdl.sh up-windscribe

Sobe o stack Windscribe/WireGuard:
  - prepara windscribe/wg0.conf a partir de Windscribe-StaticIP-WG.conf
  - carrega ./data/cookie.txt ou VDL_TOKEN, se existir
  - executa docker compose -f docker-compose.windscribe.yml up -d
EOF
      ;;
    down-windscribe)
      cat <<'EOF'
Uso: ./vdl.sh down-windscribe

Derruba o stack Windscribe e remove containers orfaos relacionados.
EOF
      ;;
    rebuild-windscribe)
      cat <<'EOF'
Uso: ./vdl.sh rebuild-windscribe

Recompila a imagem VDL sem cache e sobe novamente o stack Windscribe.
EOF
      ;;
    status|ps)
      cat <<'EOF'
Uso: ./vdl.sh status

Mostra o status Docker dos stacks CyberGhost e Windscribe.
EOF
      ;;
    ip|test-ip)
      cat <<'EOF'
Uso: ./vdl.sh ip

Consulta o IP publico de saida dos containers vdl e vdl-windscribe.
EOF
      ;;
    logs|logs-cyberghost)
      cat <<'EOF'
Uso: ./vdl.sh logs [linhas]

Mostra logs recentes do Gluetun CyberGhost. Padrao: 120 linhas.
EOF
      ;;
    logs-windscribe)
      cat <<'EOF'
Uso: ./vdl.sh logs-windscribe [linhas]

Mostra logs recentes do Gluetun Windscribe. Padrao: 120 linhas.
EOF
      ;;
    logs-novpn)
      cat <<'EOF'
Uso: ./vdl.sh logs-novpn [linhas]

Mostra logs recentes do worker VDL sem VPN. Padrao: 120 linhas.
EOF
      ;;
    shell|shell-cyberghost)
      cat <<'EOF'
Uso: ./vdl.sh shell

Abre bash interativo no container vdl do stack CyberGhost.
EOF
      ;;
    shell-windscribe)
      cat <<'EOF'
Uso: ./vdl.sh shell-windscribe

Abre bash interativo no container vdl-windscribe do stack Windscribe.
EOF
      ;;
    cli-cyberghost|studio-cyberghost)
      cat <<'EOF'
Uso: ./vdl.sh cli-cyberghost

Abre o VDL Studio interativo no container vdl do stack CyberGhost.
EOF
      ;;
    cli-novpn|studio-novpn)
      cat <<'EOF'
Uso: ./vdl.sh cli-novpn

Abre o VDL Studio interativo no container vdl-novpn.
EOF
      ;;
    cli-windscribe|studio-windscribe)
      cat <<'EOF'
Uso: ./vdl.sh cli-windscribe

Abre o VDL Studio interativo no container vdl-windscribe do stack Windscribe.
EOF
      ;;
    python-help|vdl-help)
      cat <<'EOF'
Uso: ./vdl.sh python-help

Mostra o --help do CLI Python vdl. Usa um container em execucao quando existe,
ou python3 vdl.py no host como fallback.
EOF
      ;;
    *)
      show_help
      ;;
  esac
}

compose() {
  if docker compose version >/dev/null 2>&1; then
    docker compose "$@"
  elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
  else
    echo "Erro: nem 'docker compose' nem 'docker-compose' foram encontrados." >&2
    exit 1
  fi
}

load_download_token() {
  local cookie_file="./data/cookie.txt"
  mkdir -p ./data

  if [[ -f "$cookie_file" ]]; then
    export VDL_TOKEN
    VDL_TOKEN="$(base64 < "$cookie_file" | tr -d '\n')"
    return
  fi

  if [[ -n "${VDL_TOKEN:-}" ]]; then
    export VDL_TOKEN
    return
  fi

  export VDL_TOKEN=""
  echo "Aviso: nem ./data/cookie.txt nem VDL_TOKEN foram encontrados."
  echo "       Containers sobem, mas downloads autenticados nao funcionarao."
}

reject_without_vpn() {
  if [[ "${1:-}" == "--without-vpn" ]]; then
    echo "Erro: o VDL sobe sempre via Gluetun/VPN." >&2
    exit 1
  fi
}

prepare_cyberghost() {
  "$PYTHON_BIN" scripts/prepare_gluetun.py
}

prepare_windscribe() {
  "$PYTHON_BIN" scripts/prepare_windscribe.py
}

cyberghost_compose() {
  compose -f "$BASE_COMPOSE" "$@"
}

windscribe_compose() {
  compose -f "$WINDSCRIBE_COMPOSE" "$@"
}

novpn_compose() {
  compose -f "$NOVPN_COMPOSE" "$@"
}

studio_compose() {
  VDL_PROJECT_ROOT="$ROOT_DIR" compose -f "$STUDIO_COMPOSE" "$@"
}

cmd_up_studio() {
  studio_compose up -d --build
  echo "VDL Studio Web: http://localhost:${VDL_STUDIO_PORT:-8787}"
}

cmd_down_studio() {
  studio_compose down --remove-orphans || true
}

cmd_rebuild_studio() {
  studio_compose build --no-cache
  studio_compose up -d
  echo "VDL Studio Web: http://localhost:${VDL_STUDIO_PORT:-8787}"
}

cmd_up_novpn() {
  load_download_token
  novpn_compose up -d
}

cmd_down_novpn() {
  novpn_compose down --remove-orphans || true
  docker rm -f vdl-novpn >/dev/null 2>&1 || true
}

cmd_rebuild_novpn() {
  load_download_token
  novpn_compose build --no-cache
  novpn_compose up -d
}

cmd_up_cyberghost() {
  reject_without_vpn "${1:-}"
  load_download_token
  prepare_cyberghost
  cyberghost_compose up -d
}

cmd_down_cyberghost() {
  cyberghost_compose down --remove-orphans || true
  docker rm -f gluetun >/dev/null 2>&1 || true
}

cmd_rebuild_cyberghost() {
  reject_without_vpn "${1:-}"
  load_download_token
  prepare_cyberghost
  cyberghost_compose build --no-cache
  cyberghost_compose up -d
}

cmd_up_windscribe() {
  load_download_token
  prepare_windscribe
  windscribe_compose up -d
}

cmd_down_windscribe() {
  windscribe_compose down --remove-orphans || true
  docker rm -f gluetun-windscribe vdl-windscribe >/dev/null 2>&1 || true
}

cmd_rebuild_windscribe() {
  load_download_token
  prepare_windscribe
  windscribe_compose build --no-cache
  windscribe_compose up -d
}

container_running() {
  docker ps --format '{{.Names}}' | grep -qx "$1"
}

cmd_status() {
  echo "VDL Studio Web:"
  studio_compose ps || true
  echo
  echo "Sem VPN:"
  novpn_compose ps || true
  echo
  echo "CyberGhost:"
  cyberghost_compose ps || true
  echo
  echo "Windscribe:"
  windscribe_compose ps || true
}

ip_for_container() {
  local container="$1"

  if ! container_running "$container"; then
    echo "$container: nao esta rodando"
    return
  fi

  printf '%s: ' "$container"
  docker exec "$container" sh -lc 'curl -fsS --max-time 10 ifconfig.me' || {
    echo "falha ao consultar IP"
  }
  echo
}

cmd_ip() {
  ip_for_container "vdl-novpn"
  ip_for_container "vdl"
  ip_for_container "vdl-windscribe"
}

cmd_logs_novpn() {
  local tail_lines="${1:-120}"
  docker logs vdl-novpn --tail "$tail_lines"
}

cmd_logs_cyberghost() {
  local tail_lines="${1:-120}"
  docker logs gluetun --tail "$tail_lines"
}

cmd_logs_windscribe() {
  local tail_lines="${1:-120}"
  docker logs gluetun-windscribe --tail "$tail_lines"
}

require_running_container() {
  local container="$1"
  if ! container_running "$container"; then
    echo "Erro: container '$container' nao esta rodando." >&2
    exit 1
  fi
}

require_tty() {
  local action="$1"
  if [[ ! -t 0 || ! -t 1 ]]; then
    echo "Erro: $action precisa de um terminal interativo." >&2
    exit 2
  fi
}

cmd_shell() {
  local container="$1"
  require_running_container "$container"
  require_tty "abrir shell"
  docker exec -it "$container" bash
}

cmd_studio() {
  local container="$1"
  require_running_container "$container"
  require_tty "abrir o VDL Studio"
  docker exec -it "$container" vdl
}

cmd_python_help() {
  if container_running "vdl"; then
    docker exec vdl vdl --help
  elif container_running "vdl-windscribe"; then
    docker exec vdl-windscribe vdl --help
  else
    "$PYTHON_BIN" vdl.py --help
  fi
}

pause_menu() {
  echo
  printf 'Pressione Enter para continuar... '
  read -r _
}

show_menu() {
  cat <<'EOF'

VDL Studio

1) Subir VDL Studio Web
2) Derrubar VDL Studio Web
3) Status Docker
4) Testar IPs de saida

5) Subir sem VPN
6) Derrubar sem VPN
7) Rebuild sem VPN
8) Abrir CLI VDL (sem VPN)

9) Subir CyberGhost
10) Derrubar CyberGhost
11) Rebuild CyberGhost
12) Abrir CLI VDL (CyberGhost)

13) Subir Windscribe
14) Derrubar Windscribe
15) Rebuild Windscribe
16) Abrir CLI VDL (Windscribe)

17) Logs CyberGhost
18) Logs Windscribe
19) Help do CLI Python vdl
20) Sair

EOF
}

menu_loop() {
  require_tty "abrir menu"

  while true; do
    show_menu
    printf 'Escolha uma opcao: '
    read -r choice

    case "$choice" in
      1) cmd_up_studio; pause_menu ;;
      2) cmd_down_studio; pause_menu ;;
      3) cmd_status; pause_menu ;;
      4) cmd_ip; pause_menu ;;
      5) cmd_up_novpn; pause_menu ;;
      6) cmd_down_novpn; pause_menu ;;
      7) cmd_rebuild_novpn; pause_menu ;;
      8) cmd_studio "vdl-novpn" ;;
      9) cmd_up_cyberghost; pause_menu ;;
      10) cmd_down_cyberghost; pause_menu ;;
      11) cmd_rebuild_cyberghost; pause_menu ;;
      12) cmd_studio "vdl" ;;
      13) cmd_up_windscribe; pause_menu ;;
      14) cmd_down_windscribe; pause_menu ;;
      15) cmd_rebuild_windscribe; pause_menu ;;
      16) cmd_studio "vdl-windscribe" ;;
      17) cmd_logs_cyberghost; pause_menu ;;
      18) cmd_logs_windscribe; pause_menu ;;
      19) cmd_python_help; pause_menu ;;
      20|s|S|q|Q|exit) exit 0 ;;
      *) echo "Opcao invalida."; pause_menu ;;
    esac
  done
}

cmd="${1:-menu}"
if [[ $# -gt 0 ]]; then
  shift
fi

if [[ $# -gt 0 ]] && is_help_arg "${1:-}"; then
  show_command_help "$cmd"
  exit 0
fi

case "$cmd" in
  menu) menu_loop ;;
  -h|--help|help) show_help ;;
  studio|up-studio) cmd_up_studio ;;
  down-studio) cmd_down_studio ;;
  rebuild-studio) cmd_rebuild_studio ;;
  up-novpn) cmd_up_novpn ;;
  down-novpn) cmd_down_novpn ;;
  rebuild-novpn) cmd_rebuild_novpn ;;
  up|up-cyberghost) cmd_up_cyberghost "$@" ;;
  down|down-cyberghost) cmd_down_cyberghost ;;
  rebuild|rebuild-cyberghost) cmd_rebuild_cyberghost "$@" ;;
  up-windscribe) cmd_up_windscribe ;;
  down-windscribe) cmd_down_windscribe ;;
  rebuild-windscribe) cmd_rebuild_windscribe ;;
  status|ps) cmd_status ;;
  ip|test-ip) cmd_ip ;;
  logs|logs-cyberghost) cmd_logs_cyberghost "$@" ;;
  logs-windscribe) cmd_logs_windscribe "$@" ;;
  logs-novpn) cmd_logs_novpn "$@" ;;
  shell|shell-cyberghost) cmd_shell "vdl" ;;
  shell-novpn) cmd_shell "vdl-novpn" ;;
  shell-windscribe) cmd_shell "vdl-windscribe" ;;
  cli-cyberghost|studio-cyberghost) cmd_studio "vdl" ;;
  cli-novpn|studio-novpn) cmd_studio "vdl-novpn" ;;
  cli-windscribe|studio-windscribe) cmd_studio "vdl-windscribe" ;;
  python-help|vdl-help) cmd_python_help ;;
  *)
    echo "Comando desconhecido: $cmd" >&2
    echo "Use './vdl.sh --help' para ver as opcoes." >&2
    exit 1
    ;;
esac
