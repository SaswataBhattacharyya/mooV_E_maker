FROM setup_comfy_and-stuff-comfyui:latest
RUN /opt/comfy/bin/python -m pip install --no-cache-dir demucs==4.0.1 torchcodec
ENV PATH="/opt/comfy/bin:${PATH}"
WORKDIR /workspace
