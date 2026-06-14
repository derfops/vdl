FROM python:3.11-alpine

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apk add --no-cache bash curl docker-cli docker-cli-compose

WORKDIR /app
COPY studio/api/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY studio/api/app.py /app/app.py
COPY studio/api/orchestrator.py /app/orchestrator.py
COPY studio/api/auth.py /app/auth.py

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
