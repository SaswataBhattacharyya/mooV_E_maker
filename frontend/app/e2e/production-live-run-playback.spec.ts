import { expect, test } from "@playwright/test";

const projectId = process.env.PRODUCTION_LIVE_PROJECT_ID;
const runId = process.env.PRODUCTION_LIVE_RUN_ID;
const takeId = process.env.PRODUCTION_LIVE_TAKE_ID;

test.skip(!projectId || !runId || !takeId,
  "Set PRODUCTION_LIVE_PROJECT_ID, PRODUCTION_LIVE_RUN_ID, and PRODUCTION_LIVE_TAKE_ID for a real saved-run playback check.");

test("a saved live take opens and plays in the Production Workspace", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const browserErrors: string[] = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
  page.on("response", (response) => {
    if (response.status() >= 400) browserErrors.push(`${response.status()} ${response.url()}`);
  });

  await page.addInitScript(({ selectedProjectId, selectedRunId }) => {
    localStorage.setItem("story-builder.production.project", selectedProjectId);
    localStorage.setItem("story-builder.production.run", selectedRunId);
    localStorage.setItem(`story-builder.production.workspace-stage.${selectedRunId}`, "shots");
    localStorage.setItem(`story-builder.production.stage.${selectedRunId}`, "shot_plans");
  }, { selectedProjectId: projectId!, selectedRunId: runId! });

  await page.goto("/production");
  await expect(page.getByLabel("Open saved production run")).toHaveValue(runId!);
  const runResponse = await page.request.get(`/api/projects/${projectId}/production/v2/runs/${runId}`);
  expect(runResponse.ok()).toBeTruthy();
  const run = await runResponse.json();
  const savedTake = run.takes?.find((take: { take_id: string }) => take.take_id === takeId);
  expect(savedTake).toBeDefined();
  expect(["needs_review", "accepted"]).toContain(savedTake.status);
  const layout = await page.evaluate(() => ({
    viewportWidth: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
  }));
  expect(layout.documentWidth).toBeLessThanOrEqual(layout.viewportWidth);
  const takeRow = page.getByRole("button", { name: new RegExp(takeId!) });
  await expect(takeRow).toBeVisible({ timeout: 20_000 });
  await takeRow.click();

  await expect(page.getByLabel("Selected take review")).toBeVisible();
  const acceptButton = page.getByRole("button", { name: "Accept take" });
  if (savedTake.status === "needs_review") {
    await expect(acceptButton).toHaveCount(1);
    expect(await acceptButton.evaluate((element) => (element as HTMLButtonElement).tabIndex)).toBeGreaterThanOrEqual(0);
  } else {
    await expect(acceptButton).toHaveCount(0);
    await expect(page.getByLabel("Selected take review")).toContainText(/accepted/i);
  }
  const video = page.locator("video");
  await expect(video).toHaveCount(1);
  const h264Support = await video.evaluate((element: HTMLVideoElement) =>
    element.canPlayType('video/mp4; codecs="avc1.64001f, mp4a.40.2"'));
  test.skip(!h264Support, "This Playwright browser has no H.264/AAC decoder; set PLAYWRIGHT_CHROMIUM_EXECUTABLE to a system Chrome/Chromium build with codec support.");
  await expect.poll(() => video.evaluate((element: HTMLVideoElement) => element.readyState),
    { timeout: 20_000 }).toBeGreaterThanOrEqual(1);
  const playbackStartedAt = await video.evaluate(async (element: HTMLVideoElement) => {
    await element.play();
    return element.currentTime;
  });
  await expect.poll(() => video.evaluate((element: HTMLVideoElement) => element.currentTime),
    { timeout: 10_000 }).toBeGreaterThan(playbackStartedAt + 0.2);
  expect(browserErrors).toEqual([]);
});
