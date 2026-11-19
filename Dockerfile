# VPS image: recorder, chat, radar, ingest, heatmap, scheduler, publishers, analytics and the dashboard (doc 25).
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg tesseract-ocr postgresql-client && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml ./
COPY clipping ./clipping
COPY config ./config
COPY sql ./sql
COPY assets ./assets
COPY eval ./eval
RUN pip install --no-cache-dir -e . && pip install --no-cache-dir boto3
ENV CLIPPING_DATA_DIR=/data PYTHONUNBUFFERED=1
VOLUME /data
CMD ["clip", "worker", "server"]
