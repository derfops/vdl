# HOWTO-VPN: VDL Studio

O VDL Studio Web pode iniciar o backend VDL em tres modos:

- `Sem VPN`: usa o container `vdl-novpn`.
- `CyberGhost`: usa `gluetun` + `vdl`, com OpenVPN.
- `Windscribe`: usa `gluetun-windscribe` + `vdl-windscribe`, com WireGuard.

O frontend nao conversa com Docker diretamente. Ele chama a API local
`vdl-studio-api`, que executa apenas comandos permitidos do `vdl.sh`.

## Subir o VDL Studio Web

```bash
./vdl.sh studio
```

Depois acesse:

```text
http://localhost:8787
```

Portas:

- Frontend: `8787`
- API: `8788`

Para trocar portas:

```bash
VDL_STUDIO_PORT=8790 VDL_STUDIO_API_PORT=8791 ./vdl.sh studio
```

## Modo sem VPN

Esse modo nao exige configuracao de VPN.

Pelo terminal:

```bash
./vdl.sh up-novpn
./vdl.sh ip
```

Pelo VDL Studio Web:

1. Escolha `Sem VPN`.
2. Clique em `Iniciar`.
3. Clique em `Testar IP`.

Use esse modo apenas para conteudos que nao precisam sair por VPN.

## CyberGhost

Arquivos e variaveis esperados:

- `.env` na raiz do projeto
- `OPENVPN_USER`
- `OPENVPN_PASSWORD`
- `glutenn_openvpn.zip` ou arquivos ja preparados em `gluetun/`

Exemplo de `.env`:

```bash
OPENVPN_USER=seu_usuario
OPENVPN_PASSWORD=sua_senha
OPENAI_API_KEY=
MEDIA_DIR=./data/storage/media
```

Preparar manualmente:

```bash
python3 scripts/prepare_gluetun.py
```

Subir pelo terminal:

```bash
./vdl.sh up
```

Validar:

```bash
docker compose ps
docker logs gluetun --tail=120
docker exec vdl curl -fsS ifconfig.me
```

Pelo VDL Studio Web:

1. Escolha `CyberGhost`.
2. Clique em `Iniciar`.
3. Aguarde o status `pronto`.
4. Clique em `Testar IP`.

## Windscribe

Arquivo esperado:

```text
Windscribe-StaticIP-WG.conf
```

O script cria uma copia preparada em:

```text
windscribe/wg0.conf
```

Preparar manualmente:

```bash
python3 scripts/prepare_windscribe.py
```

Subir pelo terminal:

```bash
./vdl.sh up-windscribe
```

Validar:

```bash
docker compose -f docker-compose.windscribe.yml ps
docker logs gluetun-windscribe --tail=120
docker exec vdl-windscribe curl -fsS ifconfig.me
```

Pelo VDL Studio Web:

1. Escolha `Windscribe`.
2. Clique em `Iniciar`.
3. Aguarde o status `pronto`.
4. Clique em `Testar IP`.

## Cookies e downloads

O VDL Studio Web aceita:

- `VDL_TOKEN` em Base64
- JSON de cookies exportado do navegador
- Header `Cookie` puro

No Docker, o arquivo opcional abaixo tambem e aceito:

```text
./data/cookie.txt
```

Credenciais nao devem ser versionadas. `.env`, `data/`, `windscribe/`,
`gluetun/`, `Windscribe-*.conf` e arquivos de token ficam ignorados pelo Git.

## Diagnostico rapido

Status geral:

```bash
./vdl.sh status
```

IPs de saida:

```bash
./vdl.sh ip
```

Logs:

```bash
./vdl.sh logs-novpn
./vdl.sh logs
./vdl.sh logs-windscribe
```

Se a VPN nao ficar saudavel:

- Confirme se o `.env` existe e tem as credenciais do CyberGhost.
- Confirme se `Windscribe-StaticIP-WG.conf` existe para Windscribe.
- Rode novamente os scripts `prepare_*`.
- Confira os logs do Gluetun.
- Verifique se o Docker tem acesso a `/dev/net/tun`.

## Observacao de seguranca

O `vdl-studio-api` monta `/var/run/docker.sock` para controlar containers
locais. Isso e aceitavel para uso pessoal/local, mas nao exponha a porta da API
em rede publica.
