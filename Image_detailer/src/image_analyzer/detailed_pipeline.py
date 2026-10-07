from __future__ import annotations

import json
import os
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from shutil import copy2
from typing import Any, Callable

from image_analyzer.config.settings import AppConfig
from image_analyzer.models.schemas import (
    CanvasSpec,
    ColorPaletteSpec,
    ComparisonIssue,
    ComparisonReport,
    GapRecord,
    GenerationConfig,
    GenerationResult,
    HybridSimilarityScore,
    IterationResult,
    LoopTermination,
    PromptCorrection,
    PromptPackage,
    QuestionRecord,
    RegionSpec,
    RunConfig,
    RunReport,
    SceneMemory,
    SceneMap,
    SceneObject,
    ScenePassResult,
    SemanticScoreBreakdown,
    SkySpec,
    VisualHierarchy,
)
from image_analyzer.providers.color import DominantColorProvider
from image_analyzer.providers.ollama import OllamaSynthesisProvider, configure_ollama_runtime
from image_analyzer.providers.optional_cv import FlorenceRegionProvider, TesseractOcrProvider, YoloDetectionProvider
from image_analyzer.similarity import compute_perceptual_similarity
from image_analyzer.utils.files import dump_json, dump_text, sha256_file
from image_analyzer.utils.image_ops import load_image_size


