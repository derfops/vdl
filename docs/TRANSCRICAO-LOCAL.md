# Transcrição local (sem Docker) — `vdl-trans`

Como transcrever vídeos **localmente no macOS/Linux, sem Docker e sem VPN**, usando
o `vdl.py` com [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CPU).
Inclui o atalho `vdl-trans`, que embrulha o comando completo.

> **TL;DR**
> ```bash
> # setup (uma vez)
> cd /Users/carlos.vieira/Documents/Projects/vdl
> python3.12 -m venv .venv-vdl && ./.venv-vdl/bin/pip install -r requirements.txt
> ln -sf "$PWD/bin/vdl-trans" ~/.local/bin/vdl-trans
>
> # uso
> vdl-trans "meu_video.mp4"     # transcreve 1 arquivo
> vdl-trans ~/Videos            # transcreve a pasta inteira (recursivo)
> ```
> Artefatos saem **na própria pasta do alvo**: `transcriptions/<nome>.txt` e `mp3/<nome>.mp3`.

---

## 1. Pré-requisitos

| Requisito | Versão usada / observação |
|-----------|---------------------------|
| **Python** | **3.12** recomendado. Veja a nota abaixo sobre o 3.14. |
| **ffmpeg** | Já instalado via Homebrew: `/opt/homebrew/bin/ffmpeg` (v8.1). É o único pré-requisito de sistema. Instale com `brew install ffmpeg` se faltar. |
| **GPU** | Não é necessária. No Mac (Apple Silicon) roda em **CPU com quantização int8** — sem CUDA. A flag `--gpu` não tem efeito aqui. |
| **Internet** | Só na **primeira** execução, para baixar o modelo do Whisper (depois é 100% offline). |

### Por que Python 3.12 (e não o `python3` do sistema = 3.14)?

O faster-whisper depende de wheels nativos (`ctranslate2`, `av`/PyAV, `onnxruntime`).
Em junho/2026 esses pacotes ainda **não publicavam wheels para Python 3.14**, então
`python3 -m venv` (3.14) faria o `pip install` falhar ao compilar do zero. Com **3.12**
tudo instala via wheel pré-compilado, sem dor de cabeça:

```
ctranslate2-4.8.0  av-17.1.0  faster-whisper-1.2.1  onnxruntime-1.27.0  numpy-2.4.6  ...
```

Qualquer Python **3.10–3.13** também serve. Se você só tem o 3.14, instale outro:
`brew install python@3.12`.

---

## 2. Setup do venv (uma vez)

```bash
cd /Users/carlos.vieira/Documents/Projects/vdl
python3.12 -m venv .venv-vdl
./.venv-vdl/bin/pip install --upgrade pip
./.venv-vdl/bin/pip install -r requirements.txt
```

`requirements.txt` traz: `openai`, `faster-whisper`, `pycryptodomex`, `pydub`, `yt-dlp`.
O diretório `.venv-vdl/` está no `.gitignore` — **não é versionado**.

Sanidade rápida (deve imprimir `imports OK`):

```bash
./.venv-vdl/bin/python -c "import faster_whisper, ctranslate2, av, openai, pydub; print('imports OK')"
```

---

## 3. Uso direto (`vdl.py`)

```bash
# 1 arquivo
./.venv-vdl/bin/python vdl.py "caminho/video.mp4" \
  --local --transcribe -d "caminho" --whisper-model medium

# pasta inteira (busca recursiva por .mp4 .mkv .mov .webm .m4v)
./.venv-vdl/bin/python vdl.py "caminho/pasta" \
  --local --transcribe -d "caminho/pasta" --whisper-model medium
```

Flags relevantes:

| Flag | Função |
|------|--------|
| `-l, --local` | Processa arquivo/pasta já existente (sem download). |
| `-t, --transcribe` | Transcreve **localmente** (faster-whisper). |
| `-d, --directory` | Pasta de **saída** dos artefatos. |
| `--whisper-model` | `tiny` · `base` · `small` · `medium` · `large` (padrão do vdl.py: `base`). |
| `-c, --context` | (Opcional) gera um resumo/contexto via OpenAI a partir da transcrição. **Requer `OPENAI_API_KEY`.** |

