# Production workspace operator guide

Release status and exact ongoing jobs are in [12_CURRENT_STATUS.md](12_CURRENT_STATUS.md). Required release gates are closed; exact evidence is linked from current status.

## Start safely

Before starting the normal website, inspect its saved queues and any running ComfyUI prompt. Website startup resumes saved controllers; it can queue work. The normal website is currently running on8081; reuse it. Do not launch another copy.

ComfyUI is at http://127.0.0.1:3008. If it is unavailable, the local starter is `/home/riki/web_dev/setup_comfy_and-stuff/opencode/hermes_agent/start_comfyui_local.sh`; it leaves a reachable instance running. Once release checks pass and queues are understood, start the normal website from the repository with `./run_story_builder.sh`. Use the exact frontend URL printed by the launcher; its default is port8080, backend3010. Do not start a second launcher on occupied ports.

The tested H3 paths require backend opt-ins `STORY_BUILDER_ENABLE_DYNAMIC_H3=1` and `STORY_BUILDER_ENABLE_H3_T2V=1`. Missing files, nodes, verified smoke or service readiness still disable them. The new navigation opt-in is the literal frontend value `VITE_STORY_BUILDER_NEW_PRODUCTION_NAV=true`; set it only after release gates pass, then restart/rebuild Vite. Leaving it off preserves existing navigation. The workspace itself is `/production`.

After a later shutdown, inspect saved queues first. The tested environment can be selected without changing the system Python:

```bash
cd /home/riki/web_dev/story_builder
PATH=/home/riki/miniforge3/envs/react/bin:$PATH \
STORY_BUILDER_ENABLE_DYNAMIC_H3=1 \
STORY_BUILDER_ENABLE_H3_T2V=1 \
STORY_BUILDER_FRONTEND_PORT=8081 \
./run_story_builder.sh
```

Navigation is enabled persistently in `frontend/app/.env.local`. For rollback, explicitly set `VITE_STORY_BUILDER_NEW_PRODUCTION_NAV=false` and restart/rebuild the frontend; unsetting the shell variable alone does not override the file. Optional FL2VA remains disabled: no verified live smoke is recorded. Never use this command to bypass an unresolved acceptance hold.

## Make a short production

1. Choose or create a project and supply a story. Even a short story is required. Open its saved run to resume; creating another run starts another production.
2. Choose **control mode** separately from **making route**. Manual lets you approve/edit stages. Semi lets you choose which approvals stay with you. Full delegates the saved gates to the Director. Direct H3 does not require image masters; Reference-built uses accepted character/world images; Hybrid uses selected masters where requested.
3. Review story, scene and shot material. Accepted revisions remain saved. Changes create a new revision; do not overwrite accepted files to repair a held stage.
4. For Reference-built, generate/review only the required character/world masters. Select the correct identity. A dependent shot waits for its required master.
5. Audition and bind eligible local voices if desired. Speaker labels S1/S2 are local prompt labels; character identities and voice bindings remain stable. Generated dialogue/music/effects are optional separate assets, not automatic replacements for H3 native audio.
6. Open a shot and add images, videos or voice references with their purpose. Video soundtrack sharing is optional and uses the same clip/time interval. Audio numbering follows actual selected connections; adding paired sound can shift standalone voice numbers. Read the current tag map before finalizing the prompt.
7. Use Refine to inspect the proposed wording, then accept/edit/discard it. Changing reference order or assets requires validation again. Choose explicit preview0.4 or final0.98, duration, steps, seed and reference image sizing. Final0.98 means1344×768 at16:9, not a quality score.
8. Generate queues a durable take. Generate&Next can wait for the accepted predecessor in the same scene. Starting a new scene does not inherit the previous scene's video. Back/reload preserve saved state.
9. Select the take in **Production job queue** to inspect status, Director decisions and the native-audio player. Review both appearance and spoken words. Extra/garbled speech keeps the clip held even if the requested sentence is clear. Automatic review now uses cached CPU speech screening as well as visual evidence; uncertain recognition is not a guarantee of clean audio or speaker identity.

## Cancel and recover

