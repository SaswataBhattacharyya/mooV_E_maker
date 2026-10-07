from __future__ import annotations

import argparse
from pathlib import Path

from image_analyzer.cli.batch import resolve_batch_inputs
from image_analyzer.config.settings import load_settings
from image_analyzer.detailed_pipeline import run_batch_flow, run_image_flow


def main() -> None:
    parser = argparse.ArgumentParser(prog="image-analyzer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    image_parser = subparsers.add_parser("analyze-image")
    image_parser.add_argument("image_path")
    image_parser.add_argument("--output-dir", default=None)
    image_parser.add_argument("--project-name", default=None)
    image_parser.add_argument("--target-score", type=float, default=None)
    image_parser.add_argument("--max-full-restarts", type=int, default=None)
    image_parser.add_argument("--max-question-rounds", type=int, default=None)
    image_parser.add_argument("--enable-generation", action="store_true")

    batch_parser = subparsers.add_parser("analyze-batch")
    batch_parser.add_argument("input_dir")
    batch_parser.add_argument("--output-dir", default=None)
    batch_parser.add_argument("--project-name", default=None)
    batch_parser.add_argument("--enable-generation", action="store_true")

    # Compatibility alias for older docs and scripts. This uses the same unified engine.
    detailed_parser = subparsers.add_parser("analyze-detailed")
    detailed_parser.add_argument("image_path")
    detailed_parser.add_argument("--output-dir", default=None)
    detailed_parser.add_argument("--project-name", default=None)
    detailed_parser.add_argument("--target-score", type=float, default=None)
    detailed_parser.add_argument("--max-full-restarts", type=int, default=None)
    detailed_parser.add_argument("--max-question-rounds", type=int, default=None)
    detailed_parser.add_argument("--enable-generation", action="store_true")

    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[3]
    config = load_settings(project_root)
    output_dir = Path(args.output_dir).resolve() if args.output_dir else None

    if args.command in {"analyze-image", "analyze-detailed"}:
        report = run_image_flow(
            Path(args.image_path),
            config,
            output_root=output_dir,
            project_name=args.project_name,
            target_score=args.target_score,
            max_full_restarts=args.max_full_restarts,
            max_question_rounds=args.max_question_rounds,
            enable_generation=args.enable_generation,
        )
        print(f"Run directory: {report.run_dir}")
        if report.generation.status == "completed":
            print(f"Similarity: {round(report.termination.best_score * 100.0, 2)}%")
        else:
            print(f"Generation: {report.generation.status} | {report.generation.message}")
        if report.generation.output_image:
            print(f"Generated image: {report.generation.output_image}")
        print(report.prompt_package.final_prompt)
        return

    input_dir = Path(args.input_dir)
    image_paths = resolve_batch_inputs(input_dir)
    reports = run_batch_flow(
        image_paths,
        config,
        output_root=output_dir,
        project_name=args.project_name,
        enable_generation=args.enable_generation,
    )
    print(f"Processed {len(reports)} images.")
    for report in reports:
        print(f"{Path(report.reference_image).name}: {round(report.termination.best_score * 100.0, 2)}% -> {report.run_dir}")


if __name__ == "__main__":
    main()
