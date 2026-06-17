"""Funções compartilhadas de transcrição entre vdl.py e subtitles.py.

Usa faster-whisper (CTranslate2): ~4x mais rápido que openai-whisper em CPU e
sem dependência de torch. Mantém o ponto único de carga do modelo, com:
- VDL_WHISPER_CACHE como download_root persistente (Docker).
- Detecção de CUDA (via ctranslate2) e fallback gracioso para CPU.
- compute_type dinâmico: float16 em CUDA, int8 (quantizado, rápido) em CPU.

Expõe um adapter compatível com a interface dict do openai-whisper
(result["text"], result["segments"], result["language"]) para não quebrar os
chamadores existentes (vdl.py usa ["text"]; subtitles.py usa ["segments"]/["language"]).
"""
import os

# Mapeia os nomes do seletor do Studio (tiny|base|small|medium|large) para os
# checkpoints do faster-whisper. 'large' -> 'large-v3' (melhor qualidade atual).
_MODEL_ALIASES = {
    "large": "large-v3",
}


def _cuda_available() -> bool:
    """CUDA disponível sem depender de torch (faster-whisper usa CTranslate2)."""
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


class _WhisperResultAdapter:
    """Adapta faster_whisper.WhisperModel à interface dict do openai-whisper."""

    def __init__(self, model):
        self._model = model

    def transcribe(self, audio_path, **_ignored):
        # Ignora kwargs do openai-whisper (fp16=, verbose=) que o faster-whisper
        # não aceita. segments é um gerador preguiçoso: iterar executa a transcrição.
        segments, info = self._model.transcribe(str(audio_path), beam_size=5)
        seg_list = []
        parts = []
        for seg in segments:
            seg_list.append({"start": seg.start, "end": seg.end, "text": seg.text})
            parts.append(seg.text)
        return {
            "text": "".join(parts).strip(),
            "segments": seg_list,
            "language": info.language,
        }


def load_whisper_model(model_name: str, use_gpu: bool = False):
    """Carrega o modelo via faster-whisper. Retorna (adapter, device).

    use_gpu=True com CUDA disponível -> device='cuda'; caso contrário, CPU.
    Respeita VDL_WHISPER_CACHE como download_root (cache persistente em Docker).
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError(f"Dependências de transcrição ausentes: {e}")

    device = "cuda" if use_gpu and _cuda_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    name = _MODEL_ALIASES.get(model_name, model_name)
    kwargs = {"device": device, "compute_type": compute_type}
    cache_dir = os.getenv("VDL_WHISPER_CACHE")
    if cache_dir:
        kwargs["download_root"] = cache_dir
    model = WhisperModel(name, **kwargs)
    return _WhisperResultAdapter(model), device


def fp16_for_device(device: str) -> bool:
    """Mantido por compatibilidade; fp16 só faz sentido em CUDA."""
    return device == "cuda"