def run_image_flow(
    image_path: Path,
    config: AppConfig,
    *,
    output_root: Path | None = None,
    project_name: str | None = None,
    target_score: float | None = None,
    max_full_restarts: int | None = None,
    max_question_rounds: int | None = None,
    enable_generation: bool | None = None,
    event_callback: Callable[[dict[str, Any]], None] | None = None,
) -> RunReport:
    image_path = image_path.resolve()
    timestamp = datetime.now(timezone.utc)
    run_id = f"{timestamp.strftime('%Y-%m-%d_%H%M%S')}_{_slugify(project_name or config.detailed.default_project_name)}_{_slugify(image_path.stem)}"
    run_root = (output_root or config.detailed.run_root_dir).resolve()
    run_dir = run_root / run_id
    paths = _build_run_paths(run_dir)
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)

    copied_reference = paths["input"] / f"reference{image_path.suffix.lower()}"
    copy2(image_path, copied_reference)
    width, height = load_image_size(image_path)
    aspect_ratio = _aspect_ratio_string(width, height) or config.detailed.default_aspect_ratio
    target_similarity = target_score if target_score is not None else config.detailed.target_score
    max_restarts = max_full_restarts if max_full_restarts is not None else config.detailed.max_full_restarts
    max_rounds = max_question_rounds if max_question_rounds is not None else config.detailed.max_question_rounds
    generation_enabled = config.detailed.enable_generation_by_default if enable_generation is None else enable_generation

    run_config = RunConfig(
        project_name=project_name or config.detailed.default_project_name,
        reference_image=str(copied_reference),
        vlm_model=config.models.analysis_model,
        llm_model=config.models.structuring_model,
        generator_backend=config.generation.backend,
        comparison_model=config.models.comparison_model,
        iterations=max_restarts,
        aspect_ratio=aspect_ratio,
        enable_generation=generation_enabled,
        enable_comparison=generation_enabled,
        target_score=target_similarity,
        max_iterations=max_restarts,
        scene_weight=config.detailed.scene_weight,
        perceptual_weight=config.detailed.perceptual_weight,
        created_at=timestamp,
    )
    dump_json(paths["logs"] / "run_config.json", run_config.model_dump(mode="json"))
    _emit_event(event_callback, stage="setup", status="running", message="Created run folder and copied reference image.", payload={"run_dir": str(run_dir), "reference_image": str(copied_reference)})

    configure_ollama_runtime(
        max_loaded_models=config.models.ollama_max_loaded_models,
        num_parallel=config.models.ollama_num_parallel,
    )

    support_signals, aux_warnings = _collect_support_signals(image_path)
    warnings: list[str] = list(aux_warnings)
    model_calls: list[dict[str, Any]] = []
    _emit_event(event_callback, stage="auxiliary", status="completed", message="Collected auxiliary support signals.", payload={"warnings": aux_warnings, "support_signals": support_signals})

    vlm_client = OllamaSynthesisProvider(
        base_url=config.models.ollama_base_url,
        model_name=config.models.analysis_model,
        timeout_sec=config.models.ollama_timeout_sec,
    )
    structuring_client = OllamaSynthesisProvider(
        base_url=config.models.ollama_base_url,
        model_name=config.models.structuring_model,
        timeout_sec=config.models.ollama_timeout_sec,
    )

    passes: list[ScenePassResult] = []
    question_history: list[QuestionRecord] = []
    gap_history: list[list[GapRecord]] = []
    scene_memories: list[SceneMemory] = []

    initial_pass = _run_overview_pass(
        image_path=image_path,
        width=width,
        height=height,
        aspect_ratio=aspect_ratio,
        support_signals=support_signals,
        support_signal_word_limit=config.detailed.support_signal_word_limit,
        client=vlm_client,
        paths=paths,
        model_calls=model_calls,
        warnings=warnings,
    )
    passes.append(initial_pass)
    _emit_event(event_callback, stage="overview", status="completed", message="Completed broad VLM overview.", payload={"response": initial_pass.raw_response, "warnings": initial_pass.warnings})
    current_memory = _build_initial_scene_memory(initial_pass, support_signals, aspect_ratio)
    scene_memories.append(current_memory)
    dump_json(paths["memory"] / "scene_memory_v1.json", current_memory.model_dump(mode="json"))

    for round_index in range(1, max_rounds + 1):
        gaps = _identify_gaps(current_memory)
        gap_history.append(gaps)
        _emit_event(event_callback, stage="gap_detection", status="completed", message=f"Identified {len(gaps)} high-priority gaps.", payload={"round": round_index, "gaps": [gap.model_dump(mode='json') for gap in gaps]})
        dump_json(
            paths["passes"] / f"pass_{round_index * 2:02d}_gaps.json",
            [gap.model_dump(mode="json") for gap in gaps],
        )
        if not gaps:
            break
        next_gap = gaps[0]
        _emit_event(event_callback, stage="question_planning", status="running", message=f"Planning focused question for {next_gap.topic}.", payload={"round": round_index, "topic": next_gap.topic})
        question_prompt = _build_next_question_prompt(
            current_memory,
            next_gap,
            prompt_word_limit=config.detailed.prompt_word_limit,
            scene_memory_fact_limit=config.detailed.scene_memory_fact_limit,
        )
        question_artifact = vlm_client.analyze_visual_pass(image_path, question_prompt, num_predict=220)
        warnings.extend(question_artifact.warnings)
        model_calls.append({"phase": "focused_question", "round": round_index, "topic": next_gap.topic, "warnings": question_artifact.warnings})
        question_text = _extract_question(question_artifact.data.get("content", ""), next_gap)
        dump_text(paths["passes"] / f"pass_{round_index * 2 + 1:02d}_next_question.txt", question_text + "\n")
        _emit_event(event_callback, stage="question_planning", status="completed", message=f"Generated focused question for {next_gap.topic}.", payload={"round": round_index, "question": question_text})

        answer_prompt = _build_focused_extraction_prompt(next_gap.topic, question_text)
        answer_artifact = vlm_client.analyze_visual_pass(image_path, answer_prompt, num_predict=420)
        answer_text = _normalize_memory_text(str(answer_artifact.data.get("content", "")).strip())
        warnings.extend(answer_artifact.warnings)
        model_calls.append({"phase": "question_answer", "round": round_index, "topic": next_gap.topic, "warnings": answer_artifact.warnings})
        dump_text(paths["passes"] / f"pass_{round_index * 2 + 2:02d}_answer.txt", answer_text + "\n")
        _emit_event(event_callback, stage="question_answer", status="completed", message=f"Captured focused answer for {next_gap.topic}.", payload={"round": round_index, "topic": next_gap.topic, "answer": answer_text, "warnings": answer_artifact.warnings})

        question_history.append(
            QuestionRecord(
                iteration=round_index,
                question=question_text,
                answer=answer_text,
                topic=next_gap.topic,
            )
        )
        current_memory = _update_scene_memory(current_memory, next_gap, answer_text, round_index + 1)
        scene_memories.append(current_memory)
        dump_json(paths["memory"] / f"scene_memory_v{round_index + 1}.json", current_memory.model_dump(mode="json"))
        _emit_event(event_callback, stage="memory_update", status="completed", message=f"Updated scene memory to version {round_index + 1}.", payload={"round": round_index, "scene_memory": current_memory.model_dump(mode="json")})
        if len(current_memory.high_priority_gaps) == 0 and len(current_memory.uncertain) <= 2:
            break

    refined_scene_map = _scene_memory_to_scene_map(current_memory, support_signals, width, height, aspect_ratio)
    scene_map_prompt = _build_scene_map_refiner_prompt(
        current_memory,
        refined_scene_map,
        prompt_word_limit=config.detailed.prompt_word_limit,
        scene_memory_fact_limit=config.detailed.scene_memory_fact_limit,
    )
    refined_artifact = structuring_client.generate_json(scene_map_prompt, num_predict=1400)
    warnings.extend(refined_artifact.warnings)
    model_calls.append({"phase": "scene_map_refiner", "warnings": refined_artifact.warnings})
    refined_scene_map = _refine_scene_map(refined_scene_map, refined_artifact.data.get("json"))
    dump_json(paths["outputs"] / "structured_scene_map.json", refined_scene_map.model_dump(mode="json"))
    _emit_event(event_callback, stage="scene_map", status="completed", message="Built and refined structured scene map.", payload={"scene_map": refined_scene_map.model_dump(mode="json"), "warnings": refined_artifact.warnings})

    visual_hierarchy = _build_visual_hierarchy(refined_scene_map)
    prompt_package = _build_prompt_package(refined_scene_map, visual_hierarchy)
    dump_text(paths["outputs"] / "detailed_recreation_text.txt", prompt_package.final_prompt + "\n")
    dump_text(paths["outputs"] / "concise_generation_prompt.txt", prompt_package.generator_prompt + "\n")
    dump_text(paths["outputs"] / "critical_constraints.txt", "\n".join(visual_hierarchy.must_match + visual_hierarchy.must_avoid) + "\n")
    dump_json(paths["memory"] / "final_scene_memory.json", current_memory.model_dump(mode="json"))
    dump_json(paths["logs"] / "question_history.json", [item.model_dump(mode="json") for item in question_history])
    dump_json(paths["logs"] / "gap_history.json", [[gap.model_dump(mode="json") for gap in items] for items in gap_history])
    _emit_event(event_callback, stage="prompt_synthesis", status="completed", message="Prepared final recreation prompt and text outputs.", payload={"final_prompt": prompt_package.final_prompt, "generator_prompt": prompt_package.generator_prompt})

    generation_config = GenerationConfig(
        backend=config.generation.backend,
        width=config.generation.width,
        height=config.generation.height,
        steps=config.generation.steps,
        cfg=config.generation.cfg,
        sampler=config.generation.sampler,
        seed=config.generation.seed,
        model=config.generation.model,
        command_template=config.generation.command_template,
    )

    loop_results: list[IterationResult] = []
    best_score = -1.0
    best_result: IterationResult | None = None
    if generation_enabled:
        for restart_index in range(1, max_restarts + 1):
            iter_prompt = _prompt_for_restart(prompt_package, restart_index)
            _write_prompt_files(paths["outputs"], iter_prompt, restart_index)
            _emit_event(event_callback, stage="generation", status="running", message=f"Starting generation attempt {restart_index}.", payload={"attempt": restart_index, "prompt": iter_prompt.generator_prompt})
            generation = _generate_image_iteration(
                iteration=restart_index,
                paths=paths,
                prompt_package=iter_prompt,
                generation_config=generation_config,
                enabled=True,
            )
            _emit_event(event_callback, stage="generation", status="completed" if generation.output_image else "warning", message=generation.message, payload={"attempt": restart_index, "output_image": generation.output_image, "status": generation.status})
            comparison = None
            hybrid = None
            correction = None
            if generation.output_image:
                perceptual = compute_perceptual_similarity(copied_reference, Path(generation.output_image))
                code_score = perceptual.perceptual_similarity_score
                comparison = ComparisonReport(
                    overall_similarity_score=code_score,
                    semantic_similarity_score=0.0,
                    perceptual_similarity_score=code_score,
                    issues=[],
                    negative_prompt_additions=[],
                )
                hybrid = HybridSimilarityScore(
                    weighted_score=code_score,
                    semantic=SemanticScoreBreakdown(
                        composition_score=0.0,
                        object_score=0.0,
                        lighting_score=0.0,
                        constraint_score=0.0,
                        semantic_similarity_score=0.0,
                    ),
                    perceptual=perceptual,
                    scene_weight=0.0,
                    perceptual_weight=1.0,
                )
                dump_json(paths["comparisons"] / f"comparison_v{restart_index}.json", comparison.model_dump(mode="json"))
                dump_json(paths["comparisons"] / f"similarity_v{restart_index}.json", hybrid.model_dump(mode="json"))
                _emit_event(event_callback, stage="similarity", status="completed", message=f"Similarity for attempt {restart_index}: {round(code_score * 100.0, 2)}%.", payload={"attempt": restart_index, "similarity": code_score, "comparison": comparison.model_dump(mode="json"), "hybrid_score": hybrid.model_dump(mode="json")})
            loop_result = IterationResult(
                iteration=restart_index,
                prompt_package=iter_prompt,
                generation=generation,
                comparison=comparison,
                hybrid_score=hybrid,
                correction=correction,
                accepted=bool(hybrid and hybrid.weighted_score >= target_similarity),
            )
            loop_results.append(loop_result)
            score = hybrid.weighted_score if hybrid else 0.0
            if score > best_score:
                best_score = score
                best_result = loop_result
            if loop_result.accepted:
                _emit_event(event_callback, stage="loop_control", status="completed", message=f"Accepted attempt {restart_index} with similarity {round(score * 100.0, 2)}%.", payload={"attempt": restart_index, "similarity": score, "accepted": True})
                break
            if generation.status == "failed_runtime" and generation.output_image is None:
                _emit_event(event_callback, stage="loop_control", status="error", message="Generation failed before producing an image; stopping restart loop.", payload={"attempt": restart_index, "accepted": False, "generation_status": generation.status})
                break
            _emit_event(event_callback, stage="loop_control", status="warning", message=f"Similarity below threshold on attempt {restart_index}; restarting full process logic.", payload={"attempt": restart_index, "similarity": score, "accepted": False})

        termination = _build_termination(loop_results, target_similarity, best_score)
        final_result = best_result or IterationResult(
            iteration=0,
            prompt_package=prompt_package,
            generation=GenerationResult(enabled=False, status="failed_runtime", message="No generation result was produced."),
        )
    else:
        _emit_event(event_callback, stage="generation", status="completed", message="Image generation and similarity comparison were skipped; prompt outputs are ready.", payload={"generation_enabled": False})
        generation = GenerationResult(enabled=False, status="skipped", message="Image generation setup was not enabled for this run.")
        final_result = IterationResult(iteration=0, prompt_package=prompt_package, generation=generation, accepted=False)
        termination = LoopTermination(reason="prompt_only_completed", best_iteration=None, best_score=0.0, threshold_reached=False)
    report = RunReport(
        run_id=run_id,
        run_dir=str(run_dir),
        reference_image=str(copied_reference),
        scene_map=refined_scene_map,
        final_scene_memory=current_memory,
        visual_hierarchy=visual_hierarchy,
        prompt_package=final_result.prompt_package,
        passes=passes,
        question_history=question_history,
        gap_history=gap_history,
        generation=final_result.generation,
        comparison=final_result.comparison,
        correction=final_result.correction,
        iterations=loop_results,
        termination=termination,
        warnings=sorted(set(warnings)),
    )
    dump_text(paths["outputs"] / "final_prompt.txt", report.prompt_package.final_prompt + "\n")
    dump_json(paths["outputs"] / "final_prompt_package.json", _build_final_prompt_package(report, generation_config))
    dump_json(paths["reports"] / "run_report.json", report.model_dump(mode="json"))
    dump_text(paths["reports"] / "final_report.md", _build_final_report(report))
    dump_text(paths["logs"] / "model_calls.jsonl", "\n".join(json.dumps(item) for item in model_calls) + ("\n" if model_calls else ""))
    _emit_event(event_callback, stage="run_complete", status="completed", message="Unified image recreation flow completed.", payload={"run_dir": str(run_dir), "termination": report.termination.model_dump(mode="json"), "generated_image": report.generation.output_image})
    return report


