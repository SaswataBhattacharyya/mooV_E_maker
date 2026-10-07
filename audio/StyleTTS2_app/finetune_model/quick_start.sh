#!/bin/bash
# Quick start script for StyleTTS2 fine-tuning with Docker

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FINETUNE_DIR="$SCRIPT_DIR"
# Go up two levels to get to audio/ directory
AUDIO_DIR="$(cd "$FINETUNE_DIR/../.." && pwd)"
STYLETTS2_DIR="$AUDIO_DIR/StyleTTS2"
STYLETTS2_APP_DIR="$AUDIO_DIR/StyleTTS2_app"
DATA_DIR="$FINETUNE_DIR/finetune_project/data"
WORK_DIR="$FINETUNE_DIR/finetune_project/work"
OUTPUT_DIR="$FINETUNE_DIR/finetune_project/output"

echo "🚀 StyleTTS2 Fine-tuning Quick Start"
echo "===================================="
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if nvidia-docker is available
if ! docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi &> /dev/null; then
    echo "⚠️  Warning: GPU access not available. Training will be slow on CPU."
    echo "   Install NVIDIA Container Toolkit: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
    GPU_FLAG=""
else
    GPU_FLAG="--gpus all"
    echo "✅ GPU access confirmed"
fi

# Check if data directory exists
if [ ! -d "$DATA_DIR" ] || [ -z "$(ls -A $DATA_DIR/audio 2>/dev/null)" ]; then
    echo "❌ Data directory not found or empty: $DATA_DIR/audio"
    echo "   Please create the directory structure:"
    echo "   $DATA_DIR/"
    echo "   ├── audio/"
    echo "   │   ├── Dipa_1.mp3"
    echo "   │   └── ..."
    echo "   └── text/"
    echo "       ├── Dipa_1.txt"
    echo "       └── ..."
    exit 1
fi

echo "✅ Data directory found: $DATA_DIR"
echo ""

# Build Docker image
echo "📦 Building Docker image..."
cd "$FINETUNE_DIR"
# Build from audio directory (parent of both StyleTTS2 and StyleTTS2_app)
docker build -t styletts2-finetune:latest -f Dockerfile "$AUDIO_DIR" || {
    echo "❌ Docker build failed"
    exit 1
}
echo "✅ Docker image built successfully"
echo ""

# Create output directories
mkdir -p "$WORK_DIR" "$OUTPUT_DIR"

# Check for base checkpoint (accept multiple possible names)
CHECKPOINT_FILENAME=""
if [ -f "$STYLETTS2_DIR/checkpoints/styletts2.pth" ]; then
    CHECKPOINT_FILENAME="styletts2.pth"
    echo "✅ Found checkpoint: styletts2.pth"
elif [ -f "$STYLETTS2_DIR/checkpoints/epochs_2nd_00020.pth" ]; then
    CHECKPOINT_FILENAME="epochs_2nd_00020.pth"
    echo "✅ Found checkpoint: epochs_2nd_00020.pth"
else
    echo "⚠️  Warning: Base checkpoint not found"
    echo "   Expected: styletts2.pth or epochs_2nd_00020.pth in $STYLETTS2_DIR/checkpoints/"
    echo "   Please download from: https://huggingface.co/yl4579/StyleTTS2-LibriTTS"
    echo "   Or use: huggingface-cli download yl4579/StyleTTS2-LibriTTS epochs_2nd_00020.pth --local-dir $STYLETTS2_DIR/checkpoints"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
    # Try to find any .pth file as fallback
    FOUND_CHECKPOINT=$(find "$STYLETTS2_DIR/checkpoints" -name "*.pth" -type f 2>/dev/null | head -n1)
    if [ -n "$FOUND_CHECKPOINT" ]; then
        CHECKPOINT_FILENAME=$(basename "$FOUND_CHECKPOINT")
        echo "   Using found checkpoint: $CHECKPOINT_FILENAME"
    else
        echo "   ❌ No checkpoint found. Fine-tuning will fail."
        exit 1
    fi
