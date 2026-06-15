# VDL Studio — Plano para a próxima sessão

Estado em 2026-06-15. Itens abertos depois do deploy em produção (polaris).

## Contexto rápido (ler antes)
- **Studio no ar:** https://vdl.rootbox.cc (HTTPS/Let's Encrypt, Force SSL). Binds internos `127.0.0.1:8787` (frontend) e `127.0.0.1:8788` (API). NPM proxy host id **25** → `vdl-studio-frontend:80`, cert id 44.
- **Servidor:** `ssh polaris.rootbox.cc -p 22` (root). Repo em `/root/docker/vdl` (mesmo `derfops/vdl`, branch master). IP público **135.181.130.22**.
- **Subir/atualizar o Studio:**
  ```
  cd /root/docker/vdl && git fetch origin master && git merge --ff-only origin/master
  VDL_PROJECT_ROOT=/root/docker/vdl VDL_STUDIO_PORT=127.0.0.1:8787 VDL_STUDIO_API_PORT=127.0.0.1:8788 \
    docker compose -f docker-compose.studio.yml -f docker-compose.studio.override.yml up -d --build
  ```
- **Runtimes:** `Sem VPN` (vdl-novpn) e **Windscribe** (gluetun-windscribe healthy, egress por VPN) FUNCIONAM. `CyberGhost` NÃO.
- **Storage:** `/data/storage` = disco de 13 TB (vg0-storage); montado no Studio e nos workers novpn/windscribe via `${STORAGE_DIR:-./data/storage}` (`STORAGE_DIR=/data/storage` no `.env`). **gluetun.yml ainda monta só `/data/storage/media`.**
- **SSH do servidor é intermitente** (carga: qbittorrent ~116% CPU). Use `-o ConnectTimeout=25 -o ServerAliveInterval=10`; para comandos longos, rodar `nohup ... &` detached e ler o log.
- **NPM:** SQLite em `/root/docker/nginx-proxy-manager/data/database.sqlite`. Login `pcfeduardo@gmail.com` **com 2FA**. Reset de senha = atualizar `auth.secret` (pbkdf2? não — NPM usa bcrypt $2b$13$). 2FA: ler `auth.meta.totp_secret` (base32) e gerar o código (HMAC-SHA1/30s/6díg); fluxo `POST /api/tokens` {identity,secret} → challenge_token → `POST /api/tokens/2fa` {challenge_token,code}.

---

## P0 — CyberGhost não sobe (gluetun OpenVPN)
### Sintoma
`vdl.sh up-cyberghost` corre (prepare ok), mas o container `gluetun` fica **Restarting/unhealthy** e o worker `vdl` sai pelo IP do host (135.181.130.22) em vez da VPN → `vdl` não está na netns do gluetun. Aparece warning **"Found orphan containers ([gluetun])"**.

### Causas prováveis
1. **Refactor não-commitado do compose:** no working tree LOCAL, `docker-compose.gluetun.yml` foi trocado por um stub `include: docker-compose.yml`. O **servidor usa a versão committada COMPLETA** (serviços `vpn-vdl`/container `gluetun` + `vdl`). O orchestrator de cyberghost usa `up_command="up"` → `vdl.sh up` → `cmd_up` que usa **BASE_COMPOSE=docker-compose.yml** (não o gluetun.yml). Há inconsistência entre qual compose define o gluetun e o nome de projeto → órfão + vdl fora da netns.
2. **OpenVPN do CyberGhost** pode não estar conectando (creds/cert/servidor) → gluetun unhealthy mesmo com wiring certo.

### Passos
1. Entender o roteamento atual:
   - `grep -nE "cmd_up\b|BASE_COMPOSE|compose -f|project|-p " vdl.sh` e ver o que `up`/`up-cyberghost` realmente executa e com que `-p`/arquivo.
   - `git show HEAD:docker-compose.yml` (versão do servidor) e `HEAD:docker-compose.gluetun.yml` — entender qual define gluetun+vdl e se batem.
   - No servidor: `docker compose ls`, `docker inspect gluetun` (labels project/config_files), `docker logs gluetun --tail 50` (erro real do OpenVPN).
2. **Decidir a fonte da verdade do gluetun** e reconciliar (commitar): ou (a) manter `gluetun.yml` completo e fazer o orchestrator/`vdl.sh up` usar ELE para cyberghost; ou (b) consolidar tudo em `docker-compose.yml` (o caminho do refactor `include:`) e garantir que `vdl` tenha `network_mode: service:<gluetun>` correto. Versionar a decisão (o refactor local está só no working tree — PR).
3. Alinhar o **mount de storage** do gluetun ao `${STORAGE_DIR:-./data/storage}:/data/storage` (hoje só `/data/storage/media`).
4. Se o wiring ficar certo e o gluetun seguir unhealthy → investigar OpenVPN: `docker logs gluetun` para erro de auth/handshake; conferir `gluetun/openvpn.ovpn` (gerado por `scripts/prepare_gluetun.py` a partir de `glutenn_openvpn.zip`) e `OPENVPN_USER/PASSWORD` no `.env`.

### Verificação
- `vdl.sh up-cyberghost` → `docker inspect gluetun` health=healthy; `docker exec vdl curl -s ifconfig.me` → IP ≠ 135.181.130.22.
- Pela UI: Fila → CyberGhost → Iniciar sem erro; Testar IP retorna IP de VPN.

---

## P1 — Segurança (rápido, do usuário)
1. **Trocar a senha do NPM** gerada nesta sessão (`uaN2GRTkgXwfSOSQntac`, vazou no chat). NPM → Users → editar. (2FA já protege, mas rotacionar.)
2. **Access List no NPM** no proxy `vdl.rootbox.cc` (host 25): allowlist de IP **ou** basic-auth — a API do Studio tem acesso ao **Docker socket**, então defesa em profundidade importa. Dá pra criar via API (POST `/api/nginx/access-lists`, depois PUT no proxy host com `access_list_id`).
   - Auth na API do NPM: ver o truque do TOTP no contexto acima (gerar código do `totp_secret`), rodar detached.

## P2 — Housekeeping
- Reconciliar o refactor `gluetun.yml → include:` (resolve P0 e alinha repo).
- O `.zshrc` tem só `NPM_ATLAS_*` (NPM de OUTRO servidor, 23.88.70.186) — NÃO autentica no NPM do polaris. Se quiser automação futura do NPM polaris, guardar `NPM_POLARIS_*`.
- `glutenn_openvpn.zip` NÃO está no `.gitignore` (só no `.dockerignore`) — adicionar ao `.gitignore` p/ não vazar segredo.

## Trabalho em paralelo do usuário (integrar/revisar)
O usuário começou a editar `studio/api/app.py` (adicionou `DELETE` em `allow_methods` do CORS) e `styles.css` — provável endpoint/feature de **exclusão de arquivos/jobs** na Biblioteca. Revisar e integrar quando ele pedir.

## Pendências menores conhecidas
- Senha do Studio (`vdl.rootbox.cc`) já é só do usuário (ele trocou). admin/admin não entra mais.
- Workers de teste deixados de pé: `vdl-windscribe` + `gluetun-windscribe` (funcionando) e `vdl-novpn`. Parar pela UI se não estiver baixando.
