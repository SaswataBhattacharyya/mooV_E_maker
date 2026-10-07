# 1. Product map and page-by-page guide

## What the app is

The website is a set of connected but distinct workspaces, not one single wizard. The shared top navigation makes project/story work, media generation, audio tools, video-reference analysis, and manual generation reachable from anywhere. Some pages use a current project; other tools operate on independent jobs or on the shared Video Repertoire.

## Pages and routes

| Route | Page | Purpose and typical flow |
|---|---|---|
| `/` | Overview | Shows the current project if one is selected and links into Story Builder and Media Composer. Landing copy should be treated cautiously: some descriptions still say “later” or “reserved” even though routes now exist. |
| `/story` | Story Builder | Create/open a project, write a premise, save a draft, request story assistance, generate/edit/save story artifacts, start story automation, and start a production run when the required artifacts are ready. |
| `/canvas` | Story Canvas | Novel-oriented editing, loose-end review, focused revisions, then conversion of an approved revision into a scene-by-scene screenplay outline. |
| `/media` | Media Composer | Pick a discovered ComfyUI workflow, provide prompt/reference assets and supported parameters, submit a generation job, and inspect outputs. Workflow fields are inferred from local workflow files/catalog entries. |
| `/generate` | Generate | Production overview and links to image/video, audio, music/SFX, and dialogue reconstruction sections; shows runnable workflow catalog entries and lets the user finalize an output manifest. |
| `/image-detailer` | Image Detailer | Analyze an image with a Qwen-oriented interpretation plus optional CV/depth/OCR/subject evidence; can produce a generation brief. Model readiness is environment-dependent. |
| `/audio` | Audio Studio | Browse voice/model catalogs, add reference voice assets, map project characters to voice choices, submit timed/multicharacter TTS, and use speech/effect utilities. Some blocks are capability-gated. |
| `/audio-reconstruct` | Audio Reconstruct | Calibrate a character voice, prepare one dialogue part at a time, upload takes, compare ASR/transcript and accept a take. It is a human-operated recording workflow, not automatic voice cloning. |
| `/music-sound` | Music & Sound | Submit ACE-Step music and Control-Foley jobs, inspect capability status, and access bounded fine-tuning preparation. Requires the relevant ComfyUI workflows/nodes/models. |
| `/audio-tools` | Audio Utilities | Curated audio library, audio extraction/MP3 conversion, denoise and Demucs operations. These are explicit utility jobs, distinct from automatic video analysis. |
| `/automation` | Automation | Has two concepts on one page: project/story automation and an ordered audio-processing pipeline (timed TTS → split → emotion/effect change → stitch). Do not confuse this with the media worker itself. |
| `/status` | Project Status & Logs | Inspect project state and operational logs/status. |
| `/video-repertoire` | Video Repertoire | Upload/import/download source videos; analyze them; browse results and derived audio; keyword/semantic search; select clips/assets and hand them to Manual Director. |
| `/video-summariser` | Video Repertoire alias | Routes to the same React component as `/video-repertoire`; it is not a separate current page implementation. Backend still retains a legacy analyzer option. |
| `/manual-director` | Manual Director | Compose a prompt and reference inputs from Video Repertoire or local uploads, select one of the locally mapped workflows, adjust supported settings, submit, and review outputs. |

The route table is defined in `frontend/app/src/App.tsx`; navigation is defined in `frontend/app/src/components/AppShell.tsx`.

## Shared navigation state

- A selected project is commonly persisted in browser local storage and reused between Story Builder, audio pages, and generation pages.
- A global reasoning-provider control selects Codex or Ollama for eligible story/director reasoning calls. The selection is persisted server-side; an already-running automation run captures its starting provider.
- A bottom-of-screen run monitor polls project automation state and exposes pause/resume for eligible story automation runs.
- Video Repertoire and Manual Director use their own job records under the shared repertoire rather than the Story Builder project's six-artifact chain.

## Main user journeys

### Build story material

Overview → Story Builder → save project draft → generate/edit/save artifacts stage by stage (or start story automation) → review/edit output → move to Media Composer/Audio Studio/Generate.

### Create a media asset manually

Media Composer or Manual Director → choose a locally available workflow → provide prompt and required input files → submit to ComfyUI → poll job/history → store/output artifact. The workflow graph determines which controls and references are actually accepted.

### Analyze and reuse reference footage

Video Repertoire → upload/import or YouTube download → select video(s) → configure analysis options → run analysis → inspect full-video/scene/cut/audio results → semantic or keyword search → select result assets → send references to Manual Director.

### Process or make audio

Audio Studio for voices/TTS; Audio Reconstruct for part-by-part recorded dialogue; Music & Sound for music/SFX generation; Audio Utilities for deterministic operations; Automation for a reusable sequence of audio operations.

## Important terminology

- **Project**: Story Builder project folder/state, with six primary story artifacts and project media/output areas.
- **Video asset**: source video registered in Video Repertoire; YouTube downloads are source assets and should not be confused with deletable analysis jobs.
- **Analysis run/job**: a processing attempt with progress/events and derived results.
- **Scene**: a high-level shot/scene interval detected in a video.
- **Cut/clip**: a shorter segment bounded by detected edits/cuts, associated with a parent scene when available.
- **Reusable audio asset**: an explicitly collected voice/music/SFX/ambience/isolated derivative. Original analysis audio is not automatically the same thing as a reusable clip.
- **Workflow**: a local ComfyUI API graph plus an adapter/UI contract; a workflow appearing in a catalog does not guarantee its model/node dependencies are loaded.

