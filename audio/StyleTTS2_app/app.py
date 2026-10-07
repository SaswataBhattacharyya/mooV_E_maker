import streamlit as st
from pathlib import Path
import time

from infer_backend import StyleTTS2Infer

st.set_page_config(page_title="StyleTTS2 App", layout="centered")
st.title("StyleTTS2 – Voice & Emotion TTS")

# -----------------------------
# Resolve StyleTTS2 directory paths
# -----------------------------
# Get the StyleTTS2 directory (parent of StyleTTS2_app)
STYLETTS2_DIR = Path(__file__).resolve().parent.parent / "StyleTTS2"

# Config path: prefer checkpoints/config.yml if it exists (downloaded with checkpoint),
# otherwise use Configs/config.yml
CHECKPOINT_CONFIG = STYLETTS2_DIR / "checkpoints" / "config.yml"
DEFAULT_CONFIG = STYLETTS2_DIR / "Configs" / "config.yml"
if CHECKPOINT_CONFIG.exists():
    CONFIG_PATH = str(CHECKPOINT_CONFIG)
    st.info(f"Using config from checkpoints: {CHECKPOINT_CONFIG.name}")
else:
    CONFIG_PATH = str(DEFAULT_CONFIG)

# Checkpoint path
CHECKPOINT_PATH = str(STYLETTS2_DIR / "checkpoints" / "styletts2.pth")

# Verify checkpoint exists
if not Path(CHECKPOINT_PATH).exists():
    st.error(f"Checkpoint file not found: {CHECKPOINT_PATH}")
    st.info("Please ensure your checkpoint file is named 'styletts2.pth' and placed in the checkpoints folder")
    st.stop()

@st.cache_resource
def get_tts(config_path, checkpoint_path):
    """Load and cache the TTS model to avoid reloading on every button click"""
    import torch
    # Clear cache before loading to free up memory
    torch.cuda.empty_cache() if torch.cuda.is_available() else None
    return StyleTTS2Infer(config_path, checkpoint_path)

# -----------------------------
# Inputs
# -----------------------------
ref_audio = st.file_uploader(
    "Upload reference audio (voice + emotion)",
    type=["wav", "mp3", "flac"]
)

text_input = st.text_area(
    "Enter target text (t2)",
    height=200
)

out_dir = st.text_input(
    "Output directory",
    value=str(Path.cwd() / "outputs")
)

# -----------------------------
# Run
# -----------------------------
if st.button("Generate Speech"):
    if ref_audio is None or not text_input.strip():
        st.error("Please provide reference audio and text.")
        st.stop()

    Path(out_dir).mkdir(parents=True, exist_ok=True)

    ref_path = Path(out_dir) / ref_audio.name
    ref_path.write_bytes(ref_audio.read())

    out_wav = Path(out_dir) / f"tts_{int(time.time())}.wav"

    with st.spinner("Generating audio..."):
        # Use cached TTS model instead of creating a new one each time
        tts = get_tts(CONFIG_PATH, CHECKPOINT_PATH)
        # synthesize() now handles chunking automatically for long texts
        tts.synthesize(text_input, str(ref_path), str(out_wav))

    st.success(f"Saved: {out_wav}")
    st.audio(str(out_wav))
