# H3 shot prompt contract

Write one complete prompt for one bounded shot or cut. Use this order where relevant:

1. Reference role declarations, using the exact resolved `<Picture N>`, `<Video N>`, `<Audio N>` map.
2. What the target shot is and how it relates to the story/previous accepted cut.
3. Place, time, atmosphere, visual treatment and important continuity facts.
4. Character identity and blocking; action progression; framing, lens feel, camera movement, lighting and focus.
5. Dialogue with stable `(S1)`/`(S2)` voice bindings and `<d>[Language] exact line</d>` tags; keep performance instructions outside the dialogue tag.
6. Native generated soundscape/music intent and the intended end state for the next cut.

Keep exact user-provided story facts, character names, dialogue and event ordering. Mark Director-invented connective detail in its separate inference field. Do not put alternative prompts or per-asset creation prompts into the H3 main prompt. Asset-use intent informs the one main prompt; it is not an independent competing prompt.

Duration is planned by the Director from the action/dialogue, then checked against the selected graph. Do not cram speech that cannot plausibly fit. A fresh scene does not inherit a previous MP4 merely because it exists. When continuation is intended, select the relevant accepted prior video and explicitly specify whether its paired audio should contribute; text/story/world canon remains the persistent long-term context.

Refine returns a proposal, rationale, and warnings bound to the exact base prompt, shot plan, resolved reference map, and corpus version. It must not reorder, add, remove, or silently substitute media references. A changed map requires re-lint/refine before submission. Never edit source code, published styles, or the corpus during a production run.
