# Models Required

## checkpoints
# wget https://huggingface.co/Comfy-Org/ACE-Step_ComfyUI_repackaged/resolve/main/all_in_one/ace_step_v1_3.5b.safetensors
# wget https://huggingface.co/Lightricks/LTX-2/resolve/main/ltx-2-19b-distilled-fp8.safetensors
# larger / alternate LTX checkpoints
# wget https://huggingface.co/Lightricks/LTX-2/resolve/main/ltx-2-19b-distilled.safetensors
wget https://huggingface.co/Lightricks/LTX-2/resolve/main/ltx-2-19b-dev-fp8.safetensors
# wget https://huggingface.co/Lightricks/LTX-2/resolve/main/ltx-2-19b-dev.safetensors
wget https://huggingface.co/Lightricks/LTX-2.3-fp8/resolve/main/ltx-2.3-22b-distilled-fp8.safetensors
wget https://huggingface.co/Lightricks/LTX-2.3-fp8/resolve/main/ltx-2.3-22b-dev-fp8.safetensors

## unet
# GGUF alternatives for ComfyUI-GGUF. These go in ComfyUI/models/unet.
# 24 GB VRAM oriented picks: Q4_K_M is the usual balance pick, Q5_K_M is higher quality, Q6_K is optional if you have some headroom.

# Qwen Image 2512 GGUF
# GGUF1 - wget https://huggingface.co/unsloth/Qwen-Image-2512-GGUF/resolve/main/qwen-image-2512-Q4_K_M.gguf
# GGUF2 - wget https://huggingface.co/unsloth/Qwen-Image-2512-GGUF/resolve/main/qwen-image-2512-Q5_K_M.gguf
# GGUF3 - wget https://huggingface.co/unsloth/Qwen-Image-2512-GGUF/resolve/main/qwen-image-2512-Q6_K.gguf

# Qwen Image Edit 2511 GGUF
# GGUF1 - wget https://huggingface.co/unsloth/Qwen-Image-Edit-2511-GGUF/resolve/main/qwen-image-edit-2511-Q4_K_M.gguf
# GGUF2 - wget https://huggingface.co/unsloth/Qwen-Image-Edit-2511-GGUF/resolve/main/qwen-image-edit-2511-Q5_K_M.gguf
# GGUF3 - wget https://huggingface.co/unsloth/Qwen-Image-Edit-2511-GGUF/resolve/main/qwen-image-edit-2511-Q6_K.gguf

# LTX-2 GGUF
# GGUF1 - wget https://huggingface.co/unsloth/LTX-2-GGUF/resolve/main/ltx-2-19b-dev-Q4_K_M.gguf
# GGUF2 - wget https://huggingface.co/unsloth/LTX-2-GGUF/resolve/main/ltx-2-19b-dev-Q5_K_M.gguf
# GGUF3 - wget https://huggingface.co/unsloth/LTX-2-GGUF/resolve/main/ltx-2-19b-dev-Q6_K.gguf

# LTX-2.3 GGUF
# GGUF1 - wget https://huggingface.co/unsloth/LTX-2.3-GGUF/resolve/main/ltx-2.3-22b-dev-Q4_K_M.gguf
# GGUF2 - wget https://huggingface.co/unsloth/LTX-2.3-GGUF/resolve/main/ltx-2.3-22b-dev-Q5_K_M.gguf

# wget https://huggingface.co/QuantStack/Wan2.2-Animate-14B-GGUF/resolve/main/Wan2.2-Animate-14B-Q8_0.gguf
# workflow uses wan-14B_vace_skyreels_v3_R2V_e4m3fn_v1-Q4_K_M.gguf; verified same-family VACE GGUF replacement:
# wget https://huggingface.co/QuantStack/Wan2.1_14B_VACE-GGUF/resolve/main/Wan2.1_14B_VACE-Q4_K_M.gguf

## diffusion_models
wget https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_2512_fp8_e4m3fn.safetensors
# larger duplicate precision of the same base model
# wget https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_2512_bf16.safetensors

# wget https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_edit_2511_bf16.safetensors
wget https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_edit_2509_fp8_e4m3fn.safetensors
# wget https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/diffusion_models/wan2.1_fun_control_1.3B_bf16.safetensors
# wget https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_fun_inpaint_high_noise_14B_fp8_scaled.safetensors
# wget https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_fun_inpaint_low_noise_14B_fp8_scaled.safetensors
# wget https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors
# wget https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors
# wget https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors
# wget https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors
wget https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/diffusion_models/z_image_turbo_bf16.safetensors
# wget https://huggingface.co/Inner-Reflections/VACE_Skyreels_V3_R2V_Merge/resolve/main/wan-14B_vace_skyreels_v3_R2V_e4m3fn_v1.safetensors

