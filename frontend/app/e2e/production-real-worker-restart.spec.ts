import { expect, test } from "@playwright/test";
import { access, writeFile } from "node:fs/promises";

const projectId = process.env.REAL_WORKER_PROJECT_ID;
const runId = process.env.REAL_WORKER_RUN_ID;
const takeId = process.env.REAL_WORKER_TAKE_ID;
const promptId = process.env.REAL_WORKER_PROMPT_ID;
test.skip(!projectId || !runId || !takeId || !promptId, "Requires the saved configured-provider render; never creates a fixture or submits inference.");

test("real provider take preserves exact remote identity across API restart and browser reload", async ({ page, request }) => {
  test.setTimeout(90_000);
  const url = `/api/projects/${projectId}/production/v2/runs/${runId}`;
  const assertIdentity = async () => {
    const response = await request.get(url);
    expect(response.ok()).toBeTruthy();
    const run = await response.json();
    const expectedIds = (process.env.REAL_WORKER_EXPECTED_TAKE_IDS || takeId!).split(",");
    expect(run.takes.map((take: { take_id: string }) => take.take_id).sort()).toEqual(expectedIds.sort());
    const selected = run.takes.find((take: { take_id: string }) => take.take_id === takeId);
    expect(selected).toMatchObject({ take_id: takeId, prompt_id: promptId });
    expect(["running", "collecting", "recovery_required", "needs_review", "accepted"]).toContain(selected.status);
  };
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.addInitScript(({ project, run }) => {
    localStorage.setItem("story-builder.production.project", project!);
    localStorage.setItem("story-builder.production.run", run!);
    localStorage.setItem(`story-builder.production.workspace-stage.${run}`, "shots");
    localStorage.setItem(`story-builder.production.stage.${run}`, "shot_plans");
  }, { project: projectId, run: runId });
  await assertIdentity();
  await page.goto("/production");
  await expect(page.getByRole("heading", { name: "Production job queue" })).toBeVisible();
  const row = page.getByRole("button", { name: new RegExp(`${takeId} · no predecessor`) });
  await expect(row).toBeVisible();
  await row.click();
  await expect(page.getByLabel("Selected take review")).toContainText(takeId!);
  const ready = process.env.REAL_WORKER_RESTART_READY_FILE;
  const continued = process.env.REAL_WORKER_RESTART_CONTINUE_FILE;
  if (ready && continued) {
    await writeFile(ready, "real take visible before restart\n");
    await expect.poll(async () => {
      try { await access(continued); return true; } catch { return false; }
    }, { timeout: 45_000 }).toBe(true);
  }
  await page.reload();
  await expect(page.getByLabel("Open saved production run")).toHaveValue(runId!);
  await expect(row).toBeVisible();
  await assertIdentity();
  if (process.env.REAL_WORKER_REQUIRE_PLAYBACK === "1") {
    await row.click();
    const video = page.getByLabel("Selected take review").locator("video").first();
    await expect(video).toBeVisible();
    await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.readyState)).toBeGreaterThanOrEqual(2);
    const played = await video.evaluate(async (v: HTMLVideoElement) => {
      v.muted = true;
      await v.play();
      return { width: v.videoWidth, height: v.videoHeight, duration: v.duration,
        paused: v.paused, error: v.error?.message ?? null };
    });
    expect(played).toMatchObject({ width: 1344, height: 768, paused: false, error: null });
    expect(played.duration).toBeGreaterThanOrEqual(8);
    await video.evaluate((v: HTMLVideoElement) => v.pause());
  }
  expect(errors).toEqual([]);
});
