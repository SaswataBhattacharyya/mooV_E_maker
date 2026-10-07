Yes — Whisper can do near-live transcription, and there are several stronger local multilingual options now.

The important distinction is:

* **true streaming ASR**: model is architected to consume audio continuously and emit text incrementally.
* **pseudo-streaming / chunked ASR**: record 0.5–3 s chunks, repeatedly run ASR, and update the transcript.

Whisper is mainly the second type. `whisper.cpp` even ships a microphone streaming example that samples audio every 500 ms and continuously retranscribes it, so visually it can feel almost live. ([GitHub][1])

### Good local multilingual choices right now

| Model                                 |                       Multilingual |        Real streaming |        Size | My use case                                 |
| ------------------------------------- | ---------------------------------: | --------------------: | ----------: | ------------------------------------------- |
| **Whisper large-v3 / medium**         |                     ~100 languages |               Chunked | 1.5B / 769M | Maximum language breadth + mature ecosystem |
| **Qwen3-ASR 0.6B**                    | 30 languages + 22 Chinese dialects |               **Yes** |        0.6B | Excellent fit for a local WebUI             |
| **Qwen3-ASR 1.7B**                    |                               same |               **Yes** |        1.7B | Better quality if GPU allows                |
| **NVIDIA Nemotron 3.5 ASR Streaming** |         up to ~40 language/locales |               **Yes** |        0.6B | Excellent NVIDIA/local streaming choice     |
| **Voxtral Mini Realtime**             |                       13 languages |               **Yes** |          4B | Very low latency, multilingual              |
| **FunASR / SenseVoice family**        |                50+ depending model |           Yes/options |      varies | Strong Asian-language ecosystem             |
| **Meta MMS**                          |           **1,100+ ASR languages** | not its main strength |      varies | Best starting point for rare languages      |

Qwen3-ASR is particularly interesting for what you are building because the official 0.6B and 1.7B releases support **streaming and offline inference in the same model**, with 30 named languages plus 22 Chinese dialects. Hindi is included. ([Hugging Face][2])

NVIDIA's newer **Nemotron 3.5 ASR Streaming 0.6B** is also worth serious consideration. It is a cache-aware FastConformer-RNNT specifically designed for streaming, accepts configurable chunks down to 80 ms, and extends NVIDIA's earlier English model to multilingual transcription. ([Hugging Face][3])

Voxtral Realtime supports 13 languages including Hindi and has configurable latency down to sub-200 ms. ([Mistral AI][4])

And if your real requirement becomes **“I need Bengali, Assamese, Nepali, tribal languages, low-resource Indian languages, etc.”**, Meta's MMS becomes very relevant: Meta released multilingual ASR coverage for **over 1,100 languages** and pretrained speech representations spanning more than 1,400. ([GitHub][5])

## What I would use in your WebUI

I would actually test **three** locally:

```text
1. Qwen3-ASR-0.6B
2. NVIDIA Nemotron 3.5 ASR Streaming 0.6B
3. Whisper medium / large-v3
```

Then measure:

```text
speech latency
WER/CER
Indian accent handling
Hindi
English
code-switching
your target regional language
GPU memory
CPU/GPU utilization
```

Whisper becomes your **fallback language-coverage model**, while Qwen3-ASR or Nemotron can be the real-time model.

For example:

```text
Browser microphone
       ↓
VAD
       ↓
Streaming ASR
 ┌─────┴─────────────┐
 │                   │
Qwen3-ASR       Whisper fallback
 │                   │
 └───────┬───────────┘
         ↓
live transcript
```

---

# How do you fine-tune ASR for another language?

There are actually **three different problems**, and they should not be treated the same way.

## Case 1 — Language already supported, but recognition is poor

Example:

> Hindi exists, but your Indian medical terminology or particular accents perform badly.

This is the easiest.

Prepare:

```text
audio.wav → exact transcript
audio.wav → exact transcript
audio.wav → exact transcript
...
```

Then fine-tune the existing multilingual model.

NVIDIA explicitly recommends ASR fine-tuning for new accents, domains, acoustic environments, and new languages when using multilingual pretrained models. ([NVIDIA Docs][6])

You don't normally touch the tokenizer.

You're teaching it:

```text
this sound pattern
       ↓
this existing vocabulary/text
```

---

# Case 2 — The language is poorly represented but uses a script the model already understands

For example, imagine your model understands Devanagari but has almost no training in a particular language written using Devanagari.

Then transfer learning works very well conceptually:

```text
multilingual acoustic encoder
           +
new-language audio/transcripts
           ↓
fine-tuning
```

This is where pretrained speech models are extremely useful.

Whisper itself is readily fine-tunable for multilingual ASR; Hugging Face provides a complete official Transformers workflow for multilingual Whisper fine-tuning. ([Hugging Face][7])

---

# Case 3 — Completely unsupported language / script

This is where I would **not automatically choose Whisper**.

Whisper's multilingual architecture uses predefined language-prefix tokens such as:

```text
<|en|>
<|hi|>
<|fr|>
...
```

The tokenizer documentation explicitly uses those language IDs during multilingual fine-tuning. ([Hugging Face][8])

If your language isn't represented by that scheme, you start fighting the architecture.

You could technically modify:

```text
tokenizer
decoder vocabulary
embedding matrix
language tokens
training pipeline
```

but now it is no longer a straightforward fine-tune.

For **truly new languages**, I'd prefer architectures designed for language adaptation, such as:

```text
Meta MMS
Wav2Vec2 / W2V2-BERT
NeMo multilingual CTC/RNNT
```

