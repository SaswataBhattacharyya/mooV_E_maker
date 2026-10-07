from __future__ import annotations

import tempfile
from pathlib import Path

from image_analyzer.cli.batch import resolve_batch_inputs
from image_analyzer.config.settings import load_settings
from image_analyzer.detailed_pipeline import run_batch_flow, run_image_flow
from image_analyzer.models.schemas import RunReport


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="Image Recreation Agent", layout="wide")
    st.title("Image Recreation Agent")
    st.caption("One unified OpenClaw-style flow: interrogate the image with a VLM, build scene memory, generate, score, and restart until the similarity threshold is met or retries are exhausted.")

    config = load_settings(PROJECT_ROOT)

    with st.sidebar:
        mode = st.radio("Mode", ["Single image", "Batch folder"], index=0)
        output_root_raw = st.text_input("Run folder root", value=str(config.detailed.run_root_dir))
        project_name = st.text_input("Project name", value=config.detailed.default_project_name)
        enable_generation = st.checkbox("Enable image generation + comparison", value=config.detailed.enable_generation_by_default)
        target_score = st.slider("Similarity threshold", min_value=0.50, max_value=0.99, value=float(config.detailed.target_score), step=0.01)
        max_full_restarts = st.number_input("Max full restarts", min_value=1, max_value=10, value=int(config.detailed.max_full_restarts), step=1)
        max_question_rounds = st.number_input("Max question rounds", min_value=1, max_value=20, value=int(config.detailed.max_question_rounds), step=1)

    output_root = Path(output_root_raw).expanduser()
    if mode == "Single image":
        _render_single_mode(output_root, project_name, enable_generation, target_score, int(max_full_restarts), int(max_question_rounds))
    else:
        _render_batch_mode(output_root, project_name, enable_generation)


def _render_single_mode(
    output_root: Path,
    project_name: str,
    enable_generation: bool,
    target_score: float,
    max_full_restarts: int,
    max_question_rounds: int,
) -> None:
    import streamlit as st

    path_value = st.text_input("Image path", value="")
    uploaded_file = st.file_uploader("Or upload one image", type=["png", "jpg", "jpeg", "webp", "bmp"])
    run = st.button("Run recreation flow", type="primary")

    if not run:
        return

    image_path = _resolve_single_input(path_value, uploaded_file)
    if image_path is None:
        st.error("Provide a valid image path or upload an image.")
        return

    output_root.mkdir(parents=True, exist_ok=True)
    _run_streamlit_flow(
        [image_path],
        output_root=output_root,
        project_name=project_name,
        enable_generation=enable_generation,
        target_score=target_score,
        max_full_restarts=max_full_restarts,
        max_question_rounds=max_question_rounds,
        batch_mode=False,
    )


def _render_batch_mode(output_root: Path, project_name: str, enable_generation: bool) -> None:
    import streamlit as st

    batch_path_value = st.text_input("Input folder or manifest path", value="")
    run = st.button("Run batch recreation flow", type="primary")

    if not run:
        return

    if not batch_path_value.strip():
        st.error("Provide an input folder or manifest path for batch processing.")
        return

    input_path = Path(batch_path_value).expanduser()
    try:
        image_paths = resolve_batch_inputs(input_path)
    except Exception as exc:
        st.error(f"Unable to resolve batch inputs: {exc}")
        return

    if not image_paths:
        st.warning("No supported images were found in the provided location.")
        return

    output_root.mkdir(parents=True, exist_ok=True)
    _run_streamlit_flow(
        image_paths,
        output_root=output_root,
        project_name=project_name,
        enable_generation=enable_generation,
        target_score=None,
        max_full_restarts=None,
        max_question_rounds=None,
        batch_mode=True,
    )


def _resolve_single_input(path_value: str, uploaded_file: object) -> Path | None:
    if path_value.strip():
        candidate = Path(path_value).expanduser()
        return candidate if candidate.exists() else None
    if uploaded_file is None:
        return None

    upload_dir = Path(tempfile.mkdtemp(prefix="image-analyzer-upload-"))
    target = upload_dir / str(getattr(uploaded_file, "name", "uploaded-image.png"))
    target.write_bytes(uploaded_file.getbuffer())
    return target


