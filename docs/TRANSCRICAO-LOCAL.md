# Transcrição local (sem Docker) — `vdl-trans`

Como transcrever vídeos **localmente no macOS/Linux, sem Docker e sem VPN**, usando
o `vdl.py` com [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CPU) ou,
no Apple Silicon, [mlx-whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper)
na **GPU** (~9× mais rápido). Inclui o atalho `vdl-trans`.

> **TL;DR**
> ```bash
> # setup (uma vez)
> cd /Users/carlos.vieira/Documents/Projects/vdl
> python3.12 -m venv .venv-vdl && ./.venv-vdl/bin/pip install -r requirements.txt
> ./.venv-vdl/bin/pip install -r requirements-mac.txt   # opcional: GPU no Apple Silicon
> ln -sf "$PWD/bin/vdl-trans" ~/.local/bin/vdl-trans
>
> # uso
> vdl-trans "meu_video.mp4"     # transcreve 1 arquivo (usa a GPU no Mac, auto)
> vdl-trans ~/Videos            # transcreve a pasta inteira (recursivo)
> ```
> Artefatos saem **na própria pasta do alvo**: `transcriptions/<nome>.txt` e `mp3/<nome>.mp3`.

---

## 1. Pré-requisitos

| Requisito | Versão usada / observação |
|-----------|---------------------------|
| **Python** | **3.12** recomendado. Veja a nota abaixo sobre o 3.14. |
| **ffmpeg** | Já instalado via Homebrew: `/opt/homebrew/bin/ffmpeg` (v8.1). É o único pré-requisito de sistema. Instale com `brew install ffmpeg` se faltar. |
| **GPU (Apple Silicon)** | **Opcional, recomendado.** Com o extra `requirements-mac.txt` (mlx-whisper), a transcrição roda na GPU via Metal — bem mais rápida. Sem ele, roda em CPU. |
| **Internet** | Só na **primeira** execução de cada modelo, para baixá-lo (depois é 100% offline). |

### Por que Python 3.12 (e não o `python3` do sistema = 3.14)?

O faster-whisper e o mlx-whisper dependem de wheels nativos (`ctranslate2`, `av`,
`onnxruntime`, `mlx`, `torch`). Em jun/2026 esses pacotes ainda **não publicavam
wheels para Python 3.14**, então `python3 -m venv` (3.14) faria o `pip install`
falhar. Com **3.12** tudo instala via wheel pré-compilado. Qualquer Python
**3.10–3.13** serve; se você só tem o 3.14: `brew install python@3.12`.

---

## 2. Setup do venv (uma vez)

```bash
cd /Users/carlos.vieira/Documents/Projects/vdl
python3.12 -m venv .venv-vdl
./.venv-vdl/bin/pip install --upgrade pip
./.venv-vdl/bin/pip install -r requirements.txt        # base (faster-whisper/CPU)
./.venv-vdl/bin/pip install -r requirements-mac.txt    # opcional: GPU (Apple Silicon)
```

- `requirements.txt`: `openai`, `faster-whisper`, `pycryptodomex`, `pydub`, `yt-dlp`.
- `requirements-mac.txt`: `mlx-whisper` (GPU Metal) — **só macOS Apple Silicon**. O
  servidor/Docker (Linux) **não** usa este extra.
- O diretório `.venv-vdl/` está no `.gitignore` — **não é versionado**.

Sanidade (deve imprimir `imports OK`):

```bash
./.venv-vdl/bin/python -c "import faster_whisper, ctranslate2, av, openai, pydub; print('imports OK')"
```

---

## 3. O atalho `vdl-trans`

