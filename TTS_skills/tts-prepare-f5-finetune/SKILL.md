---
name: tts-prepare-f5-finetune
description: Design, validate, and prepare transcribed voice datasets and commands for repository-supported F5-TTS fine-tuning. Use when restructuring recordings into metadata.csv plus wavs, checking transcripts/durations, preparing Arrow data, selecting F5 checkpoints/tokenizers, or planning a fine-tune. Require confirmation before training.
---

# Prepare F5-TTS Fine-tuning

Read `../_shared/references/f5-finetune.md` and `../_shared/references/dialogue-and-voices.md`.

1. Confirm the user means model fine-tuning rather than reference-based voice cloning.
2. Preserve masters and build a separate `metadata.csv` plus `wavs/` dataset.
3. Normalize filenames, require exact transcripts, and exclude unusable clips; do not fabricate missing words.
4. Run `scripts/validate_f5_dataset.py DATASET_DIR` and report sample count, total duration, failures, and warnings.
5. Prepare the dataset with the repository tool only after validation passes.
6. Draft the exact training command, checkpoint/output locations, and hyperparameters.
7. Stop and obtain explicit approval before launching training, downloading a missing pretrained checkpoint, enabling W&B, or overwriting checkpoints.

Do not claim supported end-to-end fine-tuning for other engines merely because their bundled source contains training-related code.