def run_batch_flow(
    image_paths: list[Path],
    config: AppConfig,
    *,
    output_root: Path | None = None,
    project_name: str | None = None,
    enable_generation: bool | None = None,
    event_callback: Callable[[dict[str, Any]], None] | None = None,
) -> list[RunReport]:
    return [
        run_image_flow(
            path,
            config,
            output_root=output_root,
            project_name=project_name,
            enable_generation=enable_generation,
            event_callback=event_callback,
        )
        for path in image_paths
    ]


def run_detailed_pipeline(
    image_path: Path,
    config: AppConfig,
    *,
    output_root: Path | None = None,
    project_name: str | None = None,
    iterations: int | None = None,
    aspect_ratio: str | None = None,
    enable_generation: bool | None = None,
    enable_comparison: bool | None = None,
    target_score: float | None = None,
    max_iterations: int | None = None,
) -> RunReport:
    del iterations, aspect_ratio, enable_comparison
    return run_image_flow(
        image_path,
        config,
        output_root=output_root,
        project_name=project_name,
        target_score=target_score,
        max_full_restarts=max_iterations,
        enable_generation=enable_generation,
    )


def _emit_event(
    callback: Callable[[dict[str, Any]], None] | None,
    *,
    stage: str,
    status: str,
    message: str,
    payload: dict[str, Any] | None = None,
) -> None:
    if callback is None:
        return
    callback(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "status": status,
            "message": message,
            "payload": payload or {},
        }
    )


def _run_overview_pass(
    *,
    image_path: Path,
    width: int,
    height: int,
    aspect_ratio: str,
    support_signals: dict[str, Any],
    support_signal_word_limit: int,
    client: OllamaSynthesisProvider,
    paths: dict[str, Path],
    model_calls: list[dict[str, Any]],
    warnings: list[str],
) -> ScenePassResult:
    prompt = (
        "Analyze this image for faithful recreation. Do not write a poetic caption. "
        "Describe the overall scene structure, major objects, approximate composition, probable camera angle, "
        "dominant elements, and which details still need follow-up. "
        f"Image info: {image_path.name}, {width}x{height}, aspect {aspect_ratio}. "
        f"Auxiliary evidence: {_support_signal_summary(support_signals, support_signal_word_limit)}"
    )
    artifact = client.analyze_visual_pass(image_path, prompt, num_predict=1200)
    warnings.extend(artifact.warnings)
    raw = _normalize_memory_text(str(artifact.data.get("content", "")).strip())
    model_calls.append({"phase": "overview", "warnings": artifact.warnings})
    dump_text(paths["passes"] / "pass_01_overview.txt", raw + "\n")
    return ScenePassResult(
        pass_key="overview",
        title="Overview",
        prompt=prompt,
        raw_response=raw,
        structured={"summary": raw, "support_signals": support_signals},
        warnings=list(artifact.warnings),
    )


