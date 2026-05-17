# HOW-TO: Usar vdl e subtitles

## Preparação
- Crie um arquivo `.env` na raiz do projeto com:
  - `OPENAI_API_KEY=<sua_chave_OpenAI>`
  - (Opcional para Gluetun) Variáveis de VPN conforme o seu provedor
- Crie o diretório `data/` para guardar os arquivos de saída.

## Dentro do container
- Binários disponíveis: `vdl` e `subtitles`.
- Diretório de trabalho padrão: `/data` (mapeado para `./data`).

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
- Saídas geradas no mesmo diretório:
  - `<video>.<idioma_detectado>.srt`  (ex.: `.pt.srt`, `.en.srt`)
  - `<video>.<args.lang>.srt`  (default `pt-BR`; pulado se idioma == args.lang)

## Dicas
- `output_dir` padrão é `output_dir`. Altere com `-d`.
- Para GPU na transcrição local do `vdl`, use `--gpu` e configure CUDA.
  Em CUDA, `fp16` é ativado automaticamente.
- Logs detalhados ficam em `./logs/<timestamp_pid>.log` (sem códigos ANSI).

