from __future__ import annotations

from pathlib import Path

from video_scene_summarizer.config.settings import load_settings
from video_scene_summarizer.graph.workflow import run_analysis_stage


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    import streamlit as st

    config = load_settings(PROJECT_ROOT)
    st.set_page_config(page_title="Video Scene Summarizer", layout="wide")
    st.title("Video Scene Summarizer")
    st.caption("Cut-based video analysis with keyframe detailing, frame deltas, transcript fusion, and final stitched summaries.")
    st.info(f"Direct Ollama analysis model: `{config.visual_model_path}` · Cross-scene continuity runs automatically for 2+ scenes.")

    with st.sidebar:
        input_dir = Path(st.text_input("Input video folder", value=str(config.downloads_dir))).expanduser()
        output_root = Path(st.text_input("Output folder", value=str(config.output_dir))).expanduser()
        use_transcript_fusion = st.checkbox("Use transcript fusion", value=config.transcript_fusion_default)
        reuse_cache = st.checkbox("Reuse cache", value=True)
        skip_existing = st.checkbox("Skip existing outputs", value=True)
        use_frame_shaving = st.checkbox("Use frame shaving", value=config.use_frame_shaving_default)
        extract_fps = st.number_input(
            "Frame extraction FPS",
            min_value=0.5,
            max_value=24.0,
            value=float(config.extract_fps or config.analysis_fps),
            step=0.5,
        )
        use_scene_compaction = st.checkbox("Compact scene text", value=config.use_compaction_default)
        delete_frame_images = st.checkbox("Delete saved frame images after run", value=config.delete_frames_after_analysis_default)

    run = st.button("Run analysis", type="primary")
    if not run:
        return

    progress = st.empty()
    log_slot = st.empty()
    error_slot = st.empty()
    preview_slot = st.empty()
    status_slot = st.empty()
    result_slot = st.container()
    events: list[dict[str, object]] = []
    error_events: list[dict[str, object]] = []
    if "scene_preview_items" not in st.session_state:
        st.session_state.scene_preview_items = []
    if "scene_preview_offset" not in st.session_state:
        st.session_state.scene_preview_offset = 0
    st.session_state.scene_preview_items = []
    st.session_state.scene_preview_offset = 0

    def on_event(event: dict[str, object]) -> None:
        events.append(event)
        if event.get("status") == "error":
            error_events.append(event)
            status_slot.error(f"{event['stage']} [{event['status']}] {event['message']}")
        elif event.get("status") == "warning":
            status_slot.warning(f"{event['stage']} [{event['status']}] {event['message']}")
        else:
            status_slot.info(f"{event['stage']} [{event['status']}] {event['message']}")
        lines = [f"{item['timestamp']} | {item['stage']} | {item['status']} | {item['message']}" for item in events[-40:]]
        log_slot.code("\n".join(lines), language="text")
        if error_events:
            error_lines = [f"{item['timestamp']} | {item['stage']} | {item['message']}" for item in error_events[-20:]]
            error_slot.error("\n".join(error_lines))
        else:
            error_slot.empty()
        if event.get("stage") == "scene_preview":
            payload = event.get("payload", {}) if isinstance(event.get("payload"), dict) else {}
            preview_image = str(payload.get("preview_image", "")).strip()
            if preview_image:
                st.session_state.scene_preview_items.append(
                    {
                        "scene_id": str(payload.get("scene_id", "")),
                        "label": f"{payload.get('scene_id', '')} [{payload.get('scene_start', '')} - {payload.get('scene_end', '')}]",
                        "image": preview_image,
                    }
                )
                _render_scene_preview_strip(preview_slot)

    progress.info("Running analysis...")
    error_slot.empty()
    _render_scene_preview_strip(preview_slot)
    result = run_analysis_stage(
        config=config,
        input_dir=input_dir,
        output_root=output_root,
        keep_downloaded_videos=True,
        use_transcript_fusion=use_transcript_fusion,
        reuse_cache=reuse_cache,
        skip_existing=skip_existing,
        use_frame_shaving=use_frame_shaving,
        extract_fps=float(extract_fps),
        use_scene_compaction=use_scene_compaction,
        delete_frame_images=delete_frame_images,
        event_callback=on_event,
    )
    progress.success("Analysis complete.")
    _render_scene_preview_strip(preview_slot)
    _render_results(result_slot, result)