def _collect_support_signals(image_path: Path) -> tuple[dict[str, Any], list[str]]:
    width, height = load_image_size(image_path)
    warnings: list[str] = []
    colors = DominantColorProvider().analyze(image_path, {})
    ocr = TesseractOcrProvider().analyze(image_path, {})
    yolo = YoloDetectionProvider().analyze(image_path, {})
    florence = FlorenceRegionProvider().analyze(image_path, {})
    warnings.extend(colors.warnings)
    warnings.extend(ocr.warnings)
    warnings.extend(yolo.warnings)
    warnings.extend(florence.warnings)
    return (
        {
            "file_name": image_path.name,
            "sha256": sha256_file(image_path),
            "width": width,
            "height": height,
            "dominant_colors": colors.data.get("dominant_colors", []),
            "ocr_text": str(ocr.data.get("ocr_text", "")).strip(),
            "detections": yolo.data.get("detections", []),
            "caption": florence.data.get("caption", ""),
        },
        warnings,
    )


def _build_initial_scene_memory(pass_result: ScenePassResult, support_signals: dict[str, Any], aspect_ratio: str) -> SceneMemory:
    overview = pass_result.raw_response
    detections = support_signals.get("detections", [])
    elements = [str(item.get("label")) for item in detections if isinstance(item, dict)]
    if not elements:
        elements = [str(item) for item in _extract_candidate_elements(overview)]
    uncertain = _initial_uncertainties(overview, support_signals, elements)
    gaps = _rank_gaps(uncertain)
    return SceneMemory(
        version=1,
        scene_type=_scene_type_guess(overview),
        composition={"aspect_ratio_guess": aspect_ratio, "camera_angle": _camera_angle_guess(overview)},
        major_elements=elements,
        known=[line for line in _top_phrases(overview, fallback=["overview available"])],
        uncertain=uncertain,
        contradictions=[],
        high_priority_gaps=gaps,
        scene_map={},
    )


def _identify_gaps(scene_memory: SceneMemory) -> list[GapRecord]:
    if scene_memory.high_priority_gaps:
        return scene_memory.high_priority_gaps
    return _rank_gaps(scene_memory.uncertain)


def _build_next_question_prompt(
    scene_memory: SceneMemory,
    gap: GapRecord,
    *,
    prompt_word_limit: int,
    scene_memory_fact_limit: int,
) -> str:
    memory_summary = _scene_memory_summary(scene_memory, fact_limit=scene_memory_fact_limit)
    prompt = (
        "You are planning the next image-inspection question. "
        "Write exactly one short follow-up question, under 45 words, about the highest-impact unresolved visual detail. "
        "Ask for measurable details only: approximate position, size, shape, color, material, breed/type, lighting, or relation to nearby elements. "
        f"Current memory: {memory_summary} "
        f"Priority gap: {gap.topic}. "
        "Return the question only."
    )
    return _trim_words(prompt, prompt_word_limit)


def _extract_question(raw: str, gap: GapRecord) -> str:
    text = _normalize_memory_text(raw.strip())
    if text:
        return _trim_words(text.splitlines()[0].strip(), 45)
    return (
        f"Focus only on {gap.topic}. Describe its approximate position, size, shape, colors, textures, "
        "lighting behavior, and relation to surrounding elements."
    )


def _build_focused_extraction_prompt(topic: str, question: str) -> str:
    extra = ""
    lowered = topic.lower()
    if any(token in lowered for token in ["breed", "identity", "animal", "horse"]):
        extra = " If this is an animal or horse, identify the likely breed or type and cite visible conformation markers."
    return (
        f"Focus only on {topic}. {question} "
        "Return 5 to 8 short factual lines for image recreation. Prefer approximate percentages, relative size estimates, "
        "shapes, textures, color transitions, blur, and what should not be changed."
        f"{extra} Keep the answer under 150 words."
    )


def _update_scene_memory(scene_memory: SceneMemory, gap: GapRecord, answer_text: str, next_version: int) -> SceneMemory:
    updated_known = scene_memory.known + [_normalize_memory_text(answer_text)]
    remaining_uncertain = [item for item in scene_memory.uncertain if gap.topic.lower() not in item.lower()]
    if "unclear" in answer_text.lower() or "uncertain" in answer_text.lower():
        remaining_uncertain.append(f"{gap.topic} remains partially uncertain")
    updated_gaps = _rank_gaps(remaining_uncertain)
    return SceneMemory(
        version=next_version,
        scene_type=scene_memory.scene_type,
        composition=scene_memory.composition,
        major_elements=scene_memory.major_elements,
        known=updated_known,
        uncertain=remaining_uncertain,
        contradictions=scene_memory.contradictions,
        high_priority_gaps=updated_gaps,
        scene_map=scene_memory.scene_map,
    )


