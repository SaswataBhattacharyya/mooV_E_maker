# Dockerfile for Audio Dataset Preparation Pipeline
# Base image with Python 3.10
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Note: Essentia may need to be installed separately if pip install fails
# You can uncomment and modify the following if you need to build Essentia from source:
# RUN git clone https://github.com/MTG/essentia.git /tmp/essentia && \
#     cd /tmp/essentia && \
#     python waf configure --build-static && \
#     python waf && \
#     python waf install && \
#     rm -rf /tmp/essentia

# Copy the entire codes directory
COPY . .

# Set Python path and default data directory
ENV PYTHONPATH=/app:$PYTHONPATH
ENV DEFAULT_DATA_DIR=/app/data

# Default command (can be overridden)
CMD ["python", "prepare_dataset.py", "--data_dir", "/app/data"]