def _run_streamlit_flow(
    image_paths: list[Path],
    *,
    output_root: Path,
    project_name: str,
    enable_generation: bool,
    target_score: float | None,
    max_full_restarts: int | None,
    max_question_rounds: int | None,
    batch_mode: bool,
) -> None:
    import streamlit as st

    config = load_settings(PROJECT_ROOT)

    left_col, right_col = st.columns([1.1, 1.4])
    progress_bar = st.progress(0.0)
    batch_status = st.empty()
    image_slot = left_col.empty()
    generated_slot = left_col.empty()
    latest_event_slot = left_col.empty()
    similarity_slot = right_col.empty()
    error_slot = right_col.empty()
    event_log_slot = right_col.empty()
    result_slot = right_col.empty()

    collected_events: list[dict[str, object]] = []
    reports: list[RunReport] = []

    def on_event(event: dict[str, object]) -> None:
        collected_events.append(event)
        latest_event_slot.info(f"{event['stage']} [{event['status']}] {event['message']}")
        event_lines = [
            f"{item['timestamp']} | {item['stage']} | {item['status']} | {item['message']}"
            for item in collected_events[-30:]
        ]
        event_log_slot.code("\n".join(event_lines), language="text")
        payload = event.get("payload", {}) if isinstance(event.get("payload"), dict) else {}
        if str(event.get("status")) in {"warning", "failed", "error"}:
            error_slot.error(f"{event['stage']}: {event['message']}")
        if "output_image" in payload and payload["output_image"]:
            candidate = Path(str(payload["output_image"]))
            if candidate.exists():
                generated_slot.image(str(candidate), caption="Generated image", use_container_width=True)
        if "similarity" in payload:
            similarity_slot.metric("Similarity", f"{round(float(payload['similarity']) * 100.0, 2)}%")

    total = len(image_paths)
    for index, image_path in enumerate(image_paths, start=1):
        batch_status.write(f"Processing {index}/{total}: `{image_path.name}`")
        image_slot.image(str(image_path), caption=image_path.name, use_container_width=True)
        generated_slot.empty()
        similarity_slot.empty()
        error_slot.empty()
        collected_events.clear()
        report = run_image_flow(
            image_path,
            config,
            output_root=output_root,
            project_name=project_name,
            enable_generation=enable_generation,
            target_score=target_score,
            max_full_restarts=max_full_restarts,
            max_question_rounds=max_question_rounds,
            event_callback=on_event,
        )
        reports.append(report)
        progress_bar.progress(index / total)
        result_slot.empty()
        _render_result(result_slot.container(), report)

    if batch_mode:
        st.success(f"Finished batch recreation flow for {len(reports)} images.")
    else:
        st.success("Finished image recreation flow.")


def _render_result(container, report: RunReport) -> None:
    import streamlit as st

    score_percent = round(report.termination.best_score * 100.0, 2)
    container.subheader("Current Result")
    container.write(f"Run directory: `{report.run_dir}`")
    if report.generation.status == "completed":
        container.write(f"Similarity: **{score_percent}%**")
    else:
        container.write("Similarity: **not computed**")
    container.write(f"Termination: `{report.termination.reason}`")
    if report.generation.status == "skipped":
        container.info(report.generation.message)
    elif report.generation.status != "completed":
        container.error(f"Generation status: {report.generation.status} | {report.generation.message}")
    elif report.comparison is None:
        container.warning("No similarity comparison artifact was produced for the final result.")
    if report.warnings:
        container.warning("\n".join(report.warnings))
    container.write(report.prompt_package.final_prompt)

    text_tab, json_tab, loop_tab = container.tabs(["Text Outputs", "JSON Outputs", "Loop Details"])
    with text_tab:
        container_map = {
            "Detailed recreation text": report.prompt_package.final_prompt,
            "Concise generation prompt": report.prompt_package.generator_prompt,
            "Negative prompt": report.prompt_package.negative_prompt,
            "Critical constraints": "\n".join(report.visual_hierarchy.must_match + report.visual_hierarchy.must_avoid),
        }
        for title, value in container_map.items():
            with st.expander(title, expanded=title == "Detailed recreation text"):
                st.write(value)
    with json_tab:
        st.json(
            {
                "scene_memory": report.final_scene_memory.model_dump(mode="json") if report.final_scene_memory else None,
                "scene_map": report.scene_map.model_dump(mode="json"),
                "prompt_package": report.prompt_package.model_dump(mode="json"),
                "comparison": report.comparison.model_dump(mode="json") if report.comparison else None,
                "termination": report.termination.model_dump(mode="json") if report.termination else None,
            }
        )
    with loop_tab:
        st.json(
            {
                "question_history": [item.model_dump(mode="json") for item in report.question_history],
                "gap_history": [[gap.model_dump(mode="json") for gap in items] for items in report.gap_history],
                "iterations": [item.model_dump(mode="json") for item in report.iterations],
                "generation": report.generation.model_dump(mode="json"),
                "warnings": report.warnings,
            }
        )


if __name__ == "__main__":
    main()