**Stop take** cancels unsent work locally. For submitted work, the service reconciles the exact prompt before cleanup; it never treats an unrelated ComfyUI render as owned. An uncertain remote result stays held. Do not click Generate again or issue a new retry key merely because the website restarted. Open the saved run and inspect the exact prompt/output first. A failed or explicitly reconciled absent attempt can retry; a quality correction is a new preserved take with a bounded budget.

A scoped confirmation of an uncertain native-audio review is tied to the exact clip hash. The normal/restarted reviewer reads that saved evidence and reassesses the remaining requirements; confirmation does not override visual defects or authorize extra renders. Representative disposable acceptance continuations may be intentionally held before inference, with their request preserved and `acceptance_checkpoint_hold` recorded. This is an intentional stop of additional test shots, not a failed provider or lost video.

A saved provider-unavailable video review can be reopened with `scripts/retry_unavailable_video_review.py --help`: supply the existing ledger and exact project, run, take and review IDs. It defaults to inspection; `--retry` archives the failure and reopens only that review within its saved three-attempt budget. Stop the normal API first. It never renders and refuses quality holds, active leases and changed review IDs. Resume the normal review worker only after provider availability returns.

Replacing a parent preserves already accepted descendants and their original lineage. Unfinished dependent children require explicit review; the interface cannot promise a new parent is visually continuous with old accepted children.

## GPU and files

Run one heavy GPU workload at a time. Monitor temperature, utilization and graphics clock throughout the render. Current operator limits are an 83°C intervention cutoff below 85°C maximum and 2100MHz clock ceiling. The independent watchdog survives worker errors; telemetry uncertainty holds further work. Clock locks can reset after a power cycle: verify with `nvidia-smi` before heavy work. Do not assume an idle reading proves a long render is safe.

Generated media has one canonical home under `output/<project_id>/`; small state lives under `storage`. Shared Video Repertoire media stays linked. Leave original rejected media and prompt evidence intact. Temporary staging is owned by the exact job and cleaned only after remote state is settled. No final-film stitching is included in this upgrade.

## Troubleshooting

- **Workflow unavailable:** read its specific disabled reason. Opt-in flags, missing models/nodes and busy-service readiness are different causes. A readiness timeout creates no take or GPU submission.
- **Recovery required:** exact remote state is unresolved. Preserve the prompt ID and wait for reconciliation; do not duplicate the render.
- **Browser cannot play:** verify the registered content URL and file streams. The bundled ARM Playwright browser lacks H.264/AAC; installed system Chromium is used for actual playback checks. This test-browser limitation does not prove the saved MP4 is corrupt.
- **Director holds audio:** inspect the actual native clip and transcript. A name-spelling-only ambiguity holds the clip without an automatic retake; it does not prove wrong speech or certify correct pronunciation. Do not silence, dub or truncate the file and relabel it as accepted native generation.

Rollback is to explicitly set the new navigation flag false and restart/rebuild and keep legacy routes available. Source restoration requires comparing newer edits and extracting only affected paths from the recorded compressed backup; never restore a ledger or overwrite generated media as a code rollback.


If automatic frame descriptions disagree on the number of people, the clip stays held for evidence inspection. A count contradiction is not proof of a disappearing character. One exact-file reassessment can repeat the evidence review within its ordinary budget; this does not render, accept, or reset attempts. The original decision remains archived.


An old group review may have incomplete cards because its analyser limited descriptions to3subjects. Video review now has a larger bounded subject budget. A scoped confirmation of a new clip's name-spelling ambiguity can refresh those old cards and retain the same-file speech screen within the ordinary review budget. The Director must still pass the complete fresh visual evidence; a human audio confirmation does not approve the picture.

## Completed acceptance and speaker evidence

D5, Full Direct and Full Reference release manifests passed; normal navigation and legacy regression checks passed. No technical intervention is required to finish these gates. The accepted Reference clip has Mira speaking to Arun; the user accepts the spoken pronunciation Aaron. An addressed name is not the speaker's identity. Both confirmations belong to the exact corrected file hash and must not be requested again.

A narrowly authorized, single-use fourth evidence-only review preserved all three ordinary spent claims and the old decision. It was allowed only for uncertain speaker evidence with previously accepted pronunciation, and refused changed hashes, extra words, visual defects or an active reviewer. Normal Sol review then accepted the same native file. This does not establish an unlimited retry policy. Optional FL2VA remains disabled, and no all-shot rendering or final-film stitching is required for this release.
