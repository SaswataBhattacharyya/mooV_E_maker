import { expect, test } from "@playwright/test";

const workflows = [
  { workflow_id: "minimax_text", label: "Minimax H3 · Text only", available: true, file: "minimax_h3_t2v_api.json", accepted_slots: [], required_slots: [], fps: 24,
    description: "Text-to-video with generated audio; no media reference inputs.", reference_limits: {}, parameters: [{ key: "duration_seconds", label: "Duration (seconds)", kind: "number", default: 5, min: 2, max: 10, step: 0.1 }] },
  { workflow_id: "minimax_references", label: "Minimax H3 · Reference images", available: true, file: "minimax_h3_r2v_api.json", accepted_slots: ["reference_images"], required_slots: ["reference_images"], fps: 24,
    description: "Accepts 1–3 reference images.", reference_limits: { reference_images: { min: 1, max: 3, max_bytes_each: 41943040 } }, parameters: [] },
  { workflow_id: "wan_first_last", label: "WAN 2.2 · First + last frame", available: true, file: "wan2_2_flf2v_api.json", accepted_slots: ["first_frame", "last_frame"], required_slots: ["first_frame", "last_frame"], fps: 16,
    description: "Requires first and last frame images.", reference_limits: {}, parameters: [] },
];

test("Manual Director validates workflows and stages a generation without duplicating assets", async ({ page }) => {
  let created = 0;
  await page.route("**/api/video-repertoire/manual/workflows", (route) => route.fulfill({ json: workflows }));
  await page.route("**/api/video-repertoire/manual/assets", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/video-repertoire/manual/jobs", async (route) => {
    if (route.request().method() === "POST") {
      created += 1;
      await route.fulfill({ status: 202, json: { run_id: "manual-012345abcdef", status: "queued", stage: "queued", progress: 0,
        message: "Waiting", outputs: [], created_at: new Date().toISOString(), updated_at: new Date().toISOString() } });
      return;
    }
    await route.fulfill({ json: [] });
  });
  await page.route("**/api/video-repertoire/assets", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/video-repertoire/audio-assets?category=all", (route) => route.fulfill({ json: [] }));
  await page.goto("/manual-director");
  await expect(page.getByRole("heading", { name: "Manual Director" })).toBeVisible();
  await expect(page.getByTestId("manual-run")).toBeDisabled();
  await page.getByTestId("manual-prompt").fill("A cinematic wide shot of a lighthouse during a storm");
  await expect(page.getByTestId("manual-run")).toBeEnabled();
  await page.getByTestId("manual-run").click();
  await expect.poll(() => created).toBe(1);
  await expect(page.getByText("manual-012345abcdef")).toBeVisible();

  await page.getByLabel("Manual generation workflow").selectOption("wan_first_last");
  await expect(page.getByRole("alert").filter({ hasText: "first frame, last frame" })).toBeVisible();
  await expect(page.getByTestId("manual-run")).toBeDisabled();
});

test("Manual Director warns instead of silently accepting unsupported audio refs", async ({ page }) => {
  await page.route("**/api/video-repertoire/manual/workflows", (route) => route.fulfill({ json: workflows }));
  await page.route("**/api/video-repertoire/manual/assets", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/video-repertoire/manual/jobs", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/video-repertoire/assets", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/video-repertoire/audio-assets?category=all", (route) => route.fulfill({ json: [] }));
  await page.goto("/manual-director");
  await page.getByLabel("Choose Audio reference").setInputFiles({ name: "voice.wav", mimeType: "audio/wav", buffer: Buffer.from("fake-wave") });
  await page.getByTestId("manual-prompt").fill("A quiet scene");
  await expect(page.getByRole("alert").filter({ hasText: "Some staged references are incompatible" })).toBeVisible();
  await expect(page.getByTestId("manual-run")).toBeDisabled();
});
