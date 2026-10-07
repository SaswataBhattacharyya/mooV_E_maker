import { expect, test } from "@playwright/test";

test("video repertoire supports library, downloader, analyzer, and results views", async ({ page }) => {
  await page.goto("/video-repertoire");
  await expect(page.getByRole("heading", { name: /Video Repertoire/ })).toBeVisible();
  await expect(page.getByTestId("capabilities")).toContainText("FFmpeg");
  await expect(page.getByTestId("capabilities")).toContainText("yt-dlp");
  await expect(page.getByRole("tab", { name: "Library" })).toBeVisible();

  await page.getByRole("tab", { name: "YouTube Download" }).click();
  await expect(page.getByText("Review before downloading")).toBeVisible();
  await page.getByRole("button", { name: "Paste URLs" }).click();
  await expect(page.getByPlaceholder("One URL per line")).toBeVisible();
  await page.getByRole("button", { name: "URL File" }).click();
  await expect(page.locator('input[type="file"][accept*=".txt"]')).toBeVisible();

  await page.getByRole("tab", { name: "Analyze" }).click();
  await expect(page.getByText("Analyze selected videos")).toBeVisible();
  await expect(page.getByLabel("Scene/change sampling rate (FPS)")).toHaveValue("4");
  await expect(page.getByLabel("Run upgraded audio analyzer")).toBeChecked();
  await expect(page.getByLabel("Audio semantic embeddings")).toBeChecked();
  await expect(page.getByLabel("Frame shaving by visual change")).toBeChecked();
  await expect(page.getByLabel("Frame-change threshold")).toHaveValue("0.08");
  await expect(page.getByLabel("Preserve source audio bitstream")).toBeChecked();
  await expect(page.getByLabel("Create MP3 preview")).toBeChecked();

  await page.getByRole("tab", { name: "Results" }).click();
  await expect(page.getByText("Find reusable clips")).toBeVisible();
  await expect(page.getByLabel("Search corpus")).toHaveValue("analyzer");
  await expect(page.getByLabel("Top hits per page")).toHaveValue("5");
  await expect(page.getByLabel("Semantic search")).toBeChecked();
  await page.getByRole("tab", { name: "Audio Assets" }).click();
  await expect(page.getByText("Reusable audio library")).toBeVisible();
  await page.screenshot({ path: "test-results/video-repertoire.png", fullPage: true });
});

test("navigation exposes the video repertoire", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Video Repertoire" }).first().click();
  await expect(page).toHaveURL(/\/video-repertoire$/);
});

test("results show analyzer-selected frames with timestamped evidence", async ({ page }) => {
  const runId = "0123456789abcdef";
  const job = {
    job_id: "analysis-analyzer-fixture", kind: "analysis", status: "completed", progress: 100,
    stage: "completed", message: "Completed", request: {}, events: [], error: null,
    result: { videos: [], audio_analysis: [{
      asset_id: "video-fixture", status: "completed", run_id: runId,
      summary: "fixture run", statuses: { pe_av_embeddings: "completed" }, audio_events: [],
      audio: { preview_mp3: null }, transcript: { status: "completed" }, diarization: { status: "completed" },
      scenes: [{ scene_id: "scene_0001", start_time_sec: 0, end_time_sec: 2, frames: [{
        frame_id: "frame_0001", timestamp_sec: 0.5, artifact_path: "scenes/scene_0001/frame_0001.jpg",
        change_score: 0.2, camera_motion_score: 0.02, camera: { framing: "medium", motion: "static" },
        lighting: { brightness_level: "mid", contrast_level: "high" }, uncertainties: ["No semantic model"],
      }, {
        frame_id: "frame_0002", timestamp_sec: 1.25, artifact_path: null,
        change_score: 0.035, camera_motion_score: 0.14, camera: {}, lighting: {}, uncertainties: [],
      }] }],
    }] },
  };
  await page.route("**/api/video-repertoire/capabilities", (route) => route.fulfill({ json: { ffmpeg: true, ffprobe: true, yt_dlp: true, ollama_online: false, ollama_models: [], video_audio_analyzer_ready: true, legacy_video_count: 0 } }));
  await page.route("**/api/video-repertoire/assets", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/video-repertoire/youtube/jobs", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/video-repertoire/analysis/jobs", (route) => route.fulfill({ json: [job] }));
  await page.route(`**/api/video-audio-analyzer/runs/${runId}/artifacts/**`, (route) => route.fulfill({
    status: 200, contentType: "image/png",
    body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jzWQAAAAASUVORK5CYII=", "base64"),
  }));
  await page.goto("/video-summariser");
  await page.getByRole("tab", { name: "Results" }).click();
  const visualEvidence = page.getByTestId("analyzer-visual-evidence");
  await expect(visualEvidence).toContainText("Analyzer visual evidence");
  await visualEvidence.locator("summary").first().click();
  await page.getByText(/scene_0001 · 0\.00–2\.00 sec/).click();
  await expect(page.getByText(/Camera: medium \/ static/)).toBeVisible();
  await expect(page.getByText(/frame_0002 · 1\.25 sec · visual change 0\.035 · camera motion 0\.140/)).toBeVisible();
  await expect(page.getByText("Timestamp only; the sampled image was intentionally not persisted.")).toBeVisible();
  await expect(page.getByText(/Evidence limits: No semantic model/)).toBeVisible();
});

