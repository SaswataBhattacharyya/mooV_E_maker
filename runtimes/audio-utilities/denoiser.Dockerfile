FROM setup_comfy_and-stuff-comfyui:latest
COPY audio/denoiser /opt/denoiser
RUN /opt/comfy/bin/python -m pip install --no-cache-dir hydra-core==1.3.2 hydra-colorlog julius pystoi soundfile && /opt/comfy/bin/python -m pip install --no-cache-dir --no-deps -e /opt/denoiser
COPY runtimes/audio-utilities/denoiser_sitecustomize.py /opt/comfy/lib/python3.12/site-packages/denoiser_runtime_compat.py
ENV PATH="/opt/comfy/bin:${PATH}"
WORKDIR /workspace