def _scene_memory_to_scene_map(
    scene_memory: SceneMemory,
    support_signals: dict[str, Any],
    width: int,
    height: int,
    aspect_ratio: str,
) -> SceneMap:
    dominant_names = [str(item.get("name", "")) for item in support_signals.get("dominant_colors", []) if isinstance(item, dict)]
    objects = _scene_objects_from_support(scene_memory, support_signals)
    known_text = " ".join(scene_memory.known).lower()
    subject_name = objects[0].name if objects else "main subject"
    return SceneMap(
        canvas=CanvasSpec(
            aspect_ratio=aspect_ratio,
            orientation="landscape" if width >= height else "portrait",
            camera_angle=_camera_angle_guess(known_text),
            lens_feel="natural telephoto-to-normal field framing",
            horizon_y_percent_from_top=_horizon_guess(scene_memory),
            vanishing_or_radiation_center={"x_percent": 50.0, "y_percent": 48.0},
        ),
        main_objects=objects,
        foreground=RegionSpec(
            region_y_percent="60-100",
            summary=_region_summary(
                scene_memory,
                region="foreground",
                default=f"Short grass foreground around the {subject_name}'s lower legs.",
            ),
            texture=_find_texture_lines(scene_memory, "foreground", fallback="short grass and hoof-level detail"),
            dominant_colors=dominant_names,
        ),
        middle_ground=RegionSpec(
            region_y_percent="35-60",
            summary=_region_summary(
                scene_memory,
                region="middle",
                default=f"{subject_name.capitalize()} stands in the pasture as the main subject.",
            ),
            texture=_find_texture_lines(scene_memory, "middle", fallback="subject coat and nearby grass texture"),
            dominant_colors=dominant_names,
        ),
        background=RegionSpec(
            region_y_percent="20-45",
            summary=_region_summary(
                scene_memory,
                region="background",
                default="Soft tree line and pasture background behind the subject.",
            ),
            texture=[],
            dominant_colors=dominant_names,
        ),
        sky=SkySpec(
            region_y_percent="0-45",
            cloud_direction="broad soft sky band" if "cloud" not in known_text else "broad layered sky structure",
            upper_left="soft pale upper-left sky",
            upper_right="soft pale upper-right sky",
            center="soft daylight sky above the tree line",
            motion="soft natural atmospheric motion",
            sharpness="natural, not hyper-sharp",
        ),
        color_palette=ColorPaletteSpec(
            dominant=dominant_names or ["blue", "violet", "pink"],
            saturation="vivid but natural",
            contrast="moderate to high",
        ),
        negative_constraints=_negative_constraints_from_memory(scene_memory),
        support_signals=support_signals,
    )


def _build_scene_map_refiner_prompt(
    scene_memory: SceneMemory,
    scene_map: SceneMap,
    *,
    prompt_word_limit: int,
    scene_memory_fact_limit: int,
) -> str:
    prompt = (
        "Refine the draft scene map JSON using only supported evidence. "
        "Do not invent objects, and do not repeat the same generic paragraph across foreground, middle ground, and background. "
        "Return strict JSON only. "
        f"Evidence summary: {_scene_memory_summary(scene_memory, fact_limit=scene_memory_fact_limit)} "
        f"Draft scene map: {json.dumps(scene_map.model_dump(mode='json'), ensure_ascii=True)}"
    )
    return _trim_words(prompt, prompt_word_limit)


def _refine_scene_map(scene_map: SceneMap, refined_payload: Any) -> SceneMap:
    if isinstance(refined_payload, dict):
        try:
            merged = _deep_merge(scene_map.model_dump(mode="json"), refined_payload)
            return SceneMap.model_validate(merged)
        except Exception:
            return scene_map
    return scene_map


def _build_visual_hierarchy(scene_map: SceneMap) -> VisualHierarchy:
    must_match = [
        scene_map.canvas.camera_angle,
        f"horizon around {scene_map.canvas.horizon_y_percent_from_top}% from top",
        scene_map.foreground.summary,
        scene_map.middle_ground.summary,
        scene_map.sky.cloud_direction,
    ]
    must_match.extend(
        f"{item.name} around x={item.center_x_percent or 'unknown'}%, y={item.center_y_percent or 'unknown'}%"
        for item in scene_map.main_objects
        if item.must_preserve or item.importance == "high"
    )
    return VisualHierarchy(
        must_match=[item for item in must_match if item],
        should_match=[
            f"palette: {', '.join(scene_map.color_palette.dominant[:6])}",
            scene_map.background.summary,
        ],
        can_vary_slightly=[
            "micro-texture details",
            "small cloud cluster edges",
            "fine ripple pattern",
        ],
        must_avoid=scene_map.negative_constraints,
    )


def _build_prompt_package(scene_map: SceneMap, hierarchy: VisualHierarchy) -> PromptPackage:
    object_lines = []
    for item in scene_map.main_objects:
        coords = []
        if item.center_x_percent is not None:
            coords.append(f"x={item.center_x_percent}%")
        if item.center_y_percent is not None:
            coords.append(f"y={item.center_y_percent}%")
        if item.width_percent is not None:
            coords.append(f"w={item.width_percent}%")
        if item.height_percent is not None:
            coords.append(f"h={item.height_percent}%")
        object_lines.append(
            f"{item.name}, role {item.role}, {' '.join(coords) if coords else 'position estimated'}, "
            f"{item.shape}, {item.surface}, color {item.color}"
        )
    base = (
        f"Realistic image in {scene_map.canvas.aspect_ratio} "
        f"{scene_map.canvas.orientation} format. Camera angle: {scene_map.canvas.camera_angle}. "
        f"Foreground: {scene_map.foreground.summary} Middle ground: {scene_map.middle_ground.summary} "
        f"Background: {scene_map.background.summary} Sky: {scene_map.sky.center}; {scene_map.sky.cloud_direction}."
    ).strip()
    precision = (
        f"Major objects: {'; '.join(object_lines) or 'main subject unresolved'}. "
        f"Foreground textures: {', '.join(scene_map.foreground.texture) or 'not resolved'}. "
        f"Palette: {', '.join(scene_map.color_palette.dominant)}. "
        f"Saturation {scene_map.color_palette.saturation}, contrast {scene_map.color_palette.contrast}."
    )
    negative = ", ".join(scene_map.negative_constraints) or "no extra invented elements"
    generator_prompt = f"{base}\n\n{precision}"
    final_prompt = (
        f"{generator_prompt}\n\nNon-negotiable constraints: {'; '.join(hierarchy.must_match)}. "
        f"Avoid: {'; '.join(hierarchy.must_avoid)}."
    )
    return PromptPackage(
        base_prompt=base,
        precision_prompt=precision,
        negative_prompt=negative,
        generator_prompt=generator_prompt,
        final_prompt=final_prompt,
        notes=["Prompt selected from iterative scene memory and auxiliary evidence."],
    )


def _prompt_for_restart(prompt_package: PromptPackage, restart_index: int) -> PromptPackage:
    if restart_index == 1:
        return prompt_package
    restart_suffix = f"\n\nRestart round {restart_index}: increase fidelity to composition, object placement, and critical constraints."
    return PromptPackage(
        base_prompt=prompt_package.base_prompt,
        precision_prompt=prompt_package.precision_prompt,
        negative_prompt=prompt_package.negative_prompt,
        generator_prompt=prompt_package.generator_prompt + restart_suffix,
        final_prompt=prompt_package.final_prompt + restart_suffix,
        notes=prompt_package.notes + [f"Restart round {restart_index}."],
    )