---

## 4. O atalho `vdl-trans`

`bin/vdl-trans` é um wrapper que já assume os defaults bons para transcrição local:
`--local --transcribe`, **destino = a própria pasta do alvo** e **modelo `medium`**.

### Instalação no PATH

```bash
# ~/.local/bin (recomendado, sem sudo — já costuma estar no PATH)
ln -sf "/Users/carlos.vieira/Documents/Projects/vdl/bin/vdl-trans" ~/.local/bin/vdl-trans

# alternativa: /usr/local/bin
ln -sf "/Users/carlos.vieira/Documents/Projects/vdl/bin/vdl-trans" /usr/local/bin/vdl-trans
```

O script resolve o repositório seguindo o symlink, então pode ser chamado de
**qualquer diretório**.

### Uso

```bash
vdl-trans "video.mp4"                 # 1 arquivo  → artefatos na pasta do arquivo
vdl-trans ~/Videos                    # pasta      → artefatos na própria pasta (recursivo)
vdl-trans aula.mp4 --model small      # troca o modelo (mais rápido)
VDL_MODEL=large vdl-trans aula.mp4    # modelo via variável de ambiente
vdl-trans aula.mp4 --context          # repassa flags extras ao vdl.py (aqui: --context)
vdl-trans --help                      # ajuda
```

- **Modelo padrão:** `medium`. Sobrescreva com `--model X` (logo após o alvo) ou com a env `VDL_MODEL`.
- **Flags extras** após o alvo são repassadas direto ao `vdl.py` (ex.: `--context`, `--gpu`).
- Os `logs/` do `vdl.py` caem dentro do repo (ignorado pelo git), não na sua pasta de trabalho.

---

## 5. Onde saem os artefatos

Para `-d <DEST>` (no `vdl-trans`, `DEST` = a pasta do alvo):

```
<DEST>/
├── mp3/<nome>.mp3              # áudio extraído (mono 16 kHz, alvo do Whisper)
└── transcriptions/<nome>.txt   # a transcrição em texto puro
```

No modo pasta, **um** `mp3/` e **um** `transcriptions/` agregam todos os vídeos
encontrados (o modelo é carregado uma única vez para o lote).

---

## 6. Modelos × velocidade × qualidade (CPU, Apple Silicon)

| Modelo | Velocidade | Qualidade | Quando usar |
|--------|-----------|-----------|-------------|
| `tiny`   | 🚀🚀🚀 | baixa        | rascunho/teste muito rápido |
| `base`   | 🚀🚀   | ok           | default do `vdl.py` |
| `small`  | 🚀     | boa          | bom equilíbrio para áudio limpo |
| `medium` | 🐢     | muito boa    | **default do `vdl-trans`** — melhor custo/benefício |
| `large`  | 🐢🐢   | a melhor     | máxima fidelidade, bem mais lento |

A 1ª execução de cada modelo **baixa o checkpoint** (ex.: `medium` ≈ 1,5 GB) e o
guarda em cache (`~/.cache/huggingface/...` por padrão). Para fixar o cache em outro
lugar, use a env `VDL_WHISPER_CACHE`.

---

## 7. Notas / troubleshooting

- **Pasta protegida do macOS (Downloads/Desktop/Documents).** O macOS (TCC) pode
  bloquear processos de ler arquivos nessas pastas até você **conceder permissão**
  (System Settings → Privacy & Security → Files and Folders / Full Disk Access para o
  seu terminal). No seu Terminal normal isso costuma já estar liberado; se aparecer
  `Operation not permitted` ao ler o vídeo, conceda o acesso ou mova o arquivo para
  uma pasta liberada.
- **`venv não encontrado`.** Rode o setup da Seção 2 (o `vdl-trans` aponta para
  `.venv-vdl/bin/python` dentro do repo).
- **Sem internet na 1ª vez.** É preciso baixar o modelo uma vez; depois roda offline.
- **`--gpu` no Mac.** Não tem efeito (sem CUDA); a transcrição usa CPU/int8.
- **`--context` / modo unificado.** Usam a API da OpenAI e exigem `OPENAI_API_KEY` —
  só a **transcrição** (`-t`) é 100% local.