test("direct-video results show InternVideo3 summaries, timed clips, and audio cues without Ollama", async ({ page }) => {
  const direct = { job_id: "analysis-direct-fixture", kind: "analysis", status: "completed", progress: 100,
    stage: "completed", message: "Completed", request: {}, events: [], error: null,
    result: { primary_backend: "video_audio_analyzer", videos: [{ asset_id: "video-direct", title: "Direct clip fixture",
      summary_model: "InternVideo3", summary: { detailed_video_summary: "A person speaks, then gestures to the right." },
      scenes: [{ scene_id: "scene_0001", start_time_hms: "00:00:00", end_time_hms: "00:00:08",
        start_time_sec: 0, end_time_sec: 8,
        summary: "A person speaks in a close-up and gestures to the right.", transcript: "We should go.",
        cuts: [{ cut_id: "scene_0001_cut_0001", parent_scene_id: "scene_0001", start_time_sec: 0, end_time_sec: 3.5, duration_sec: 3.5, boundary_method: "motion_compensated_sampled_frame_difference", boundary_confidence: "estimated" }, { cut_id: "scene_0001_cut_0002", parent_scene_id: "scene_0001", start_time_sec: 3.5, end_time_sec: 8, duration_sec: 4.5, boundary_method: "motion_compensated_sampled_frame_difference", boundary_confidence: "estimated" }],
        audio_events: [{ event_id: "event_1", start_time_sec: 2.1, end_time_sec: 3.4, label: "Speech", confidence: 0.91, source: "HTS-AT" }],
        clip_path: "analyses/video_audio_analyzer/direct-run/embeddings/scene_0001.mp4" }] }], audio_analysis: [] } };
  await page.route("**/api/video-repertoire/capabilities", (route) => route.fulfill({ json: { ffmpeg: true, ffprobe: true, yt_dlp: true, ollama_online: false, ollama_models: [], video_audio_analyzer_ready: true, legacy_video_count: 0 } }));
  await page.route("**/api/video-repertoire/assets", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/video-repertoire/youtube/jobs", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/video-repertoire/analysis/jobs", (route) => route.fulfill({ json: [direct] }));
  await page.route("**/api/video-repertoire/artifacts/**", (route) => route.fulfill({ status: 200, contentType: "video/mp4", body: Buffer.from("fixture") }));
  await page.goto("/video-repertoire");
  await page.getByRole("tab", { name: "Results" }).click();
  await expect(page.getByText("A person speaks, then gestures to the right.")).toBeVisible();
  await expect(page.getByText(/InternVideo3/)).toBeVisible();
  await page.getByText(/scene_0001 · 00:00:00–00:00:08/).click();
  await expect(page.getByText("Audio cues in this clip")).toBeVisible();
  await expect(page.getByText("Cut-to-cut subdivisions (2)")).toBeVisible();
  await expect(page.getByRole("button", { name: "Stage cut" })).toHaveCount(2);
  await expect(page.getByText(/2\.10–3\.40 sec · Speech · 91% · HTS-AT/)).toBeVisible();
  await expect(page.getByLabel("Matched source video interval")).toHaveCount(0);
  await page.getByRole("button", { name: "Stage cut" }).first().click();
  await expect(page).toHaveURL(/manual-director/);
  const staged = await page.evaluate(() => JSON.parse(localStorage.getItem("story_builder.manual_director.selection") || "[]"));
  expect(staged).toEqual([expect.objectContaining({ asset_id: "video-direct", slot: "video", start_time_sec: 0, end_time_sec: 3.5 })]);
});