def _shift_preview(direction: int) -> None:
    import streamlit as st

    items = st.session_state.get("scene_preview_items", [])
    max_offset = max(0, len(items) - 4)
    next_offset = st.session_state.get("scene_preview_offset", 0) + direction
    st.session_state.scene_preview_offset = max(0, min(max_offset, next_offset))


def _render_scene_preview_strip(container) -> None:
    import streamlit as st

    container.empty()
    with container:
        st.markdown("**Scene previews**")
        items = st.session_state.get("scene_preview_items", [])
        if not items:
            st.caption("Scene preview images will appear here as scenes start analysis.")
            return
        control_cols = st.columns([0.08, 0.84, 0.08])
        with control_cols[0]:
            st.button("◀", key="scene_preview_left", on_click=_shift_preview, args=(-1,))
        with control_cols[2]:
            st.button("▶", key="scene_preview_right", on_click=_shift_preview, args=(1,))
        offset = st.session_state.get("scene_preview_offset", 0)
        window = items[offset : offset + 4]
        preview_cols = control_cols[1].columns(max(len(window), 1))
        for col, item in zip(preview_cols, window):
            with col:
                image_path = Path(item["image"])
                if image_path.exists():
                    st.image(str(image_path), caption=item["label"], use_container_width=True)
                else:
                    st.caption(item["label"])
        if len(items) > 4:
            st.caption(f"Showing scenes {offset + 1}-{offset + len(window)} of {len(items)}")


def _render_results(container, result: dict) -> None:
    import streamlit as st

    processed = result.get("processed_videos", [])
    errors = result.get("errors", [])
    skipped = result.get("skipped_videos", [])
    container.subheader("Run Summary")
    container.write(f"Processed videos: {len(processed)}")
    if skipped:
        container.write(f"Skipped videos: {len(skipped)}")
    if errors:
        container.error("\n".join(errors))

    for record in processed:
        with container.expander(record.title, expanded=True):
            scenes = record.metadata.get("_scenes", [])
            summary = record.metadata.get("_final_summary")
            if summary:
                st.markdown("**Final summary**")
                st.write(summary.detailed_video_summary)
                if summary.video_story_text:
                    st.markdown("**Threaded video story**")
                    st.write(summary.video_story_text)
                st.markdown("**Cross-scene continuity**")
                if not summary.scene_transitions:
                    st.caption("This video has fewer than two analyzed scenes, so no transition pass was required.")
                for transition in summary.scene_transitions:
                    with st.expander(f"{transition.from_scene_id} → {transition.to_scene_id}"):
                        st.write(transition.narrative_connection or "No narrative connection established.")
                        st.json(transition.to_dict())
            for scene in scenes:
                tabs = st.tabs(["Scene Text", "Keyframes", "Deltas", "Transcript"])
                with tabs[0]:
                    st.markdown(f"**{scene.scene_id}** `{scene.start_time_hms} - {scene.end_time_hms}`")
                    st.write(scene.scene_compiled_text)
                with tabs[1]:
                    for analysis in scene.keyframe_analyses:
                        image_path = Path(analysis.frame_path)
                        if image_path.exists():
                            st.image(str(image_path), caption=f"{analysis.frame_id} @ {analysis.timestamp_sec:.2f}s", use_container_width=True)
                        st.write(analysis.detailed_description)
                with tabs[2]:
                    if not scene.frame_deltas:
                        st.write("No delta records saved for this scene.")
                    for delta in scene.frame_deltas:
                        st.markdown(f"**{delta.pair_id}** `{delta.previous_timestamp_sec:.2f}s -> {delta.current_timestamp_sec:.2f}s`")
                        st.write(delta.natural_language_delta)
                        st.json(delta.to_dict())
                with tabs[3]:
                    st.write(scene.transcript_text or "No transcript slice available.")


if __name__ == "__main__":
    main()
