FROM python:3.12-slim

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-core.txt .
RUN pip install --no-cache-dir -r requirements-core.txt
COPY src ./src
COPY manifests ./manifests
COPY runs ./runs
ENV PYTHONPATH=/app/src
ENTRYPOINT ["python", "-m", "video_audio_analyzer.cli"]