def _write_prompt_files(output_dir: Path, prompt_package: PromptPackage, restart_index: int) -> None:
    dump_text(output_dir / f"generator_prompt_v{restart_index}.txt", prompt_package.generator_prompt + "\n")
    dump_text(output_dir / f"negative_prompt_v{restart_index}.txt", prompt_package.negative_prompt + "\n")


def _generate_image_iteration(
    *,
    iteration: int,
    paths: dict[str, Path],
    prompt_package: PromptPackage,
    generation_config: GenerationConfig,
    enabled: bool,
) -> GenerationResult:
    metadata_path = paths["logs"] / f"generation_v{iteration}.json"
    prompt_file = paths["outputs"] / f"generator_prompt_v{iteration}.txt"
    negative_prompt_file = paths["outputs"] / f"negative_prompt_v{iteration}.txt"
    output_image = paths["generated"] / f"generated_v{iteration}.png"
    dump_json(
        metadata_path,
        generation_config.model_dump(mode="json")
        | {
            "prompt_file": str(prompt_file),
            "negative_prompt_file": str(negative_prompt_file),
            "output_image": str(output_image),
            "iteration": iteration,
        },
    )
    if not enabled:
        return GenerationResult(enabled=False, status="skipped", message="Generation disabled.", metadata_path=str(metadata_path))
    command_template = os.environ.get("IMAGE_ANALYZER_QWEN_IMAGE_COMMAND") or generation_config.command_template
    result = _execute_generation_command(
        command_template=command_template,
        prompt_file=prompt_file,
        negative_prompt_file=negative_prompt_file,
        output_image=output_image,
        generation_config=generation_config,
        iteration=iteration,
    )
    result.metadata_path = str(metadata_path)
    result.seed = generation_config.seed + (iteration - 1)
    return result


def _execute_generation_command(
    *,
    command_template: str,
    prompt_file: Path,
    negative_prompt_file: Path,
    output_image: Path,
    generation_config: GenerationConfig,
    iteration: int,
) -> GenerationResult:
    if not command_template:
        return GenerationResult(enabled=True, status="failed_runtime", message="No Qwen-image command template is configured.")
    command = command_template.format(
        prompt_file=prompt_file,
        negative_prompt_file=negative_prompt_file,
        output_image=output_image,
        width=generation_config.width,
        height=generation_config.height,
        steps=generation_config.steps,
        cfg=generation_config.cfg,
        sampler=generation_config.sampler,
        seed=generation_config.seed + (iteration - 1),
        model=generation_config.model,
    )
    completed = subprocess.run(shlex.split(command), capture_output=True, text=True)
    if completed.returncode != 0:
        return GenerationResult(
            enabled=True,
            status="failed_runtime",
            message=completed.stderr.strip() or completed.stdout.strip() or f"Generator exited with {completed.returncode}",
        )
    if not output_image.exists():
        return GenerationResult(enabled=True, status="failed_runtime", message="Generator completed but no output image was created.")
    return GenerationResult(enabled=True, status="completed", message=completed.stdout.strip() or "Generation completed.", output_image=str(output_image))


def _build_comparison_prompt(scene_map: SceneMap, hierarchy: VisualHierarchy) -> str:
    return (
        "Compare the generated image against the reference image. Focus on composition, object placement, object size, "
        "foreground/middle/background separation, lighting, color, texture, blur, and missing or extra elements. "
        "Return strict JSON with fields: overall_similarity_score, semantic_similarity_score, issues, negative_prompt_additions. "
        f"Reference expectations: {scene_map.model_dump(mode='json')} hierarchy: {hierarchy.model_dump(mode='json')}"
    )


def _build_comparison_report(payload: Any, hierarchy: VisualHierarchy) -> ComparisonReport:
    if isinstance(payload, dict):
        try:
            return ComparisonReport.model_validate(
                {
                    "overall_similarity_score": float(payload.get("overall_similarity_score", payload.get("semantic_similarity_score", 0.0))),
                    "semantic_similarity_score": float(payload.get("semantic_similarity_score", payload.get("overall_similarity_score", 0.0))),
                    "perceptual_similarity_score": float(payload.get("perceptual_similarity_score", 0.0)),
                    "issues": payload.get("issues", []),
                    "negative_prompt_additions": payload.get("negative_prompt_additions", []),
                }
            )
        except Exception:
            pass
    return ComparisonReport(
        overall_similarity_score=0.0,
        semantic_similarity_score=0.0,
        perceptual_similarity_score=0.0,
        issues=[
            ComparisonIssue(
                category="comparison",
                issue="Comparison response was not structured.",
                severity="medium",
                reference="full image",
                generated="unknown",
                prompt_fix="reinforce must-match constraints and keep composition stable",
            )
        ],
        negative_prompt_additions=hierarchy.must_avoid,
    )


def _build_prompt_correction(comparison_report: ComparisonReport, prompt_package: PromptPackage) -> PromptCorrection:
    changes = []
    for issue in comparison_report.issues:
        if issue.prompt_fix:
            changes.append(
                {
                    "old_instruction": prompt_package.generator_prompt,
                    "new_instruction": issue.prompt_fix,
                    "reason": issue.issue,
                }
            )
    return PromptCorrection(
        changes_to_prompt=changes,
        changes_to_negative_prompt=list(dict.fromkeys(comparison_report.negative_prompt_additions)),
    )


def _build_termination(iterations: list[IterationResult], target_score: float, best_score: float) -> LoopTermination:
    if not iterations:
        return LoopTermination(reason="no_iterations", best_iteration=None, best_score=0.0, threshold_reached=False)
    for item in iterations:
        if item.accepted and item.hybrid_score is not None:
            return LoopTermination(
                reason="threshold_met",
                best_iteration=item.iteration,
                best_score=item.hybrid_score.weighted_score,
                threshold_reached=True,
            )
    if all(item.generation.status == "failed_runtime" and item.generation.output_image is None for item in iterations):
        return LoopTermination(
            reason="generation_failed",
            best_iteration=iterations[-1].iteration,
            best_score=0.0,
            threshold_reached=False,
        )
    best_iteration = max(iterations, key=lambda item: item.hybrid_score.weighted_score if item.hybrid_score else 0.0).iteration
    return LoopTermination(
        reason="max_restarts",
        best_iteration=best_iteration,
        best_score=max(best_score, 0.0),
        threshold_reached=best_score >= target_score,
    )