fi

# Ask user what to do
echo "What would you like to do?"
echo "1) Preprocess data only"
echo "2) Run fine-tuning only (assumes preprocessing done)"
echo "3) Preprocess + Fine-tune (full pipeline)"
read -p "Enter choice [1-3]: " choice

case $choice in
    1)
        echo ""
        echo "🔄 Running preprocessing..."
        docker run -it --rm $GPU_FLAG \
            -v "$STYLETTS2_DIR:/workspace/StyleTTS2:ro" \
            -v "$STYLETTS2_APP_DIR:/workspace/StyleTTS2_app:ro" \
            -v "$DATA_DIR:/workspace/finetune_project/data:ro" \
            -v "$WORK_DIR:/workspace/finetune_project/work" \
            styletts2-finetune:latest \
            python /workspace/StyleTTS2_app/finetune_model/preprocess_dataset.py \
                --data_root /workspace/finetune_project/data \
                --work_dir /workspace/finetune_project/work \
                --sr 24000 \
                --val_ratio 0.05
        ;;
    2)
        echo ""
        echo "🎯 Running fine-tuning..."
        docker run -it --rm $GPU_FLAG \
            -v "$STYLETTS2_DIR:/workspace/StyleTTS2:ro" \
            -v "$STYLETTS2_APP_DIR:/workspace/StyleTTS2_app:ro" \
            -v "$WORK_DIR:/workspace/finetune_project/work:ro" \
            -v "$OUTPUT_DIR:/workspace/finetune_project/output" \
            styletts2-finetune:latest \
            python /workspace/StyleTTS2_app/finetune_model/finetune_multi.py \
                --styletts2_repo /workspace/StyleTTS2 \
                --work_dir /workspace/finetune_project/work \
                --out_dir /workspace/finetune_project/output \
                --base_checkpoint /workspace/StyleTTS2/checkpoints/$CHECKPOINT_FILENAME \
                --base_config /workspace/StyleTTS2/Configs/config_ft.yml \
                --epochs 50 \
                --batch_size 4 \
                --use_accelerate
        ;;
    3)
        echo ""
        echo "🔄 Step 1/2: Preprocessing..."
        docker run -it --rm $GPU_FLAG \
            -v "$STYLETTS2_DIR:/workspace/StyleTTS2:ro" \
            -v "$STYLETTS2_APP_DIR:/workspace/StyleTTS2_app:ro" \
            -v "$DATA_DIR:/workspace/finetune_project/data:ro" \
            -v "$WORK_DIR:/workspace/finetune_project/work" \
            styletts2-finetune:latest \
            python /workspace/StyleTTS2_app/finetune_model/preprocess_dataset.py \
                --data_root /workspace/finetune_project/data \
                --work_dir /workspace/finetune_project/work \
                --sr 24000 \
                --val_ratio 0.05
        
        echo ""
        echo "🎯 Step 2/2: Fine-tuning..."
        docker run -it --rm $GPU_FLAG \
            -v "$STYLETTS2_DIR:/workspace/StyleTTS2:ro" \
            -v "$STYLETTS2_APP_DIR:/workspace/StyleTTS2_app:ro" \
            -v "$WORK_DIR:/workspace/finetune_project/work:ro" \
            -v "$OUTPUT_DIR:/workspace/finetune_project/output" \
            styletts2-finetune:latest \
            python /workspace/StyleTTS2_app/finetune_model/finetune_multi.py \
                --styletts2_repo /workspace/StyleTTS2 \
                --work_dir /workspace/finetune_project/work \
                --out_dir /workspace/finetune_project/output \
                --base_checkpoint /workspace/StyleTTS2/checkpoints/$CHECKPOINT_FILENAME \
                --base_config /workspace/StyleTTS2/Configs/config_ft.yml \
                --epochs 50 \
                --batch_size 4 \
                --use_accelerate
        ;;
    *)
        echo "❌ Invalid choice"
        exit 1
        ;;
esac

echo ""
echo "✅ Done! Check output directory: $OUTPUT_DIR"

