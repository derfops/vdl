# HOW-TO: Usar vdl e subtitles

## Preparação
- Crie um arquivo `.env` na raiz do projeto com:
  - `OPENVPN_USER=<usuario_CyberGhost>`
  - `OPENVPN_PASSWORD=<senha_CyberGhost>`
  - `OPENAI_API_KEY=<sua_chave_OpenAI>`
  - `MEDIA_DIR=./data/storage/media` ou outro caminho local para mídia
- Crie o diretório `data/` para guardar os arquivos de saída.
- Garanta que os arquivos do OpenVPN estejam em `gluetun/`:
  - `ca.crt`
  - `client.crt`
  - `client.key`
  - `openvpn.ovpn`
  - Para preparar a partir do zip: `python3 scripts/prepare_gluetun.py`

## Docker com runtimes VDL
- O `docker-compose.yml` padrão sobe dois serviços:
  - `vpn-vdl`: Gluetun com OpenVPN custom do CyberGhost.
  - `vdl`: container do VDL usando `network_mode: service:vpn-vdl`.
- Isso faz o VDL compartilhar a rede do Gluetun; se a VPN não estiver saudável, o VDL não sobe.
- O launcher recomendado é `./vdl.sh`. Sem argumentos ele abre um menu para
  CyberGhost, Windscribe, status, logs, shell e teste de IP.
- O runtime sem VPN fica em `docker-compose.novpn.yml` e pode ser iniciado com
  `./vdl.sh up-novpn`.
- Subir:
  - `./vdl.sh up`
  - ou `docker compose up -d --build`
- Verificar status:
  - `./vdl.sh status`
  - `./vdl.sh ip`
  - ou `docker exec vdl curl -s ifconfig.me`
- Derrubar:
  - `./vdl.sh down`

## Docker com Windscribe WireGuard
- Há um compose separado para Windscribe:
  - `docker-compose.windscribe.yml`
- Ele usa o arquivo local `Windscribe-StaticIP-WG.conf` e prepara uma cópia em
  `windscribe/wg0.conf`.
- Subir:
  - `./vdl.sh up-windscribe`
- Verificar:
  - `./vdl.sh status`
  - `./vdl.sh ip`
  - ou `docker exec vdl-windscribe curl -s ifconfig.me`
- Derrubar:
  - `./vdl.sh down-windscribe`

## Launchers e help
- `./vdl.sh`: abre o menu de operação Docker.
- `./vdl.sh studio`: sobe o VDL Studio Web em `http://localhost:8787`.
- `./vdl.sh --help`: mostra todos os comandos diretos.
- `./manage.sh --help`: mantém compatibilidade e chama o help do `vdl.sh`.
- `vdl --help`: dentro do container, mostra o help do CLI Python.
- `python3 vdl.py --help`: fora do container, mostra o mesmo help do CLI Python.
- Guia específico de VPN: `docs/HOWTO-VPN.md`.

## Dentro do container
- Binários disponíveis: `vdl` e `subtitles`.
- Diretório de trabalho padrão: `/data` (mapeado para `./data`).

## VDL Studio: modo interativo
- Abra o menu guiado:
  - `vdl`
  - `vdl --studio`
  - ou, pelo host: `./vdl.sh studio`
- Opções disponíveis:
  - `Download em lote`
  - `Retomar lote de download`
  - `Gerar legendas`
  - `Gerar contexto`
  - `Consolidar em e-book`
- No download em lote:
  - Cole o cookie/token em Base64, cookies JSON puros ou header `Cookie` puro.
  - Informe o diretório de destino.
  - Cole várias URLs, uma por linha, e finalize com `END`.
  - Os arquivos são nomeados automaticamente como `01.mp4`, `02.mp4`, etc.
  - Escolha entre 1 e 4 jobs simultâneos.
  - Use `Retomar lote de download` para reprocessar jobs pendentes, falhados ou interrompidos.
  - O estado local da fila fica em `.vdl-studio/` quando executado dentro de `/data`.
  - Credenciais não são gravadas no estado da fila; informe novamente ao retomar.

## vdl: download e processamento
- Download simples (apenas baixar o vídeo):
  - `vdl <URL> <nome_saida>.mp4 --only-download -d output_dir`
- Download e processamento local (extrai áudio, transcreve e gera contexto):
  - `vdl <URL> <nome_saida>.mp4 -t -c -d output_dir`
- Processar um arquivo local já existente:
  - `vdl -l /data/meu_video.mp4 -t -c -d output_dir`
- Processar um diretório recursivamente:
  - `vdl -l /data/aulas -t -c -d output_dir`  (busca recursiva)
- Modo unificado via API (transcrição + contexto pela OpenAI):
  - `vdl -l /data/meu_video.mp4 -u -d output_dir`
- E-book consolidado a partir de contextos `.md`:
  - `vdl --all-contexts -d output_dir`  (usa map-reduce, suporta muitos arquivos)

Notas:
- Para funcionalidades de IA, defina `OPENAI_API_KEY` no ambiente.
- Para downloads autenticados, defina `VDL_TOKEN` em Base64 com **cookies em
  JSON** exportados do navegador, ou coloque um arquivo
  `cookies.json`/`cookie.json`/`token.txt`/`cookie.txt` em `/data` ou no
  diretório do script. O formato legado `User-Agent;cookie` está deprecado.
- Para CDNs com hot-link (BunnyCDN, etc.), o Referer é inferido do domínio dos
  cookies. Override manual: `--referer https://plataforma.com/`.
- Cache do Whisper: o volume `whisper_cache` (em `/cache/whisper`) preserva
  modelos entre restarts do container — sem isso o medium (1.5GB) seria
  re-baixado a cada `up`.

## subtitles: gerar SRT por idioma detectado + tradução
- Processar um arquivo ou diretório:
  - `subtitles /data/meu_video.mp4 --translate-engine openai --model base --device cpu`
  - Threads: padrão usa todas (CPU multi-core); para limitar, `--threads 4`.
  - Diretório de saída: `--output-dir /data/legendas` (padrão: ao lado da mídia).
- Saídas geradas no mesmo diretório:
  - `<video>.<idioma_detectado>.srt`  (ex.: `.pt.srt`, `.en.srt`)
  - `<video>.<args.lang>.srt`  (default `pt-BR`; pulado se idioma == args.lang)

## Dicas
- `output_dir` padrão é `output_dir`. Altere com `-d`.
- Para GPU na transcrição local do `vdl`, use `--gpu` e configure CUDA.
  Em CUDA, `fp16` é ativado automaticamente.
- Logs detalhados ficam em `./logs/<timestamp_pid>.log` (sem códigos ANSI).
