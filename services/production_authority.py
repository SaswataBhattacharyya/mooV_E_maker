"""Resolve human/Director decision authority from immutable run configuration."""

GATES = frozenset({"story_review", "image_candidate_selection", "voice_selection",
                   "shot_workflow_render_approval"})


def director_controls(config, gate):
    if gate not in GATES:
        raise ValueError(f"Unknown decision gate: {gate}")
    mode = config.get("control_mode", "manual")
    return mode == "fully_automated" or (
        mode == "semi" and config.get("semi_gates", {}).get(gate, True) is False)
