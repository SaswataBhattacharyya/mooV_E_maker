"""Explicitly fetch the public NeMo diarization models into /models/nemo.

This script is a one-time, user-invoked preparation step. Analysis jobs never
call from_pretrained and therefore never download weights unexpectedly.
"""
from __future__ import annotations

import argparse
import tarfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models-dir", type=Path, default=Path("/models/nemo"))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    args.models_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "vad_multilingual_marblenet": args.models_dir / "vad_multilingual_marblenet.nemo",
        "titanet_large": args.models_dir / "titanet_large.nemo",
    }
    def valid_archive(path: Path) -> bool:
        if not path.is_file() or path.stat().st_size == 0:
            return False
        try:
            with tarfile.open(path, "r") as archive:
                names = set(archive.getnames())
            return any(name.endswith("model_config.yaml") for name in names) and any(
                name.endswith("model_weights.ckpt") for name in names
            )
        except (tarfile.TarError, OSError):
            return False

    invalid = [path for path in outputs.values() if path.exists() and not valid_archive(path)]
    if invalid and not args.overwrite:
        raise SystemExit("Refusing to replace invalid existing model files: " + ", ".join(str(path) for path in invalid) + ". Inspect them, then explicitly pass --overwrite if replacement is intended.")
    from nemo.collections.asr.models import EncDecClassificationModel, EncDecSpeakerLabelModel
    models = {
        "vad_multilingual_marblenet": EncDecClassificationModel,
        "titanet_large": EncDecSpeakerLabelModel,
    }
    for name, model_class in models.items():
        if valid_archive(outputs[name]) and not args.overwrite:
            print(f"Keeping valid existing checkpoint {outputs[name]} ({outputs[name].stat().st_size} bytes)", flush=True)
            continue
        print(f"Downloading official NeMo model {name} into {outputs[name]}", flush=True)
        model = model_class.from_pretrained(model_name=name)
        model.save_to(str(outputs[name]))
        if not valid_archive(outputs[name]):
            raise RuntimeError(f"Model preparation failed/incomplete: {outputs[name]}")
        print(f"Prepared {outputs[name]} ({outputs[name].stat().st_size} bytes)", flush=True)


if __name__ == "__main__":
    main()
