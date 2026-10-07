# F5-TTS Dataset and Fine-tuning

This repository includes a supported F5-TTS preparation/training toolchain under `TTS-Audio-Suite/engines/f5_tts/train/`. Do not generalize that support to every bundled TTS engine.

## Input layout

```text
dataset/
├── metadata.csv
└── wavs/
    ├── clip_0001.wav
    └── clip_0002.wav
```

`metadata.csv` is UTF-8 and pipe-delimited. The first row is skipped as a header. Column 1 is a path relative to the dataset directory; column 2 is the exact transcript.

```text
audio_file|text
wavs/clip_0001.wav|Exact words spoken in clip one.
```

Use clean single-speaker clips, consistent recording conditions, accurate transcripts, and legal consent. Split long recordings on natural boundaries and exclude silence-only, clipped, noisy, duplicated, or mis-transcribed samples. Preserve source masters outside the dataset.

## Preparation

```bash
python -m engines.f5_tts.train.datasets.prepare_csv_wavs INPUT_DIR OUTPUT_DIR
```

Preparation creates `raw.arrow`, `duration.json`, and `vocab.txt`. Fine-tuning mode requires the pretrained vocabulary to exist.

## Training approval gate

Before training, report dataset sample count, total duration, rejected samples, experiment, pretrained checkpoint, tokenizer, learning rate, batch size, epochs, output/checkpoint directory, logging choice, and exact command. Obtain explicit approval because training is expensive and writes large checkpoints.

The CLI supports `F5TTS_v1_Base`, `F5TTS_Base`, and `E2TTS_Base`; use `--finetune` and optionally `--pretrain`. Do not silently download a checkpoint or start W&B.
