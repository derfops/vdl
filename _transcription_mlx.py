#!/usr/bin/env python3
"""Engine de transcrição LOCAL via mlx-whisper (GPU Apple/Metal) — só macOS.

Alternativa OPCIONAL ao faster-whisper, usada apenas pelo atalho `vdl-trans`
quando a engine 'mlx' é selecionada. NÃO é importada nem executada pelo
servidor/Docker (Linux), que continua no faster-whisper (`_transcription.py`):
este módulo só roda como __main__, disparado pelo vdl-trans no Mac.

Mantém o MESMO layout de saída do vdl.py (reutilizando `vdl.extract_audio`):
  <dest>/mp3/<nome>.mp3             (áudio extraído — mono 16 kHz)
  <dest>/transcriptions/<nome>.txt  (transcrição em texto puro)

Aceita arquivo OU pasta (busca recursiva), espelhando o modo --local do vdl.py.
"""
import argparse
import os
import sys
from pathlib import Path

# Reutiliza extração de áudio e helpers de log do vdl.py (mesmo repositório).
# Importar 'vdl' como módulo é seguro: define funções e não executa main().
import vdl

# Mesmas extensões que o vdl.py varre no modo --local com diretório.
_VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".webm", ".m4v"}

# Mapeia o seletor de tamanho (igual ao --whisper-model do vdl.py) para os
# checkpoints MLX da comunidade. Sobrescrevível por VDL_MLX_MODEL (repo HF
# ou caminho local), para usar variantes quantizadas (ex.: ...-mlx-q4) etc.
_MLX_MODELS = {
    "tiny": "mlx-community/whisper-tiny-mlx",
    "base": "mlx-community/whisper-base-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "large": "mlx-community/whisper-large-v3-mlx",
}


def _resolve_repo(model_name):
    """Repo/caminho do modelo MLX para o tamanho pedido (env tem precedência)."""
    return os.getenv("VDL_MLX_MODEL") or _MLX_MODELS.get(model_name, model_name)


def transcribe_one(transcribe_fn, video_path, output_dir, repo):
    """Extrai o áudio (via vdl.extract_audio) e transcreve com mlx-whisper.

    Retorna o texto (str, possivelmente vazio para áudio sem fala) ou None se
    a extração/transcrição falhar — mesma semântica do vdl.py."""
    audio_path = vdl.extract_audio(video_path, output_dir)
    if not audio_path:
        vdl.print_error(f"Pulado por falha na extração de áudio: {video_path}")
        return None

    transcription_dir = os.path.join(output_dir, "transcriptions")
    os.makedirs(transcription_dir, exist_ok=True)
    transcription_path = os.path.join(
        transcription_dir,
        os.path.basename(os.path.splitext(audio_path)[0] + ".txt"),
    )
    vdl.print_info(f"Iniciando a transcrição LOCAL (mlx/GPU) para: {transcription_path}")
    try:
        result = transcribe_fn(audio_path, path_or_hf_repo=repo)
        text = (result.get("text") or "").strip()
        with open(transcription_path, "w", encoding="utf-8") as f:
            f.write(text)
        vdl.print_success(f"Transcrição local (mlx) salva em: {transcription_path}")
        return text
    except Exception as e:
        vdl.print_error(f"Ocorreu um erro durante a transcrição mlx: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        prog="vdl-trans (mlx)",
        description="Transcrição local com mlx-whisper (GPU Apple/Metal).",
    )
    parser.add_argument("input", help="Arquivo de vídeo ou pasta (busca recursiva).")
    parser.add_argument("-d", "--directory", default=".", help="Diretório de saída.")
    parser.add_argument(
        "--whisper-model", default="large",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Tamanho do modelo Whisper (mapeado para o checkpoint MLX).",
    )
    args = parser.parse_args()

    try:
        from mlx_whisper import transcribe as mlx_transcribe
    except Exception as e:
        vdl.print_error(
            f"mlx-whisper não disponível: {e}. "
            f"Instale com: ./.venv-vdl/bin/pip install mlx-whisper"
        )
        sys.exit(1)

    repo = _resolve_repo(args.whisper_model)
    dest = args.directory if args.directory.strip() else "."
    inp = args.input

    if os.path.isdir(inp):
        try:
            videos = sorted(
                (str(p) for p in Path(inp).rglob("*")
                 if p.is_file() and p.suffix.lower() in _VIDEO_EXTS),
                key=str.lower,
            )
        except OSError as e:
            vdl.print_error(f"Falha ao listar diretório '{inp}': {e}")
            sys.exit(1)
        if not videos:
            vdl.print_error(
                f"Nenhum vídeo encontrado (busca recursiva) em: {os.path.abspath(inp)}"
            )
            sys.exit(1)
        vdl.print_info(f"Encontrados {len(videos)} vídeo(s) (recursivo) em: {os.path.abspath(inp)}")
        vdl.print_info(f"Engine: mlx-whisper (GPU) · modelo: {repo}")
        # mlx_whisper.transcribe cacheia o modelo por repo (lru_cache): em lote,
        # carrega uma única vez e reutiliza nos arquivos seguintes.
        ok = 0
        for idx, vp in enumerate(videos, start=1):
            vdl.print_info(f"[{idx}/{len(videos)}] Processando: {vp}")
            if transcribe_one(mlx_transcribe, vp, dest, repo) is not None:
                ok += 1
        if ok == 0:
            vdl.print_error("Nenhum vídeo transcrito com sucesso.")
            sys.exit(1)
    elif os.path.isfile(inp):
        vdl.print_info(f"Engine: mlx-whisper (GPU) · modelo: {repo}")
        if transcribe_one(mlx_transcribe, inp, dest, repo) is None:
            vdl.print_error("Transcrição local (mlx) falhou: nenhum texto gerado.")
            sys.exit(1)
    else:
        vdl.print_error(f"Arquivo ou diretório local não encontrado: {inp}")
        sys.exit(1)


if __name__ == "__main__":
    main()
