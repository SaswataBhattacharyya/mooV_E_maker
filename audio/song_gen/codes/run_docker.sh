#!/bin/bash
# Helper script to run the audio pipeline in Docker
# Usage: ./run_docker.sh [additional arguments for prepare_dataset.py]

set -e

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
DATA_DIR="$(dirname "$SCRIPT_DIR")/data"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if image exists, build if not
if ! docker image inspect audio-pipeline &> /dev/null; then
    echo "Building Docker image (this may take 10-15 minutes)..."
    docker build -t audio-pipeline "$SCRIPT_DIR"
fi

# Run the container with mounted data directory
echo "Running audio pipeline..."
docker run --rm \
    -v "$DATA_DIR:/app/data" \
    audio-pipeline \
    python prepare_dataset.py --data_dir /app/data "$@"