Meta MMS is especially compelling here precisely because it was built around scaling ASR to over 1,000 languages. ([GitHub][5])

---

# What your training dataset looks like

The fundamental unit is surprisingly simple:

```json
{
  "audio": "000123.wav",
  "text": "আমার নাম সুমন।"
}
```

Or NeMo-style:

```json
{
  "audio_filepath": "/dataset/audio/000123.wav",
  "duration": 4.71,
  "text": "আমার নাম সুমন।"
}
```

You need **native-speaker speech + accurate transcription**.

Then build:

```text
dataset/
├── train/
├── validation/
└── test/
```

And make sure speakers do not leak heavily between your training and evaluation sets.

The important part is not simply getting huge amounts of audio.

You want diversity across:

```text
male/female voices
age groups
regional accents
fast/slow speech
quiet/noisy environments
microphones
mobile recordings
formal speech
casual speech
code switching
numbers
names
places
technical words
```

---

# How much data?

There isn't one magic number.

A useful practical mental model is:

```text
5–20 hours
    ↓
experiment / prove adaptation works

20–100 hours
    ↓
potentially useful low-resource fine-tune

100–500 hours
    ↓
much more serious language adaptation

500+ diverse hours
    ↓
production-quality ambitions
```

Those are **engineering heuristics rather than hard thresholds**. Data quality and the pretrained model matter enormously. NVIDIA's own customization guidance says that robust ASR fine-tuning can require data on the order of **several hundred hours**, particularly when doing language-level adaptation rather than simple domain customization. ([NVIDIA Docs][9])

---

# The interesting shortcut: synthetic speech

You might think:

```text
I have written Bengali text
        ↓
TTS
        ↓
50,000 hours synthetic Bengali
        ↓
train ASR
```

You can use synthetic data, but I would **not train primarily on synthetic TTS**.

ASR has to learn real speech:

```text
breathing
hesitation
mispronunciation
accent
room echo
bad microphones
background sounds
unfinished words
speech rate variation
```

A TTS system tends to produce cleaner and more regular pronunciation. NVIDIA specifically warns about cases where fine-tuning against synthetic pronunciation mismatches can teach an ASR system the wrong behaviour. ([NVIDIA Developer][10])

Better:

```text
REAL SPEECH        70–90%
+
SYNTHETIC/AUGMENTED DATA
+
noise/reverb augmentation
```

with the precise ratio determined experimentally.

---

# For an Indian multilingual WebUI, I would design it differently

Don't commit yourself to a single ASR engine.

Build an interface such as:

```python
class ASREngine:
    def start_stream(self):
        ...

    def feed_audio(self, chunk):
        ...

    def partial_text(self):
        ...

    def final_text(self):
        ...
```

Then adapters:

```text
WhisperASR
QwenASR
NemotronASR
MMSASR
```

Your frontend sees exactly the same API.

Then later you can route automatically:

```text
microphone
    ↓
language detection
    ↓
┌─────────────────────────────┐
│ English/Hindi → Qwen/Nemotron
│ supported language → Qwen
│ rare language → MMS
│ uncertain → Whisper
└─────────────────────────────┘
```

That would be much more future-proof than embedding Whisper directly throughout your application.

### And one model I would definitely test now: **Qwen3-ASR-0.6B**

Since you're already using Qwen elsewhere, it's unusually convenient: **600M parameters, local, multilingual, actual streaming inference**, with official tooling for local WebUI/streaming deployment. ([Hugging Face][2])

If your target includes **Bengali specifically**, though, I'd benchmark Whisper and MMS as well rather than assuming Qwen3-ASR covers it—the current Qwen3-ASR language list includes Hindi but does **not** list Bengali. ([Hugging Face][2])

I can also keep an eye on new open multilingual streaming-ASR releases and flag ones that beat these for local use.

[1]: https://github.com/ggerganov/whisper.cpp/blob/master/examples/stream/README.md?utm_source=chatgpt.com "whisper.cpp/examples/stream/README.md at master · ..."
[2]: https://huggingface.co/Qwen/Qwen3-ASR-1.7B?utm_source=chatgpt.com "Qwen/Qwen3-ASR-1.7B"
[3]: https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b?utm_source=chatgpt.com "nvidia/nemotron-3.5-asr-streaming-0.6b"
[4]: https://docs.mistral.ai/studio-api/audio/speech_to_text?utm_source=chatgpt.com "Speech to Text | Mistral Docs"
[5]: https://github.com/facebookresearch/fairseq/blob/main/examples/mms/README.md?utm_source=chatgpt.com "fairseq/examples/mms/README.md at main"
[6]: https://docs.nvidia.com/nemo/speech/nightly/asr/fine_tuning.html?utm_source=chatgpt.com "Fine-Tuning — NeMo-Speech"
[7]: https://huggingface.co/blog/fine-tune-whisper?utm_source=chatgpt.com "Fine-Tune Whisper For Multilingual ASR with 🤗 Transformers"
[8]: https://huggingface.co/docs/transformers/en/model_doc/whisper?utm_source=chatgpt.com "Whisper"
[9]: https://docs.nvidia.com/nim/speech/latest/asr/customization/customization.html?utm_source=chatgpt.com "Customizing ASR Models"
[10]: https://developer.nvidia.com/blog/evaluate-clinical-asr-models-faster-with-agent-skills-and-nvidia-nemotron-speech/?utm_source=chatgpt.com "Evaluate Clinical ASR Models Faster with Agent Skills and ..."
