#!/bin/bash
# Verify Docker setup for StyleTTS2 fine-tuning

set -e

echo "🔍 Verifying StyleTTS2 Fine-tuning Setup"
echo "========================================="
echo ""

ERRORS=0

# Check Docker
echo "1. Checking Docker..."
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version)
    echo "   ✅ Docker installed: $DOCKER_VERSION"
else
    echo "   ❌ Docker not found. Install from: https://docs.docker.com/get-docker/"
    ERRORS=$((ERRORS + 1))
fi

# Check NVIDIA Container Toolkit
echo ""
echo "2. Checking NVIDIA Container Toolkit..."
if docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi &> /dev/null; then
    echo "   ✅ GPU access available"
    GPU_AVAILABLE=true
else
    echo "   ⚠️  GPU access not available"
    echo "      Install: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
    GPU_AVAILABLE=false
fi

# Check StyleTTS2 directory
echo ""
echo "3. Checking StyleTTS2 repository..."
# Go up two levels from finetune_model to get to audio/, then into StyleTTS2
FINETUNE_DIR="$(dirname "$0")"
AUDIO_DIR="$(cd "$FINETUNE_DIR/../.." && pwd)"
STYLETTS2_DIR="$AUDIO_DIR/StyleTTS2"

if [ -d "$STYLETTS2_DIR" ]; then
    echo "   ✅ StyleTTS2 directory: $STYLETTS2_DIR"
    
    # Check for required files
    if [ -f "$STYLETTS2_DIR/Configs/config_ft.yml" ]; then
        echo "   ✅ Config file found: config_ft.yml"
    else
        echo "   ❌ Missing: Configs/config_ft.yml"
        ERRORS=$((ERRORS + 1))
    fi
    
    if [ -d "$STYLETTS2_DIR/Utils/ASR" ] && [ -d "$STYLETTS2_DIR/Utils/JDC" ] && [ -d "$STYLETTS2_DIR/Utils/PLBERT" ]; then
        echo "   ✅ Utils directories found"
    else
        echo "   ⚠️  Missing Utils directories (ASR, JDC, PLBERT)"
        echo "      Download from: https://github.com/yl4579/StyleTTS2"
    fi
    
    # Check for checkpoint (accept multiple possible names)
    CHECKPOINT_FOUND=false
    CHECKPOINT_NAME=""
    
    # Check for styletts2.pth (common name)
    if [ -f "$STYLETTS2_DIR/checkpoints/styletts2.pth" ]; then
        CHECKPOINT_FOUND=true
        CHECKPOINT_NAME="styletts2.pth"
    # Check for epochs_2nd_00020.pth (original name)
    elif [ -f "$STYLETTS2_DIR/checkpoints/epochs_2nd_00020.pth" ]; then
        CHECKPOINT_FOUND=true
        CHECKPOINT_NAME="epochs_2nd_00020.pth"
    # Check for any .pth file in checkpoints directory
    elif [ -f "$STYLETTS2_DIR/checkpoints"/*.pth ] 2>/dev/null; then
        CHECKPOINT_FOUND=true
        CHECKPOINT_NAME=$(basename "$STYLETTS2_DIR/checkpoints"/*.pth | head -n1)
    fi
    
    if [ "$CHECKPOINT_FOUND" = true ]; then
        echo "   ✅ Base checkpoint found: checkpoints/$CHECKPOINT_NAME"
    else
        echo "   ⚠️  Base checkpoint not found in checkpoints/ directory"
        echo "      Expected: styletts2.pth or epochs_2nd_00020.pth"
        echo "      Download from: https://huggingface.co/yl4579/StyleTTS2-LibriTTS"
    fi
else
    echo "   ❌ StyleTTS2 directory not found at: $STYLETTS2_DIR"
    ERRORS=$((ERRORS + 1))
fi

# Check fine-tuning scripts
echo ""
echo "4. Checking fine-tuning scripts..."
FINETUNE_DIR="$(dirname "$0")"
if [ -f "$FINETUNE_DIR/preprocess_dataset.py" ]; then
    echo "   ✅ preprocess_dataset.py found"
else
    echo "   ⚠️  preprocess_dataset.py not in finetune_model/ (should be in StyleTTS2_app/finetune_model/)"
fi

if [ -f "$FINETUNE_DIR/finetune_multi.py" ]; then
    echo "   ✅ finetune_multi.py found"
else
    echo "   ⚠️  finetune_multi.py not in finetune_model/ (should be in StyleTTS2_app/finetune_model/)"
fi

# Check Docker image
echo ""
echo "5. Checking Docker image..."
if docker images | grep -q "styletts2-finetune"; then
    echo "   ✅ Docker image 'styletts2-finetune' exists"
else
    echo "   ⚠️  Docker image not built yet"
    echo "      Run: cd $FINETUNE_DIR && docker build -t styletts2-finetune:latest -f Dockerfile ../.."
fi

# Check data directory
echo ""
echo "6. Checking data directory..."
DATA_DIR="$FINETUNE_DIR/finetune_project/data"
if [ -d "$DATA_DIR" ] && [ -d "$DATA_DIR/audio" ] && [ -d "$DATA_DIR/text" ]; then
    AUDIO_COUNT=$(find "$DATA_DIR/audio" -type f 2>/dev/null | wc -l)
    TEXT_COUNT=$(find "$DATA_DIR/text" -type f 2>/dev/null | wc -l)
    echo "   ✅ Data directory structure exists"
    echo "      Audio files: $AUDIO_COUNT"
    echo "      Text files: $TEXT_COUNT"
    
    if [ "$AUDIO_COUNT" -eq 0 ] || [ "$TEXT_COUNT" -eq 0 ]; then
        echo "   ⚠️  No data files found. Add your audio/text pairs to:"
        echo "      $DATA_DIR/audio/"
        echo "      $DATA_DIR/text/"
    fi
else
    echo "   ⚠️  Data directory not set up"
    echo "      Create: $DATA_DIR/{audio,text}/"
fi

# Summary
echo ""
echo "========================================="
if [ $ERRORS -eq 0 ]; then
    echo "✅ Setup looks good!"
    if [ "$GPU_AVAILABLE" = false ]; then
        echo "⚠️  Note: GPU not available - training will be slow on CPU"
    fi
    echo ""
    echo "Next steps:"
    echo "1. Prepare your audio/text data in: $DATA_DIR/"
    echo "2. Download base checkpoint if missing"
    echo "3. Run: ./quick_start.sh"
else
    echo "❌ Found $ERRORS critical issue(s). Please fix them before proceeding."
    exit 1
fi