def _build_final_prompt_package(report: RunReport, generation_config: GenerationConfig) -> dict[str, Any]:
    return {
        "reference_image": report.reference_image,
        "final_image": report.generation.output_image,
        "final_prompt": report.prompt_package.final_prompt,
        "negative_prompt": report.prompt_package.negative_prompt,
        "scene_memory": report.final_scene_memory.model_dump(mode="json") if report.final_scene_memory else None,
        "scene_map": report.scene_map.model_dump(mode="json"),
        "generator_settings": generation_config.model_dump(mode="json"),
        "best_iteration": report.termination.best_iteration if report.termination else None,
        "best_score": report.termination.best_score if report.termination else 0.0,
        "termination_reason": report.termination.reason if report.termination else "unknown",
    }


def _build_final_report(report: RunReport) -> str:
    termination = report.termination or LoopTermination(reason="unknown")
    similarity = 0.0
    if report.comparison is not None:
        similarity = report.comparison.overall_similarity_score * 100.0
    return "\n".join(
        [
            f"# Unified Image Recreation Report: {report.run_id}",
            "",
            f"- Reference image: `{report.reference_image}`",
            f"- Run directory: `{report.run_dir}`",
            f"- Best restart round: `{termination.best_iteration}`",
            f"- Best similarity: `{similarity:.2f}%`",
            f"- Termination: `{termination.reason}`",
            "",
            "## Final Prompt",
            report.prompt_package.final_prompt,
        ]
    ) + "\n"


def _scene_type_guess(text: str) -> str:
    lowered = text.lower()
    if "beach" in lowered:
        return "beach scene"
    if "horse" in lowered:
        return "horse in pasture scene"
    if "city" in lowered:
        return "urban scene"
    if "portrait" in lowered or "person" in lowered:
        return "person-centric scene"
    return "general scene"


def _camera_angle_guess(text: str) -> str:
    lowered = text.lower()
    if "low angle" in lowered or "close to the ground" in lowered:
        return "very low angle close to the surface"
    if "eye-level" in lowered:
        return "eye-level angle"
    if "overhead" in lowered:
        return "overhead angle"
    return "eye-level to low angle"


def _extract_candidate_elements(text: str) -> list[str]:
    lowered = text.lower()
    candidates = []
    for token in ["horse", "animal", "sky", "ocean", "water", "sand", "rock", "clouds", "sun", "trees", "field", "grass", "building", "person"]:
        if token in lowered:
            candidates.append(token)
    return candidates


def _initial_uncertainties(text: str, support_signals: dict[str, Any], elements: list[str]) -> list[str]:
    subject_is_animal = _looks_like_animal_subject(text, support_signals, elements)
    base = [
        "exact composition and horizon position",
        "main object placement and size",
    ]
    if subject_is_animal:
        base.append("subject identity, breed, and distinctive conformation markers")
    base.extend(
        [
        "foreground texture and reflection strength",
        "sky structure and dominant cloud masses",
        "lighting behavior and source visibility",
        "color transitions and saturation balance",
        "negative constraints and absent objects",
        ]
    )
    if "unclear" in text.lower():
        base.append("details marked unclear by overview")
    return base


def _rank_gaps(uncertain: list[str]) -> list[GapRecord]:
    ranked = []
    for index, item in enumerate(uncertain, start=1):
        ranked.append(GapRecord(topic=item, reason="High-impact missing recreation detail", priority=index))
    return ranked


def _scene_objects_from_support(scene_memory: SceneMemory, support_signals: dict[str, Any]) -> list[SceneObject]:
    detections = support_signals.get("detections", [])
    objects: list[SceneObject] = []
    for item in detections[:6]:
        if not isinstance(item, dict):
            continue
        bbox = item.get("bbox_px", {})
        width = max(float(support_signals.get("width", 1)), 1.0)
        height = max(float(support_signals.get("height", 1)), 1.0)
        center_x = ((float(bbox.get("x1", 0)) + float(bbox.get("x2", 0))) / 2.0) / width * 100.0
        center_y = ((float(bbox.get("y1", 0)) + float(bbox.get("y2", 0))) / 2.0) / height * 100.0
        width_percent = (float(bbox.get("x2", 0)) - float(bbox.get("x1", 0))) / width * 100.0
        height_percent = (float(bbox.get("y2", 0)) - float(bbox.get("y1", 0))) / height * 100.0
        objects.append(
            SceneObject(
                name=str(item.get("label", "object")),
                role="major object",
                center_x_percent=round(center_x, 2),
                center_y_percent=round(center_y, 2),
                width_percent=round(width_percent, 2),
                height_percent=round(height_percent, 2),
                shape="shape unresolved",
                color="color unresolved",
                surface="surface unresolved",
                importance="high" if float(item.get("confidence", 0.0)) > 0.5 else "medium",
                must_preserve=float(item.get("confidence", 0.0)) > 0.5,
            )
        )
    if not objects and any("rock" in item.lower() for item in scene_memory.major_elements):
        objects.append(
            SceneObject(
                name="single dark rock",
                role="foreground anchor",
                center_x_percent=78.0,
                center_y_percent=78.0,
                width_percent=9.0,
                height_percent=7.0,
                shape="rounded oval dome",
                color="dark cool-toned rock",
                surface="wet glossy surface",
                importance="high",
                must_preserve=True,
            )
        )
    if not objects and _looks_like_horse_scene(scene_memory, support_signals):
        objects.append(
            SceneObject(
                name=_horse_name_hint(scene_memory),
                role="main animal subject",
                center_x_percent=46.0,
                center_y_percent=56.0,
                width_percent=28.0,
                height_percent=68.0,
                shape="full standing horse profile with long mane and feathered lower legs",
                color="black and white piebald coat",
                surface="long flowing mane and natural coat texture",
                importance="high",
                must_preserve=True,
            )
        )
    return objects


def _best_known_line(scene_memory: SceneMemory, keyword: str, *, default: str) -> str:
    return _region_summary(scene_memory, region=keyword, default=default)


def _find_texture_lines(scene_memory: SceneMemory, keyword: str, *, fallback: str) -> list[str]:
    results = []
    region_terms = {
        "foreground": ["foreground", "grass", "ground", "hoof", "hooves", "legs", "lower"],
        "middle": ["middle", "coat", "mane", "subject", "horse", "animal"],
        "background": ["background", "tree", "treeline", "hill", "sky"],
    }
    for line in scene_memory.known:
        lowered = line.lower()
        keyword_hit = any(term in lowered for term in region_terms.get(keyword, [keyword]))
        broad_texture_hit = "texture" in lowered or "grass" in lowered
        if keyword == "middle":
            broad_texture_hit = broad_texture_hit or "coat" in lowered or "mane" in lowered
        if keyword_hit or broad_texture_hit:
            cleaned = _clean_summary_line(line)
            if cleaned and cleaned not in results:
                results.append(cleaned)
        if len(results) == 4:
            break
    return results or [fallback]