## text_encoders
wget https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors
wget https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors
# duplicate source for the same text encoder
# wget https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors

wget https://huggingface.co/Comfy-Org/ltx-2/resolve/main/split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors
# duplicate / same-family higher precision encoder from workflows/LTX2
# wget https://huggingface.co/Comfy-Org/ltx-2/resolve/main/split_files/text_encoders/gemma_3_12B_it.safetensors
wget https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/text_encoders/qwen_3_4b.safetensors
# ComfyUI-LTXVideo Gemma loader uses the full repo layout under
# ComfyUI/models/text_encoders/gemma-3-12b-it-qat-q4_0-unquantized/
# https://huggingface.co/google/gemma-3-12b-it-qat-q4_0-unquantized

## vae
wget https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors
# wget https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors
# duplicate source for the same VAE
# wget https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors

wget https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/vae/ae.safetensors
# wget https://huggingface.co/stabilityai/sd-vae-ft-mse-original/resolve/main/vae-ft-mse-840000-ema-pruned.safetensors

## clip_vision
# wget https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/clip_vision/clip_vision_h.safetensors

## controlnet
# wget https://huggingface.co/lllyasviel/ControlNet-v1-1/resolve/main/control_v11p_sd15_canny.pth

## dwpose
# wget https://huggingface.co/licyk/comfyui-extension-models/resolve/main/comfyui_controlnet_aux/yzd-v/DWPose/yolox_l.onnx
# wget https://huggingface.co/licyk/comfyui-extension-models/resolve/main/comfyui_controlnet_aux/hr16/DWPose-TorchScript-BatchSize5/dw-ll_ucoco_384_bs5.torchscript.pt

## loras
# wget https://huggingface.co/lightx2v/Qwen-Image-Edit-2511-Lightning/resolve/main/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors
# older / alternate lightning LoRA
# wget https://huggingface.co/lightx2v/Qwen-Image-Lightning/resolve/main/Qwen-Image-Edit-Lightning-4steps-V1.0-bf16.safetensors
wget https://huggingface.co/lightx2v/Qwen-Image-Lightning/resolve/main/Qwen-Image-Edit-2509/Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors
wget https://huggingface.co/lightx2v/Qwen-Image-2512-Lightning/resolve/main/Qwen-Image-2512-Lightning-4steps-V1.0-fp32.safetensors

# wget https://huggingface.co/fal/Qwen-Image-Edit-2511-Multiple-Angles-LoRA/resolve/main/qwen-image-edit-2511-multiple-angles-lora.safetensors
# wget https://huggingface.co/MIUProject/VNCCS_PoseStudio/resolve/main/models/loras/qwen/VNCCS/VNCCS_PoseStudioQIE2511_V3_Art.safetensors
# older PoseStudio variant replaced by the V3 Art LoRA above
# wget https://huggingface.co/MIUProject/VNCCS_PoseStudio/resolve/main/models/loras/qwen/VNCCS/VNCCS_PoseStudioQIE2511_V2.safetensors
# Lenovo.safetensors
# wget https://civitai.com/api/download/models/2066914
# wget https://huggingface.co/vrgamedevgirl84/Wan14BT2VFusioniX/resolve/main/FusionX_LoRa/Wan2.1_T2V_14B_FusionX_LoRA.safetensors
# wget https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors
# wget https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors
# wget https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/loras/wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors
# wget https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/loras/wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors
# alternate Wan i2v lightning pair
# wget https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/LoRAs/Wan22-Lightning/old/Wan2.2-Lightning_I2V-A14B-4steps-lora_HIGH_fp16.safetensors
# wget https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/LoRAs/Wan22-Lightning/old/Wan2.2-Lightning_I2V-A14B-4steps-lora_LOW_fp16.safetensors

# wget https://huggingface.co/Lightricks/LTX-2-19b-IC-LoRA-Canny-Control/resolve/main/ltx-2-19b-ic-lora-canny-control.safetensors
# wget https://huggingface.co/Lightricks/LTX-2-19b-IC-LoRA-Depth-Control/resolve/main/ltx-2-19b-ic-lora-depth-control.safetensors
wget https://huggingface.co/Lightricks/LTX-2-19b-LoRA-Camera-Control-Dolly-Left/resolve/main/ltx-2-19b-lora-camera-control-dolly-left.safetensors
wget https://huggingface.co/Lightricks/LTX-2/resolve/main/ltx-2-19b-distilled-lora-384.safetensors
wget https://huggingface.co/Lightricks/LTX-2.3/resolve/main/ltx-2.3-22b-distilled-lora-384.safetensors
wget https://huggingface.co/Comfy-Org/ltx-2/resolve/main/split_files/loras/gemma-3-12b-it-abliterated_lora_rank64_bf16.safetensors

