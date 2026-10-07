# Knowledge

Main reasoning path:

- VLM overview
- gap detection
- focused follow-up questioning
- scene memory refinement
- final prompt synthesis

Auxiliary evidence:

- YOLO detections
- Florence captions
- OCR text
- dominant color extraction

Important outputs:

- `memory/final_scene_memory.json`
- `outputs/structured_scene_map.json`
- `outputs/detailed_recreation_text.txt`
- `outputs/concise_generation_prompt.txt`
- `outputs/critical_constraints.txt`
- `comparisons/similarity_v*.json` when optional generation is enabled
- `reports/run_report.json`
