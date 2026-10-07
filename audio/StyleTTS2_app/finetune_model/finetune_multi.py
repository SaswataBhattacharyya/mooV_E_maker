#!/usr/bin/env python3
"""
Orchestrate per-speaker StyleTTS2 finetuning.

For each speaker:
- Generates a config derived from a base config
- Points train/val filelists to that speaker's files
- Updates root_path, log_dir, pretrained_model
- Invokes the repo training entrypoint (train_finetune.py or accelerate variant)
- Copies final checkpoint as styletts2_{speaker}.pth
"""

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List

import yaml


def load_speaker_map(work_dir: Path) -> Dict[str, int]:
    spk_map_path = work_dir / "speakers.json"
    if not spk_map_path.exists():
        raise FileNotFoundError(f"Missing speaker map: {spk_map_path}")
    return json.loads(spk_map_path.read_text())


def detect_speakers(work_dir: Path) -> List[str]:
    filelists = (work_dir / "filelists").glob("*_train.txt")
    speakers = sorted({p.stem.replace("_train", "") for p in filelists})
    if not speakers:
        raise RuntimeError("No speakers found in filelists/")
    return speakers


def prepare_config(base_config: Path,
                   out_config: Path,
                   train_list: Path,
                   val_list: Path,
                   root_path: Path,
                   log_dir: Path,
                   checkpoint: Path,
                   lr: float = None,
                   batch_size: int = None,
                   epochs: int = None,
                   max_steps: int = None,
                   seed: int = None) -> None:
    cfg = yaml.safe_load(base_config.read_text())

    # Update data paths
    cfg["data_params"]["train_data"] = str(train_list)
    cfg["data_params"]["val_data"] = str(val_list)
    cfg["data_params"]["root_path"] = str(root_path)

    # Pretrained checkpoint
    cfg["pretrained_model"] = str(checkpoint)
    cfg["second_stage_load_pretrained"] = True
    cfg["load_only_params"] = True

    # Logging dir
    cfg["log_dir"] = str(log_dir)

    # Ensure multispeaker for adaptation
    if "model_params" in cfg:
        cfg["model_params"]["multispeaker"] = True

    # Overrides
    if lr is not None:
        cfg.setdefault("optimizer_params", {})
        cfg["optimizer_params"]["lr"] = lr
    if batch_size is not None:
        cfg["batch_size"] = batch_size
    if epochs is not None:
        cfg["epochs"] = epochs
    if max_steps is not None:
        cfg["max_steps"] = max_steps
    if seed is not None:
        cfg["seed"] = seed

    out_config.parent.mkdir(parents=True, exist_ok=True)
    out_config.write_text(yaml.safe_dump(cfg), encoding="utf-8")


def run_training(script: Path, config_path: Path, use_accelerate: bool) -> None:
    cmd = ["python", str(script), "--config_path", str(config_path)]
    if use_accelerate:
        cmd = ["accelerate", "launch", "--mixed_precision=fp16", "--num_processes=1"] + cmd
    subprocess.run(cmd, check=True)


def copy_final_checkpoint(log_dir: Path, dest_path: Path) -> None:
    # Heuristic: pick latest epoch_2nd*.pth or epoch*.pth
    candidates = sorted(log_dir.glob("epoch*_*.pth"))
    if not candidates:
        candidates = sorted(log_dir.glob("epoch*.pth"))
    if not candidates:
        raise FileNotFoundError(f"No checkpoints found in {log_dir}")
    latest = candidates[-1]
    shutil.copy(latest, dest_path)


def main():
    ap = argparse.ArgumentParser(
        description="Finetune StyleTTS2 for multiple speakers",
        epilog="If key arguments are omitted, you will be prompted interactively.")
    ap.add_argument("--styletts2_repo", type=Path, help="Path to StyleTTS2 repo")
    ap.add_argument("--work_dir", type=Path, help="Preprocess output directory")
    ap.add_argument("--out_dir", type=Path, help="Output directory for runs")
    ap.add_argument("--base_checkpoint", type=Path, help="Pretrained .pth to start from")
    ap.add_argument("--base_config", type=Path, help="Template config (e.g., Configs/config_ft.yml)")
    ap.add_argument("--speakers", type=str, help="Comma-separated speaker names; if omitted, auto-detect")
    ap.add_argument("--lr", type=float, help="Override learning rate")
    ap.add_argument("--batch_size", type=int, help="Override batch size")
    ap.add_argument("--epochs", type=int, help="Override epochs")
    ap.add_argument("--max_steps", type=int, help="Override max_steps")
    ap.add_argument("--seed", type=int, help="Random seed")
    ap.add_argument("--use_accelerate", action="store_true", help="Use accelerate launch (single GPU fp16)")
    args = ap.parse_args()

    # Interactive prompts for missing required paths
    if args.styletts2_repo is None:
        args.styletts2_repo = Path(input("Enter path to StyleTTS2 repo: ").strip())
    if args.work_dir is None:
        args.work_dir = Path(input("Enter work_dir (preprocess output): ").strip())
    if args.out_dir is None:
        args.out_dir = Path(input("Enter out_dir (finetune outputs): ").strip())
    if args.base_checkpoint is None:
        args.base_checkpoint = Path(input("Enter base checkpoint (.pth): ").strip())
    if args.base_config is None:
        args.base_config = Path(input("Enter base config (e.g., Configs/config_ft.yml): ").strip())

    speakers = args.speakers.split(",") if args.speakers else detect_speakers(args.work_dir)
    spk_map = load_speaker_map(args.work_dir)

    train_finetune_py = args.styletts2_repo / ("train_finetune_accelerate.py" if args.use_accelerate else "train_finetune.py")
    if not train_finetune_py.exists():
        raise FileNotFoundError(f"Training script not found: {train_finetune_py}")

    for spk in speakers:
        if spk not in spk_map:
            raise ValueError(f"Speaker '{spk}' not found in speaker map.")
        print(f"=== Finetuning speaker: {spk} (id={spk_map[spk]}) ===")
        out_spk_dir = args.out_dir / spk
        out_spk_dir.mkdir(parents=True, exist_ok=True)

        train_list = args.work_dir / "filelists" / f"{spk}_train.txt"
        val_list = args.work_dir / "filelists" / f"{spk}_val.txt"
        root_path = args.work_dir / "wavs"

        gen_config = out_spk_dir / f"config_{spk}.yml"
        prepare_config(
            base_config=args.base_config,
            out_config=gen_config,
            train_list=train_list,
            val_list=val_list,
            root_path=root_path,
            log_dir=out_spk_dir,
            checkpoint=args.base_checkpoint,
            lr=args.lr,
            batch_size=args.batch_size,
            epochs=args.epochs,
            max_steps=args.max_steps,
            seed=args.seed,
        )

        run_training(train_finetune_py, gen_config, use_accelerate=args.use_accelerate)

        final_ckpt = out_spk_dir / f"styletts2_{spk}.pth"
        copy_final_checkpoint(out_spk_dir, final_ckpt)
        print(f"Saved final checkpoint to {final_ckpt}")


if __name__ == "__main__":
    main()

