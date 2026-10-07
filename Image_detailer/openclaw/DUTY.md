# Duty

Priorities:

1. Build a usable scene memory, not a one-shot caption.
2. Prioritize high-impact missing details first:
   composition, object placement, size, lighting, color, texture, blur, and perspective.
3. Use auxiliary providers as support signals only.
4. Prefer measurable statements:
   approximate position, relative size, shape, material, color transitions, and constraints.
5. Treat prompt creation as the default successful path. Only enter the generation/restart loop when optional image generation is enabled.
6. If a model-load or GPU-resource failure appears, mitigate it:
   check active Ollama models, unload competing models, and retry once before reporting failure.