## latent_upscale_models
wget https://huggingface.co/Lightricks/LTX-2/resolve/main/ltx-2-spatial-upscaler-x2-1.0.safetensors
wget https://huggingface.co/Lightricks/LTX-2.3/resolve/main/ltx-2.3-spatial-upscaler-x2-1.1.safetensors

## upscale_models
# wget https://huggingface.co/Comfy-Org/Real-ESRGAN_repackaged/resolve/main/RealESRGAN_x4plus.safetensors

## other_models
# folder depends on the custom Lotus node setup
# wget https://huggingface.co/Comfy-Org/lotus/resolve/main/lotus-depth-d-v1-1.safetensors

# wget https://huggingface.co/Bingsu/adetailer/resolve/main/person_yolov8m-seg.pt
# wget https://huggingface.co/Bingsu/adetailer/resolve/main/hand_yolov9c.pt
# wget https://huggingface.co/Bingsu/adetailer/resolve/main/face_yolov9c.pt


## notes
# custom nodes required by workflows/qwen_image
git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git
git clone https://github.com/kijai/ComfyUI-KJNodes.git
git clone https://github.com/ltdrdata/was-node-suite-comfyui.git
## git clone https://github.com/yolain/ComfyUI-Easy-Use.git
# git clone https://github.com/jtydhr88/ComfyUI-qwenmultiangle.git
# git clone https://github.com/chflame163/ComfyUI_LayerStyle.git
# git clone https://github.com/city96/ComfyUI-GGUF.git
# git clone https://github.com/AHEKOT/ComfyUI_VNCCS.git
# git clone https://github.com/AHEKOT/ComfyUI_VNCCS_Utils.git
# git clone https://github.com/ltdrdata/ComfyUI-Impact-Pack.git
# git clone https://github.com/ltdrdata/ComfyUI-Impact-Subpack.git
# git clone https://github.com/pythongosssss/ComfyUI-Custom-Scripts.git
# git clone https://github.com/rgthree/rgthree-comfy.git
# git clone https://github.com/Fannovel16/comfyui_controlnet_aux.git
# git clone https://github.com/akatz-ai/ComfyUI-DepthCrafter-Nodes.git
# git clone https://github.com/kijai/ComfyUI-Florence2.git
# git clone https://github.com/cubiq/ComfyUI_IPAdapter_plus.git
# git clone https://github.com/Kosinkadink/ComfyUI-Advanced-ControlNet.git
# git clone https://github.com/AlekPet/ComfyUI_Custom_Nodes_AlekPet.git
# git clone https://github.com/sipherxyz/comfyui-art-venture.git
git clone https://github.com/TTPlanetPig/Comfyui_TTP_Toolset.git
# git clone https://github.com/Acly/comfyui-inpaint-nodes.git
# git clone https://github.com/Acly/comfyui-tooling-nodes.git
# git clone https://github.com/kijai/ComfyUI-WanVideoWrapper.git
# git clone https://github.com/kijai/ComfyUI-WanAnimatePreprocess.git
# git clone https://github.com/stduhpf/ComfyUI-WanMoeKSampler.git
# git clone https://github.com/pollockjj/ComfyUI-MultiGPU.git
# git clone https://github.com/evanspearman/ComfyMath.git
# git clone https://github.com/ltdrdata/was-node-suite-comfyui.git
# git clone https://github.com/Fannovel16/ComfyUI-Frame-Interpolation.git
git clone https://github.com/Comfy-Org/ComfyUI-Manager.git
# LTX workflows use nodes such as LTXVGemmaCLIPModelLoader.
git clone https://github.com/Lightricks/ComfyUI-LTXVideo.git
# git clone https://github.com/kijai/ComfyUI-segment-anything-2.git
# git clone https://github.com/1038lab/ComfyUI-RMBG.git
# git clone https://github.com/s9roll7/comfyui_cotracker_node.git
# git clone https://github.com/wanaigc/ComfyUI-Qwen3-TTS.git
# git clone https://github.com/un-seen/comfyui-tensorops.git
git clone https://github.com/diodiogod/TTS-Audio-Suite.git
# git clone https://github.com/Tencent-Hunyuan/HunyuanVideo-Foley.git
# git clone https://github.com/Windecay/ComfyUI-ReservedVRAM.git
git clone https://github.com/if-ai/ComfyUI_HunyuanVideoFoley.git

# reference
# https://huggingface.co/lllyasviel/ControlNet/tree/main/models
# https://huggingface.co/Comfy-Org/ltx-2.3/resolve/main/split_files/loras/ltx-2.3-id-lora-talkvid-3k.safetensors
