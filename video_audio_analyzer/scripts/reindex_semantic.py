"""Safely build version-2 clip-semantic indexes beside existing run indexes.

Original run directories and their `index/` directories are never modified.
New indexes are stored under the analyzer-owned `corpus_index_v2/` directory.
Existing corpus indexes are skipped unless the caller explicitly supplies
--replace.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from video_audio_analyzer.retrieval import build_index  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="analyzer root")
    parser.add_argument("--write", action="store_true", help="create corpus_index_v2 entries without modifying run artifacts")
    parser.add_argument("--replace", action="store_true", help="replace existing corpus_index_v2 entries when intentionally rebuilding")
    args = parser.parse_args()
    if args.replace and not args.write:
        parser.error("--replace requires --write")
    runs_root = args.root.resolve() / "runs"
    manifests = sorted(runs_root.glob("*/manifest.json"))
    if not manifests:
        print(f"No run manifests found under {runs_root}")
        return 0
    completed = skipped = errors = 0
    corpus_root = args.root.resolve() / "corpus_index_v2"
    for manifest_path in manifests:
        run_dir = manifest_path.parent
        target = corpus_root / run_dir.name / "index"
        if target.exists() and not args.replace:
            print(f"SKIP {run_dir.name}: index_v2 already exists (use --replace to rebuild)")
            skipped += 1
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(manifest.get("source"), dict) or not isinstance(manifest.get("scenes"), list):
                raise ValueError("manifest is missing source/scenes structures")
            if not args.write:
                print(f"READY {run_dir.name}: {len(manifest['scenes'])} scene(s) -> {target}")
                continue
            report = build_index(manifest, target.parent, index_name="index", preserve_clap_from=run_dir / "index")
            print(f"DONE {run_dir.name}: records={report['record_count']} PE-AV={report['vector_fields']['pe_av_vector']} CLAP={report['clap'].get('status')} ({report['clap'].get('preserved_record_count', 0)} preserved) backend={report['backend']}")
            completed += 1
        except Exception as exc:
            print(f"ERROR {run_dir.name}: {type(exc).__name__}: {exc}", file=sys.stderr)
            errors += 1
    print(f"Summary: completed={completed} skipped={skipped} errors={errors} write={args.write}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
