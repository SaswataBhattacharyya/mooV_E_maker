"""Save pipeline outputs from results dict."""
import json
from pathlib import Path
from datetime import datetime


def save_results(story_text, results):
    """Persist the full pipeline result and the original story to disk."""
    project_name = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(OUTPUT_DIR) / f"story_{project_name}"
    out_dir.mkdir(parents=True, exist_ok=True)

    files_saved = []

    # 0 — the raw story
    (out_dir / "00_story_raw.txt").write_text(story_text)
    files_saved.append("00_story_raw.txt")

    # 1 — each stage output as pretty JSON
    stage_names = {
        "stage_1": "01_story_structure",
        "stage_2": "02_character_design",
        "stage_3": "03_scene_mapping",
        "stage_4": "04_subscene_breakdown",
        "stage_5": "05_dialogue_generation",
        "stage_6": "06_visual_continuity_plan",
        "stage_7": "07_asset_plan",
        "stage_8": "08_keyframe_plan",
        "stage_9": "09_generation_queue",
    }

    for stage_id, basename in stage_names.items():
        if stage_id in results:
            data = results[stage_id]
            fp = out_dir / f"{basename}.json"
            fp.write_text(json.dumps(data, indent=2))
            files_saved.append(f"{basename}.json")

    return {
        "project_name": project_name,
        "output_dir": str(out_dir),
        "files_saved": files_saved,
        "count": len(files_saved),
    }
