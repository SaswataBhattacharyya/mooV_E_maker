import { expect, test } from "@playwright/test";

const duplicateA = { asset_id: "fx-a", category: "sfx", filename: "thunder-a.wav", label: "thunder", relative_path: "analyses/video_audio_analyzer/run-a/sfx/thunder-a.wav", available: true, duplicate: true, duplicate_group_id: "exact-abc", duplicate_group_size: 2, duplicate_basis: "exact_file_hash", start_time_sec: 1, end_time_sec: 4, source_video_id: "video-a", project_id: "project-a", size: 1200, content_url: "/audio-a" };
const duplicateB = { ...duplicateA, asset_id: "fx-b", filename: "thunder-b.wav", relative_path: "analyses/video_audio_analyzer/run-a/sfx/thunder-b.wav", start_time_sec: 8, end_time_sec: 11 };
const sameClassDifferentSound = { ...duplicateA, asset_id: "fx-c", filename: "thunder-c.wav", relative_path: "analyses/video_audio_analyzer/run-a/sfx/thunder-c.wav", duplicate: false, duplicate_group_id: undefined, classification_duplicate_candidate: true, classification_group_id: "class-thunder", classification_group_size: 3, classification_group_label: "thunder", start_time_sec: 13, end_time_sec: 16 };
const workflows = [{ workflow_id: "minimax_text", label: "Minimax H3 · Text only", available: true, file: "minimax_h3_t2v_api.json", accepted_slots: [], required_slots: [], fps: 24, description: "Text to video", reference_limits: {}, parameters: [] }];

async function mockSharedApis(page: import("@playwright/test").Page) {
  let assets = [duplicateA, duplicateB, sameClassDifferentSound];
  await page.route("**/api/video-repertoire/capabilities", (route) => route.fulfill({ json: { ffmpeg: true, ffprobe: true, yt_dlp: true, video_audio_analyzer_ready: true, legacy_video_count: 0 } }));
  await page.route("**/api/video-repertoire/assets", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/video-repertoire/youtube/jobs", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/video-repertoire/analysis/jobs", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/video-repertoire/audio-assets**", async (route) => {
    if (route.request().method() === "DELETE") {
      const body = route.request().postDataJSON();
      assets = assets.map((asset) => body.relative_paths.includes(asset.relative_path) ? { ...asset, available: false } : asset);
      await route.fulfill({ json: { deleted: body.relative_paths, failures: [], reclaimed_bytes: 2400, occurrence_metadata_preserved: true, source_media_preserved: true } });
      return;
    }
    await route.fulfill({ json: assets });
  });
  await page.route("**/api/video-repertoire/manual/workflows", (route) => route.fulfill({ json: workflows }));
  await page.route("**/api/video-repertoire/manual/assets", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/video-repertoire/manual/jobs", (route) => route.fulfill({ json: [] }));
}

test("audio duplicate candidates can be staged once for Manual Director", async ({ page }) => {
  await mockSharedApis(page);
  await page.goto("/video-repertoire");
  await page.getByRole("tab", { name: "Audio Assets" }).click();
  await expect(page.getByText("thunder-a.wav")).toBeVisible();
  await expect(page.getByText("Same-class review · 3")).toBeVisible();
  await page.getByRole("button", { name: "Select exact duplicates" }).click();
  await expect(page.getByText("2 selected · same-class grouping never selects/deletes automatically")).toBeVisible();
  await page.getByRole("button", { name: "Send selected to Manual Director" }).click();
  await expect(page).toHaveURL(/\/manual-director$/);
  await expect(page.getByText("2 staged references")).toBeVisible();
  await page.reload();
  await expect(page.getByText("2 staged references")).toBeVisible();
});

test("derived audio deletion confirms scope and retains event records", async ({ page }) => {
  await mockSharedApis(page);
  let confirmation = "";
  page.on("dialog", async (dialog) => { confirmation = dialog.message(); await dialog.accept(); });
  await page.goto("/video-repertoire");
  await page.getByRole("tab", { name: "Audio Assets" }).click();
  await page.getByRole("checkbox", { name: "Select thunder-a.wav" }).check();
  await page.getByRole("button", { name: "Delete selected" }).click();
  await expect.poll(() => confirmation).toContain("Original videos/source audio and event, transcript, and timestamp records will remain");
  await expect(page.getByText("Derived audio deleted; occurrence and timestamp metadata retained.")).toBeVisible();
});