`bin/vdl-trans` é um wrapper que já assume os defaults bons para transcrição local:
destino = a própria pasta do alvo, modelo `medium` e **engine `auto`** (GPU no Mac,
senão CPU).

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
vdl-trans aula.mp4 --model small      # troca o modelo
vdl-trans aula.mp4 --engine cpu       # força faster-whisper (CPU)
VDL_MODEL=large VDL_ENGINE=mlx vdl-trans aula.mp4   # via variáveis de ambiente
vdl-trans aula.mp4 --context          # repassa flags extras ao vdl.py (aqui: --context)
vdl-trans --help
```

- **Modelo padrão:** `medium`. Sobrescreva com `--model X` (logo após o alvo) ou env `VDL_MODEL`.
- **Engine padrão:** `auto`. Sobrescreva com `--engine auto|mlx|cpu` ou env `VDL_ENGINE`.
- **Flags extras** após o alvo são repassadas ao `vdl.py`; como dependem do fluxo dele
  (ex.: `--context`, que usa a OpenAI), **forçam a engine `cpu`** automaticamente.
- Os `logs/` do `vdl.py` caem dentro do repo (ignorado pelo git), não na sua pasta de trabalho.

---

## 4. Engines: GPU (mlx) × CPU (faster-whisper)

| Engine | Backend | Onde roda | Velocidade |
|--------|---------|-----------|------------|
| `mlx`  | mlx-whisper (Metal) | **só Apple Silicon** | 🚀 GPU — ~9× mais rápida |
| `cpu`  | faster-whisper (int8) | qualquer CPU (= servidor/Docker) | baseline |
| `auto` | — | escolhe sozinho | mlx no Mac (se instalado), senão cpu |

**Benchmark** (M4 Max, áudio de 65 s, modelo `medium`):

| | faster-whisper (CPU/int8) | mlx-whisper (GPU/Metal) |
|---|---|---|
| Inferência (warm) | **30,9 s** (2,1× tempo real) | **3,3 s** (19,8× tempo real) |
| Qualidade | ✅ | ✅ (equivalente) |

→ Numa gravação de 1 h: **~30 min** em CPU vs **~3 min** na GPU.

Notas:
- A engine `mlx` usa a **GPU** (Metal), **não a NPU/ANE** (a ANE só via whisper.cpp/Core
  ML ou WhisperKit — bem mais setup, ganho marginal sobre a GPU).
- mlx é **macOS-only**: por isso fica restrita ao `vdl-trans`. O servidor/Docker (Linux)
  continua no faster-whisper, **inalterado**.
- Sem o `requirements-mac.txt` instalado, a engine `auto` cai em `cpu` e tudo segue
  funcionando; `--engine mlx` sem o pacote avisa e usa `cpu`.
- O modelo MLX padrão por tamanho é `mlx-community/whisper-<size>-mlx` (`large` →
  `large-v3`). Para usar outra variante (ex.: quantizada), exporte
  `VDL_MLX_MODEL=<repo HF ou caminho>`.

---

## 5. Onde saem os artefatos

Para `-d <DEST>` (no `vdl-trans`, `DEST` = a pasta do alvo):

```
<DEST>/
├── mp3/<nome>.mp3              # áudio extraído (mono 16 kHz, alvo do Whisper)
└── transcriptions/<nome>.txt   # a transcrição em texto puro
```

No modo pasta, **um** `mp3/` e **um** `transcriptions/` agregam todos os vídeos
encontrados (o modelo é carregado uma única vez para o lote, em ambas as engines).

---

## 6. Modelos × velocidade × qualidade

| Modelo | Velocidade | Qualidade | Quando usar |
|--------|-----------|-----------|-------------|
| `tiny`   | 🚀🚀🚀 | baixa        | rascunho/teste muito rápido |
| `base`   | 🚀🚀   | ok           | default do `vdl.py` |
| `small`  | 🚀     | boa          | bom equilíbrio para áudio limpo |
| `medium` | 🐢*    | muito boa    | **default do `vdl-trans`** — melhor custo/benefício |
| `large`  | 🐢🐢*  | a melhor     | máxima fidelidade |

\* Na GPU (engine `mlx`), até `medium`/`large` ficam rápidos — veja o benchmark acima.

A 1ª execução de cada modelo **baixa o checkpoint** (ex.: `medium` ≈ 1,5 GB) e o guarda
em cache (`~/.cache/huggingface/...`). Para a engine CPU, dá para fixar o cache do
faster-whisper com a env `VDL_WHISPER_CACHE`.

---

## 7. Uso direto do `vdl.py` (sem o wrapper)

```bash
# 1 arquivo (faster-whisper/CPU)
./.venv-vdl/bin/python vdl.py "caminho/video.mp4" \
  --local --transcribe -d "caminho" --whisper-model medium

# pasta inteira (busca recursiva por .mp4 .mkv .mov .webm .m4v)
./.venv-vdl/bin/python vdl.py "caminho/pasta" \
  --local --transcribe -d "caminho/pasta" --whisper-model medium

# engine GPU (Apple Silicon) — módulo dedicado, mesmo layout de saída
./.venv-vdl/bin/python _transcription_mlx.py "caminho/video.mp4" \
  -d "caminho" --whisper-model medium
```

| Flag (`vdl.py`) | Função |
|------|--------|
| `-l, --local` | Processa arquivo/pasta já existente (sem download). |
| `-t, --transcribe` | Transcreve **localmente** (faster-whisper). |
| `-d, --directory` | Pasta de **saída** dos artefatos. |
| `--whisper-model` | `tiny` · `base` · `small` · `medium` · `large` (padrão do vdl.py: `base`). |
| `-c, --context` | (Opcional) gera resumo/contexto via OpenAI. **Requer `OPENAI_API_KEY`.** |

---

## 8. Notas / troubleshooting

- **Pasta protegida do macOS (Downloads/Desktop/Documents).** O macOS (TCC) pode
  bloquear processos de ler arquivos nessas pastas até você **conceder permissão**
  (System Settings → Privacy & Security → Files and Folders / Full Disk Access para o
  seu terminal). No seu Terminal normal isso costuma já estar liberado; se aparecer
  `Operation not permitted` ao ler o vídeo, conceda o acesso ou mova o arquivo.
- **`venv não encontrado`.** Rode o setup da Seção 2 (o `vdl-trans` aponta para
  `.venv-vdl/bin/python` dentro do repo).
- **Sem internet na 1ª vez.** É preciso baixar o modelo uma vez; depois roda offline.
- **`--context` / modo unificado.** Usam a API da OpenAI e exigem `OPENAI_API_KEY` —
  só a **transcrição** (`-t` / engines mlx e cpu) é 100% local.
