import { expect, test } from "@playwright/test";

const projectId = process.env.IMAGE_MASTER_ACCEPTANCE_PROJECT_ID || "";
const runId = process.env.IMAGE_MASTER_ACCEPTANCE_RUN_ID || "";
const expectedAssets = (() => {
  try { return JSON.parse(process.env.IMAGE_MASTER_ACCEPTANCE_EXPECTED_ASSETS || "[]"); }
  catch { return []; }
})();
const required = [projectId, runId, ...expectedAssets.map((row: any) => row.asset_id || "")];
test.skip(required.some(value => !value) || expectedAssets.length === 0,
  "opt-in automatic-image acceptance runner did not provide isolated backend identities/assets");

async function expectGeneratedImagesLoaded(page: import("@playwright/test").Page): Promise<void> {
  for (const row of expectedAssets) {
    const contentUrl = `/api/projects/${encodeURIComponent(projectId)}/production/v2/assets/${encodeURIComponent(row.asset_id)}/content`;
    const image = page.locator(`img[src="${contentUrl}"]`);
    await expect(image).toBeVisible();
    await expect.poll(() => image.evaluate((element: HTMLImageElement) =>
      element.complete && element.naturalWidth > 0 && element.naturalHeight > 0,
    )).toBe(true);
  }
}

test("accepted automatic identity masters and controller continuation survive browser reload", async ({ page }) => {
  test.setTimeout(60_000);
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("response", response => {
    if (response.status() >= 500) errors.push(`${response.status()} ${response.url()}`);
  });
  await page.addInitScript(({ selectedProjectId, selectedRunId }) => {
    localStorage.setItem("story-builder.production.project", selectedProjectId);
    localStorage.setItem("story-builder.production.run", selectedRunId);
    localStorage.setItem(`story-builder.production.workspace-stage.${selectedRunId}`, "assets");
    localStorage.setItem(`story-builder.production.stage.${selectedRunId}`, "shot_plans");
  }, { selectedProjectId: projectId, selectedRunId: runId });

  await page.goto("/production");
  await expect(page.getByRole("heading", { name: "Production workspace" })).toBeVisible();
  await page.getByRole("button", { name: /Assets & world/ }).click();
  await expect(page.getByRole("heading", { name: "Character & world bible" })).toBeVisible();
  for (const row of expectedAssets) {
    await expect(page.getByText(`Assigned to ${row.display_name}`)).toBeVisible();
  }
  await expectGeneratedImagesLoaded(page);

  const apiState = await page.evaluate(async ({ p, r, expected }) => {
    const [runResponse, assetsResponse] = await Promise.all([
      fetch(`/api/projects/${p}/production/v2/runs/${r}`),
      fetch(`/api/projects/${p}/production/v2/assets?kind=image&limit=100`),
    ]);
    if (![runResponse, assetsResponse].every(response => response.ok)) {
      throw new Error(`Persisted API readback failed: run=${runResponse.status}, assets=${assetsResponse.status}`);
    }
    const [run, assetPage] = await Promise.all([runResponse.json(), assetsResponse.json()]);
    const batchStates = await Promise.all(expected.map(async (row: any) => {
      const response = await fetch(`/api/projects/${p}/production/v2/image-jobs/${row.batch_id}`);
      if (!response.ok) throw new Error(`Persisted batch readback failed for ${row.batch_id}: ${response.status}`);
      return { expected: row, batch: await response.json() };
    }));
    const assets = expected.map((row: any) => assetPage.assets.find((asset: any) => asset.asset_id === row.asset_id));
    const controllerTasks = run.stage_tasks.filter((task: any) => task.stage === "controller:resolved_shot_prompt");
    return { assets, batchStates, controllerTasks };
  }, { p: projectId, r: runId, expected: expectedAssets });
  expect(apiState.assets).toHaveLength(expectedAssets.length);
  for (let index = 0; index < expectedAssets.length; index += 1) {
    const expected = expectedAssets[index];
    const asset = apiState.assets[index];
    expect(asset).toBeTruthy();
    expect(asset.roles).toContain(expected.role);
    expect(asset.metadata.approval_status).toBe("accepted");
    expect(asset.metadata[expected.role === "character_master" ? "character_id" : "world_id"]).toBe(expected.entity_id);
    const batchState = apiState.batchStates[index];
    expect(batchState.batch.jobs).toHaveLength(1);
    const job = batchState.batch.jobs.find((candidate: any) => candidate.job_id === expected.job_id);
    expect(job.status).toBe("completed");
    expect(job.director_review.resolution_status).toBe("accepted");
    expect(job.director_review.asset_id).toBe(job.output_asset_id);
    expect(job.director_review.decision.action).toBe("accept");
  }
  expect(apiState.controllerTasks).toHaveLength(1);
  expect(apiState.controllerTasks[0].status).toBe("queued");

  await page.reload();
  await expect(page.getByRole("heading", { name: "Production workspace" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Character & world bible" })).toBeVisible();
  for (const row of expectedAssets) {
    await expect(page.getByText(`Assigned to ${row.display_name}`)).toBeVisible();
  }
  await expectGeneratedImagesLoaded(page);
  expect(errors).toEqual([]);
});
