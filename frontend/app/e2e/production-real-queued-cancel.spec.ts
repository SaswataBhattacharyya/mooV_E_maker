import { expect, test } from "@playwright/test";

const project = process.env.REAL_CANCEL_PROJECT_ID;
const runId = process.env.REAL_CANCEL_RUN_ID;
const takeId = process.env.REAL_CANCEL_TAKE_ID;
test.skip(!project || !runId || !takeId, "Requires an existing disposable queued take; no fixtures or inference.");

test("real queued cancellation survives reload and preserves accepted native-video playback", async ({ page, request }) => {
  test.setTimeout(90_000);
  const url = `/api/projects/${project}/production/v2/runs/${runId}`;
  const read = async () => {
    const response = await request.get(url);
    expect(response.ok()).toBeTruthy();
    return response.json();
  };
  const before = await read();
  const candidate = before.takes.find((t: { take_id: string }) => t.take_id === takeId);
  expect(candidate.status).toBe(process.env.REAL_CANCEL_ALREADY_CANCELLED === "1" ? "cancelled" : "queued");
  expect(candidate.prompt_id).toBeFalsy();
  const untouched = before.takes.filter((t: { take_id: string }) => t.take_id !== takeId)
    .map((t: { take_id: string; status: string; prompt_id: string | null }) => ({ take_id: t.take_id, status: t.status, prompt_id: t.prompt_id }));
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.addInitScript(({ project, runId }) => {
    localStorage.setItem("story-builder.production.project", project!);
    localStorage.setItem("story-builder.production.run", runId!);
    localStorage.setItem(`story-builder.production.workspace-stage.${runId}`, "shots");
    localStorage.setItem(`story-builder.production.stage.${runId}`, "shot_plans");
  }, { project, runId });
  await page.goto("/production");
  await page.getByRole("button", { name: new RegExp(`${takeId} · no predecessor`) }).click();
  const review = page.getByLabel("Selected take review");
  await expect(review).toContainText(takeId!);
  if (candidate.status === "queued") await review.getByRole("button", { name: "Stop take", exact: true }).click();
  await expect.poll(async () => (await read()).takes.find((t: { take_id: string }) => t.take_id === takeId)?.status).toBe("cancelled");
  await page.reload();
  await page.getByRole("button", { name: new RegExp(`${takeId} · no predecessor`) }).click();
  await expect(review).toContainText("cancelled");
  await expect(review.getByRole("button", { name: "Stop take", exact: true })).toHaveCount(0);
  const after = await read();
  expect(after.takes).toHaveLength(before.takes.length);
  expect(after.takes.filter((t: { take_id: string }) => t.take_id !== takeId)
    .map((t: { take_id: string; status: string; prompt_id: string | null }) => ({ take_id: t.take_id, status: t.status, prompt_id: t.prompt_id }))).toEqual(untouched);
  expect(after.takes.find((t: { take_id: string }) => t.take_id === takeId).prompt_id).toBeFalsy();
  const acceptedTakeIds = process.env.REAL_CANCEL_ACCEPTED_TAKE_IDS?.split(",") ?? ["c76c5a53-445c-5108-831e-ca5a99b442f9", "06ad5392-cff7-537d-92d4-19bcc13cfbf2"];
  for (const accepted of acceptedTakeIds) {
    const saved = after.takes.find((t: { take_id: string }) => t.take_id === accepted);
    expect(saved.status).toBe("accepted");
    await page.getByRole("button", { name: new RegExp(accepted) }).click();
    const video = review.locator("video").first();
    await expect(video).toBeVisible();
    await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.readyState)).toBeGreaterThanOrEqual(2);
    const metadata = await video.evaluate(async (v: HTMLVideoElement) => {
      v.muted = true;
      await v.play();
      return { width: v.videoWidth, height: v.videoHeight, duration: v.duration, paused: v.paused, error: v.error?.message ?? null };
    });
    expect(metadata.width).toBeGreaterThan(0);
    expect(metadata.height).toBeGreaterThan(0);
    expect(metadata.duration).toBeGreaterThan(4);
    expect(metadata.paused).toBe(false);
    expect(metadata.error).toBeNull();
    await video.evaluate((v: HTMLVideoElement) => v.pause());
  }
  expect(errors).toEqual([]);
});
