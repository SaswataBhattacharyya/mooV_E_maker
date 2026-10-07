# Current implementation status — released 7 October 2026

The original required implementation and representative acceptance gates are complete. This is the authoritative current handoff; older pending approvals, running jobs and flag-off instructions in the log and archive are historical. See [27_FINAL_RELEASE_2026_10_07.md](27_FINAL_RELEASE_2026_10_07.md) and [evidence/FINAL_PLAN_ACCEPTANCE_20261007.json](evidence/FINAL_PLAN_ACCEPTANCE_20261007.json).

## Closed packages

| Package | Exit evidence |
| --- | --- |
| Restart/browser | Actual persisted worker/prompt recovery, native Direct/Reference playback after HTTP restart/reload, queued UI cancellation and sibling preservation; deterministic restart/error/concurrency regressions. |
| D5/release | Three accepted native clips, exact hashes, corrected cut-01 compatibility, scene reset, empty owned staging and real playback. D5_RELEASE_20261006.json. |
| Full Direct | Configured Sol acceptance, native take, normal controller continuation exactly once and replay prevention. FULL_DIRECT_ACCEPTANCE_20261006.json. |
| Full Reference | Accepted text and three image masters, corrected clothing/native take, final normal Sol acceptance, actual same-scene continuation, replay prevention and new-scene reset. FULL_REFERENCE_ACCEPTANCE_20261006.json. |
| Navigation/handoff | Persistent flag enabled, four actual flag-off/on checks and two checks against the running normal website passed; legacy routes retained and operator guide updated. |

Reference take `86da118e-91a6-59a1-aca2-c36e7e6dfa61`, review `8af4d9d6-4f1f-4412-a2da-256fbf6a5cb0`, is accepted. SHA256 `9de2de0ad1bfcb7f7eb03580a74549f2e7a7c3e2f6ad86ebd5264968115b11b0`. The user confirmed the girl speaks and Aaron is the addressee, and previously accepted Aaron pronunciation. Both exact-file confirmations are persisted. Never ask these questions again or rerun the spent fourth review. Three ordinary claims and one single-use authorized speaker reassessment remain recorded; no budget reset, dubbing or new render occurred.

Fresh dialogue review can use sixteen timed CPU visual observations; cached review remains bounded by its saved evidence. Human confirmation never overrides extra speech, changed bytes or visual defects. The dedicated fourth-claim repair has fourteen regression cases; normal review accepted the same bytes without repeating ASR/vision inference.

## Final verification

Backend: **803 passed**, four existing FastAPI lifespan warnings. Frontend: **14 unit tests passed**, lint zero errors / thirteen existing warnings, TypeScript and Vite build passed. Maintained browser suite: **24 passed / 8 opt-in or separately covered tests skipped**; real navigation four isolated checks plus two normal-site checks passed. Live media quality is established by separate release manifests, not mocked clicks. Final read-only audit rehashed all five selected clips and verified native audio/video and healthy normal services.

All source changes were tested before documentation-only completion edits. Do not repeat broad suites or GPU acceptance without a new change/failure. Original historical snapshots remain in26_CURRENT_STATUS_ARCHIVE_2026_10_07.md. Optional FL2VA stays disabled/unverified; unavailable AddGuide/ControlNet and hosted cloning remain separately gated. Final-film stitching and rendering every planned Full shot are outside this upgrade.

## Runtime and preserved work

Normal website is running at **http://127.0.0.1:8081/production**, API3010, launcher session83317 / API PID815945 at handoff. ComfyUI3008 and Ollama11434 were reused without restart. Do not start a duplicate launcher. The persistent navigation setting is `frontend/app/.env.local`; rollback uses explicit `VITE_STORY_BUILDER_NEW_PRODUCTION_NAV=false` followed by frontend restart/build.

Startup was preceded by controller/queue inspection and did not change normal queue counts: takes accepted6/cancelled2/failed2/needs_review3 (all held Manual); stage tasks completed13/failed5; image jobs completed1; no active or queued work. Disposable Full continuation tasks are intentionally held before further provider/GPU dispatch with acceptance_checkpoint_hold; they are retained test evidence, not unfinished release work. Reference acceptance ledger/media remain under `/tmp/storybuilder-full-controller-acceptance-20261006-nlmgwm4y`; preserve this directory. D5/Direct outputs remain in canonical repository project output roots. Original rejected takes and spent claims remain intact.

No active render or provider review. One heavy GPU workload at a time, independent continuous temperature/utilization/clock monitoring: intervene83°C, maximum85°C, operator ceiling2100MHz. Never change locks or kill desktop work. Last observed idle45°C/6%/2086MHz; idle readings do not prove future render safety. Locks reset after power cycles. Release manifests record render peaks78–82°C and no watchdog trip.

Backups and restore instructions are in the final release record. Restore only selected source/config paths after comparing newer edits, never a ledger/media directory. The60% context preference remains; no runtime usage/control is exposed, so durable handoffs accompany configured automatic compaction. A prose summary does not compact runtime context.
