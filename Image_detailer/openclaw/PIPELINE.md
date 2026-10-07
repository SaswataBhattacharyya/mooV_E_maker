# Pipeline

Single canonical flow:

1. Create the run folder and copy the input image.
2. Run one broad VLM overview pass.
3. Build initial scene memory.
4. Rank unresolved gaps.
5. Generate one focused follow-up question for the highest-priority gap.
6. Ask the VLM that question.
7. Update scene memory.
8. Repeat until remaining gaps are low impact or the question-round limit is hit.
9. Produce:
   - `structured_scene_map.json`
   - `detailed_recreation_text.txt`
   - `concise_generation_prompt.txt`
   - `critical_constraints.txt`
10. If optional image generation is enabled, generate the image through `scripts/run_qwen_image_generation.sh`.
11. If optional image generation is enabled, score similarity with code.
12. If optional generation is enabled and similarity is below `80%`, restart from step 2.
13. If optional generation is disabled, stop after prompt outputs are written.
