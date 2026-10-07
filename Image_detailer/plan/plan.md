# Streamlit UI + VM Packaging Plan

## Summary
Build a Streamlit frontend for the existing `image_analyzer` repo that runs on a VM, supports single-image and batch workflows, and exposes both analysis outputs and orchestration visibility. The UI will sit on top of the current Python pipeline, plus a lightweight orchestration/event layer that records what ran, why it ran, what each module returned, and which layered descriptions were produced.

## Implementation Changes
- Add a Streamlit app for single-image path/upload input, batch folder input, output-root selection, and live run controls.
- Extend the pipeline with orchestration events, decision logging, and fixed layered descriptions.
- Preserve the existing CLI behavior while expanding the artifact bundle with `events.json`, `layers.json`, and numbered description files.
- Add a Streamlit launcher script and update VM bootstrap/dependency documentation.

## Public Interfaces
- New Streamlit entrypoint: `./scripts/run_streamlit_app.sh`
- New output files per image:
  - `events.json`
  - `layers.json`
  - `<image_stem>_desc_1.txt` through `<image_stem>_desc_6.txt`
- Existing CLI commands remain unchanged.

## Test Plan
- Verify orchestration event stages are emitted in expected flows.
- Verify layered description files are deterministically named from the image stem.
- Extend smoke coverage to ensure the expanded artifact bundle is written.

## Assumptions
- v1 uses the current repo pipeline plus explicit orchestration logs rather than a full OpenClaw runtime.
- Layered descriptions use a fixed six-layer schema.
- VM deployment remains script-driven with bootstrap plus a Streamlit launcher.
