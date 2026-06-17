FROM python:3.11-slim
ENV TZ=America/Sao_Paulo
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
ARG OPENAI_API_KEY=""
ENV OPENAI_API_KEY=${OPENAI_API_KEY}
ARG DEBIAN_FRONTEND=noninteractive
ARG APT_CACHE_BUST=1
# ffmpeg + curl para checkup; ca-certificates+tzdata mínimos.
# Demais ferramentas de rede (dnsutils, whois, etc.) movidas para imagem
# de debug separada se necessário (aqui buscamos imagem enxuta).
RUN echo $APT_CACHE_BUST && set -eux; for i in 1 2 3; do \
    apt-get update && apt-get install -y --no-install-recommends \
    bash ffmpeg curl ca-certificates tzdata && break || sleep 5; \
    done; \
    ln -sf /usr/share/zoneinfo/$TZ /etc/localtime && dpkg-reconfigure -f noninteractive tzdata; \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt /app/requirements.txt
# Torch em wheel CPU-only (~750MB vs ~2.5GB CUDA). Para GPU, sobreponha em
# build-arg/runtime substituindo o pip install do torch.
RUN pip install --upgrade pip && \
    pip install --extra-index-url https://download.pytorch.org/whl/cpu torch && \
    pip install -r requirements.txt
COPY vdl.py /app/vdl.py
COPY subtitles.py /app/subtitles.py
# Modulo compartilhado de transcricao (Whisper) importado por vdl.py e subtitles.py.
# Sem ele, `from _transcription import load_whisper_model` quebra e a transcricao
# local falha silenciosamente (o job ainda sai 0 e aparece como "Concluido").
COPY _transcription.py /app/_transcription.py
COPY vdl_studio /app/vdl_studio
COPY prompts /app/prompts
COPY checkup.py /opt/vdl/checkup.py
COPY docs/HOWTO.md /opt/vdl/HOWTO.md
RUN chmod +x /app/vdl.py /app/subtitles.py && ln -s /app/vdl.py /usr/local/bin/vdl && ln -s /app/subtitles.py /usr/local/bin/subtitles
# Cache persistente do Whisper: monte volume em /cache/whisper para evitar
# re-download do modelo a cada container restart (medium ~1.5GB, large ~3GB).
ENV VDL_WHISPER_CACHE=/cache/whisper
RUN mkdir -p /cache/whisper
WORKDIR /data
CMD ["/bin/bash"]
