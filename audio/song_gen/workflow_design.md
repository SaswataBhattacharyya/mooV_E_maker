
workflow design (simple + scalable)
Step 0 — Standardize audio (WAV cache)

For every filename.mp3, create:

data/_cache_wav/<class>/filename.wav

Decide ONE standard format:

sample rate: 44100 Hz (good default)

channels: stereo (keep music stereo; raga pipeline can use mono vocals)

sample format: PCM 16-bit or float32

Step 1 — Extract features into JSON (per track)

Create:

data/_analysis/<class>/filename.analysis.json

This JSON is merged output from:

Essentia: bpm, key, loudness-ish, energy, danceability-ish

Librosa: spectral centroid, rolloff, chroma, tempo confirmation, harmonic/percussive ratio

Demucs (optional): vocal_presence score, stem energy ratios

Raga classifier (bhajan only): raga label + confidence

Step 2 — Segment audio into fixed windows (recommended)

Create segments (example 20s with 2s overlap):
data/_segments/<class>/filename/seg000.wav
.../seg001.wav

Step 3 — Copy prompt + lyrics per segment (Option 1)

For every segment create:

seg000_prompt.txt = same as filename_prompt.txt (or generated later)

seg000_lyrics.txt = same as filename_lyrics.txt

seg000_analysis.json = inherit track-level + add {"segment": {"start":..,"end":..}}

This is easiest for training systems that expect 1 audio ↔ 1 prompt ↔ 1 lyric file.

Step 4 — Generate / update prompts using an LLM (Cursor agent)

You will not write prompt manually. The agent will:

read filename.analysis.json

generate filename_prompt.txt (and optionally segment prompts if desired)

Important: Don’t generate prompts before you have analysis JSON — otherwise prompts are vague.

Important clarifications (only 2)

I’ll assume defaults unless you say otherwise:

Segment length: I recommend 20 seconds (good balance). OK?

Sample rate for standardized wav: I recommend 44.1kHz. OK?

If you don’t reply, I’ll assume 20s / 44.1kHz.

requirements-
1) System tools

ffmpeg (mandatory): convert mp3 → wav, resample, split

Ubuntu: sudo apt-get install ffmpeg

(optional) sox (not required if you use ffmpeg)

2) Python env packages (core)

Create one venv/conda env (recommended):

numpy, scipy, pandas

soundfile (read/write wav reliably)

librosa

tqdm

pyyaml

jsonschema (optional but helpful)

torch (needed anyway for ACE-step + demucs + raga model)

essentia (install as python package; don’t rely only on repo clone)

Essentia install options

easiest: pip install essentia (if available for your Python)

otherwise: build from the cloned repo (MTG essentia docs)
