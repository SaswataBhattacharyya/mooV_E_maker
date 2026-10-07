# StyleTTS2 Fine-tuning Docker Image
# Supports GPU training with CUDA

FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV CUDA_HOME=/usr/local/cuda
ENV PATH=${CUDA_HOME}/bin:${PATH}
ENV LD_LIBRARY_PATH=${CUDA_HOME}/lib64:${LD_LIBRARY_PATH}

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3.10-dev \
    python3-pip \
    git \
    wget \
    curl \
    espeak-ng \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Create symlink for python
RUN ln -s /usr/bin/python3.10 /usr/bin/python

# Upgrade pip
RUN pip3 install --upgrade pip setuptools wheel

# Install PyTorch with CUDA 11.8 support
RUN pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Install StyleTTS2 core dependencies
RUN pip3 install \
    SoundFile \
    munch \
    pydub \
    pyyaml \
    librosa \
    nltk \
    matplotlib \
    accelerate \
    transformers \
    einops \
    einops-exts \
    tqdm \
    typing-extensions \
    phonemizer \
    torchaudio

# Install monotonic_align from git
RUN pip3 install git+https://github.com/resemble-ai/monotonic_align.git

# Install fine-tuning orchestration dependencies
RUN pip3 install \
    pyyaml \
    torchaudio \
    tqdm

# Set working directory
WORKDIR /workspace

# Create directories for data and outputs
RUN mkdir -p /workspace/finetune_project/{data,output,work} \
    && mkdir -p /workspace/StyleTTS2_app

# Copy fine-tuning scripts (will be mounted at runtime, but good to have structure)
# Note: Actual code will be mounted via volumes in docker-compose or docker run

# Default command (can be overridden)
CMD ["/bin/bash"]