def _negative_constraints_from_memory(scene_memory: SceneMemory) -> list[str]:
    negatives = []
    for line in scene_memory.known + scene_memory.uncertain:
        lowered = line.lower()
        if lowered.startswith("no ") or lowered.startswith("not "):
            negatives.append(line)
    return negatives or ["no extra invented objects", "no major crop change", "not overly stylized"]


def _top_phrases(raw_response: str, *, fallback: list[str]) -> list[str]:
    parts = [item.strip(" .") for item in raw_response.replace("\n", " ").split(",")]
    results = [_clean_summary_line(item) for item in parts if item]
    results = [item for item in results if item][:4]
    return results or fallback


def _aspect_ratio_string(width: int, height: int) -> str:
    if width == 0 or height == 0:
        return "unknown"
    from math import gcd

    divisor = gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


def _slugify(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_") or "run"


def _build_run_paths(run_dir: Path) -> dict[str, Path]:
    return {
        "run_dir": run_dir,
        "input": run_dir / "input",
        "memory": run_dir / "memory",
        "passes": run_dir / "passes",
        "outputs": run_dir / "outputs",
        "generated": run_dir / "generated",
        "comparisons": run_dir / "comparisons",
        "reports": run_dir / "reports",
        "logs": run_dir / "logs",
    }


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _support_signal_summary(support_signals: dict[str, Any], word_limit: int) -> str:
    detections = [
        str(item.get("label", "")).strip()
        for item in support_signals.get("detections", [])
        if isinstance(item, dict) and str(item.get("label", "")).strip()
    ]
    colors = [
        str(item.get("name", "")).strip()
        for item in support_signals.get("dominant_colors", [])
        if isinstance(item, dict) and str(item.get("name", "")).strip()
    ]
    caption = support_signals.get("caption", "")
    if isinstance(caption, dict):
        caption = json.dumps(caption, ensure_ascii=True)
    summary = (
        f"detections={detections[:6] or ['none']}; "
        f"colors={colors[:6] or ['unresolved']}; "
        f"ocr={str(support_signals.get('ocr_text', '')).strip() or 'none'}; "
        f"caption={str(caption).strip() or 'none'}"
    )
    return _trim_words(summary, word_limit)


def _scene_memory_summary(scene_memory: SceneMemory, *, fact_limit: int) -> str:
    facts = [_clean_summary_line(item) for item in scene_memory.known if _clean_summary_line(item)]
    gaps = [item.topic for item in scene_memory.high_priority_gaps[:3]]
    return (
        f"scene_type={scene_memory.scene_type}; "
        f"major_elements={scene_memory.major_elements[:6]}; "
        f"composition={scene_memory.composition}; "
        f"known={facts[:fact_limit]}; "
        f"uncertain={scene_memory.uncertain[:3]}; "
        f"priority_gaps={gaps}"
    )


def _trim_words(text: str, limit: int) -> str:
    words = text.split()
    if len(words) <= limit:
        return text.strip()
    return " ".join(words[:limit]).strip()


def _clean_summary_line(text: str) -> str:
    cleaned = _normalize_memory_text(text)
    if not cleaned:
        return ""
    return _trim_words(cleaned, 28)


def _looks_like_animal_subject(text: str, support_signals: dict[str, Any], elements: list[str]) -> bool:
    lowered = text.lower()
    if any(token in lowered for token in ["horse", "animal", "pony", "stallion", "mare"]):
        return True
    if any(token in " ".join(elements).lower() for token in ["horse", "animal", "pony"]):
        return True
    caption = str(support_signals.get("caption", "")).lower()
    return any(token in caption for token in ["horse", "animal", "pony", "stallion", "mare"])


def _looks_like_horse_scene(scene_memory: SceneMemory, support_signals: dict[str, Any]) -> bool:
    haystack = " ".join(scene_memory.major_elements + scene_memory.known + scene_memory.uncertain).lower()
    caption = str(support_signals.get("caption", "")).lower()
    return "horse" in haystack or "horse" in caption


def _horse_name_hint(scene_memory: SceneMemory) -> str:
    haystack = " ".join(scene_memory.known).lower()
    if "gypsy" in haystack or "vanner" in haystack:
        return "Gypsy Vanner horse"
    return "horse"


def _horizon_guess(scene_memory: SceneMemory) -> float:
    known = " ".join(scene_memory.known).lower()
    if "slightly below center" in known:
        return 48.0
    if "above the middle" in known or "above center" in known:
        return 44.0
    return 48.0


def _region_summary(scene_memory: SceneMemory, *, region: str, default: str) -> str:
    region_keywords = {
        "foreground": ["foreground", "grass", "hooves", "legs", "lower"],
        "middle": ["middle", "subject", "horse", "animal", "stands", "center"],
        "background": ["background", "tree", "treeline", "hill", "pasture", "horizon"],
    }
    generic_phrases = {
        "the image features",
        "the image depicts",
        "central focus",
        "overall composition",
        "should not be altered",
        "scene analysis",
        "overall scene structure",
    }
    for line in scene_memory.known:
        lowered = line.lower()
        if any(keyword in lowered for keyword in region_keywords.get(region, [region])):
            if any(phrase in lowered for phrase in generic_phrases) and len(lowered.split()) > 18:
                continue
            cleaned = _clean_summary_line(line)
            if cleaned:
                return cleaned
    return default


def _normalize_memory_text(text: str) -> str:
    cleaned = text.replace("\r", "\n")
    normalized_lines: list[str] = []
    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        while line.startswith("#"):
            line = line[1:].strip()
        if line.startswith(("-", "*")):
            line = line[1:].strip()
        line = " ".join(line.split())
        if not line:
            continue
        lowered = line.lower()
        if lowered in {"scene analysis:", "overall scene structure:"}:
            continue
        normalized_lines.append(line)
    normalized = " ".join(normalized_lines)
    normalized = normalized.replace("Scene Analysis:", "").replace("Overall Scene Structure:", "")
    normalized = " ".join(normalized.split()).strip(" .")
    return normalized
