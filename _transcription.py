"""Funções compartilhadas de transcrição entre vdl.py e subtitles.py.

Mantém o ponto único de carga do modelo Whisper, com suporte a:
- VDL_WHISPER_CACHE para download_root persistente (Docker).
- Detecção de GPU (CUDA) e fallback gracioso para CPU.
- fp16 dinâmico baseado no device.
"""
import os
from typing import Tuple, Optional


def load_whisper_model(model_name: str, use_gpu: bool = False):
    """Carrega o modelo Whisper. Retorna (model, device) ou (None, None).

    use_gpu=True com CUDA disponível -> device='cuda'; caso contrário, CPU.
    Respeita VDL_WHISPER_CACHE como download_root (útil em Docker).
    """
    try:
        import torch
        import whisper
    except ImportError as e:
        raise RuntimeError(f"Dependências de transcrição ausentes: {e}")

    device = "cuda" if use_gpu and torch.cuda.is_available() else "cpu"
    cache_dir = os.getenv("VDL_WHISPER_CACHE")
    kwargs = {"device": device}
    if cache_dir:
        kwargs["download_root"] = cache_dir
    model = whisper.load_model(model_name, **kwargs)
    return model, device


def fp16_for_device(device: str) -> bool:
    """fp16 só faz sentido em CUDA; em CPU o whisper exige fp32."""
    return device == "cuda"
