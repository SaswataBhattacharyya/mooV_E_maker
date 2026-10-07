# H3 reference roles (local ComfyUI graph)

Use only roles supported by the selected and preflighted graph. For the tested local R2V graph, references are numbered in resolved graph order: images are `<Picture 1..N>`; for each video, its paired soundtrack (when connected) is assigned an `<Audio N>` immediately before that `<Video N>`; standalone audio references follow. The compiler's `ResolvedReferenceMap` is authoritative—never guess numbering.

For every connected reference, state both what it contributes and what must not transfer:

- Images can provide character identity, costume, props, a location/world layout, visual style, or a composition anchor. State which subject or scene features to preserve and whether the reference background should be ignored.
- Videos can provide action/choreography, camera movement, shot rhythm/cuts, style, or immediate previous-shot state. Distinguish a motion/style reference from an actual continuation/edit request; ordinary R2V is not pixel-preserving video editing.
- A paired `<Audio N>` is only the soundtrack of its corresponding `<Video N>` when that pairing is present in the resolved map. Decide whether to transfer dialogue, impacts, timing, ambience, or nothing. Do not include it by accident.
- Standalone audio can provide a stable voice/timbre, a particular performance, or a deliberate music/SFX reference. Bind character voice samples to stable speaker IDs such as `(S1)`; never assume the model will infer the face/voice mapping.

Speaker IDs identify voice sources; `<Subject N>` identifies a visible subject. Declare the mapping explicitly. Use only references needed for this shot. Changing slot order or paired-audio selection changes tags and makes the old prompt stale. Remove unused connected assets rather than asking the model to ignore a confusing surplus set.

Do not claim exact pose coordinates, exact camera paths, pixel preservation, or exact waveform copying from a reference unless a separately tested deterministic tool guarantees it. If exact dialogue audio is required, preserve/mix that approved waveform downstream instead of promising generative reconstruction.