test("analysis job Stop waits for mocked cleanup and removes the job from the list", async ({ page }) => {
  let visible = true;
  let stopCalls = 0;
  const active = { job_id: "analysis-stop-fixture", kind: "analysis", status: "running", progress: 32,
    stage: "audio_extraction", message: "Extracting", request: {}, events: [], result: null };
  await page.route("**/api/video-repertoire/capabilities", (route) => route.fulfill({ json: { ffmpeg: true, ffprobe: true, yt_dlp: true, ollama_online: false, ollama_models: [], video_audio_analyzer_ready: true, legacy_video_count: 0 } }));
  await page.route("**/api/video-repertoire/assets", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/video-repertoire/youtube/jobs", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/video-repertoire/analysis/jobs", (route) => route.fulfill({ json: visible ? [active] : [] }));
  await page.route("**/api/video-repertoire/analysis/jobs/analysis-stop-fixture/stop", async (route) => {
    stopCalls += 1; visible = false;
    await route.fulfill({ json: { job_id: active.job_id, status: "stopped", deleted: true } });
  });
  page.on("dialog", (dialog) => dialog.accept());
  await page.goto("/video-repertoire");
  await page.getByRole("tab", { name: "Analyze" }).click();
  await expect(page.getByTestId("video-job")).toContainText(active.job_id);
  await page.getByRole("button", { name: `Stop ${active.job_id}` }).click();
  await expect.poll(() => stopCalls).toBe(1);
  await expect(page.getByTestId("video-job")).toHaveCount(0);
});

test("analysis job Delete sends the backend delete request", async ({ page }) => {
  let visible = true;
  let deleteCalls = 0;
  const completed = { job_id: "analysis-delete-fixture", kind: "analysis", status: "completed", progress: 100,
    stage: "completed", message: "Done", request: {}, events: [], result: { videos: [], audio_analysis: [] } };
  await page.route("**/api/video-repertoire/capabilities", (route) => route.fulfill({ json: { ffmpeg: true, ffprobe: true, yt_dlp: true, ollama_online: false, ollama_models: [], video_audio_analyzer_ready: true, legacy_video_count: 0 } }));
  await page.route("**/api/video-repertoire/assets", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/video-repertoire/youtube/jobs", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/video-repertoire/analysis/jobs", (route) => route.fulfill({ json: visible ? [completed] : [] }));
  await page.route("**/api/video-repertoire/analysis/jobs/analysis-delete-fixture", async (route) => {
    if (route.request().method() !== "DELETE") return route.fallback();
    deleteCalls += 1; visible = false;
    await route.fulfill({ json: { job_id: completed.job_id, status: "stopped", deleted: true } });
  });
  page.on("dialog", (dialog) => dialog.accept());
  await page.goto("/video-repertoire");
  await page.getByRole("tab", { name: "Analyze" }).click();
  await expect(page.getByTestId("video-job")).toContainText(completed.job_id);
  await page.getByRole("button", { name: `Delete ${completed.job_id}` }).click();
  await expect.poll(() => deleteCalls).toBe(1);
  await expect(page.getByTestId("video-job")).toHaveCount(0);
});
