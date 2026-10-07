import { expect, test } from "@playwright/test";

test("Production V2 keeps control modes independent from making routes", async ({ page }) => {
  let project: any = null;
  let projectNumber = 0;
  const createdRuns: any[] = [];
  let failedStageReadCount = 0;
  let showDelegatedStoryFixture = false;
  let simulateExpiredStoryTask = false;
  let recoveryResolutionCount = 0;
  let expiredTextTask = false;
  let textResolutionCount = 0;
  const textRetryKeys: string[] = [];
  const automaticStoryTaskKeys: string[] = [];
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (project && url.pathname === `/api/projects/${project.id}/production/v2/runs` && request.method() === "GET") {
      return route.fulfill({ json: { runs: createdRuns.map((config, index) => ({
        run_id: `matrix-run-${index + 1}`, project_id: project.id, status: "draft", config, takes: [],
      })) } });
    }
    if (url.pathname === "/api/projects" && request.method() === "GET") return route.fulfill({ json: project ? [project] : [] });
    if (url.pathname === "/api/projects" && request.method() === "POST") {
      projectNumber += 1;
      project = { id: `matrix-project-${projectNumber}`, title: "Matrix story", story_input: "A small story premise." };
      return route.fulfill({ status: 201, json: project });
    }
    if (url.pathname.endsWith("/draft") && request.method() === "PUT") return route.fulfill({ json: project });
    if (url.pathname === "/api/production/v2/styles") return route.fulfill({ json: { production_types: [] } });
    if (project && url.pathname === `/api/projects/${project.id}/production/v2/runs/matrix-run-${createdRuns.length}` && request.method() === "GET") return route.fulfill({ json: { run_id: `matrix-run-${createdRuns.length}`, project_id: project.id, status: "draft", config: createdRuns.at(-1), takes: [] } });
    if (/\/production\/v2\/runs\/matrix-run-\d+\/story\/revisions$/.test(url.pathname) && request.method() === "GET") {
      return route.fulfill({ json: { revisions: showDelegatedStoryFixture ? [{ revision_id: "story-canon-0123456789ab", expanded_story: "A small expanded story.", source_hash: "matrix-source-hash", review_status: "accepted" }] : [] } });
    }
    if (/\/production\/v2\/runs\/matrix-run-\d+\/text\/scenes\/tasks$/.test(url.pathname) && request.method() === "POST") {
      if (expiredTextTask) textRetryKeys.push(request.postDataJSON().idempotency_key);
      return route.fulfill({ status: 202, json: { task_id: "scenes-task-matrix", status: "queued" } });
    }
    if (/\/production\/v2\/runs\/matrix-run-\d+\/text\/scenes\/tasks\/scenes-task-matrix$/.test(url.pathname) && request.method() === "GET") return route.fulfill({ json: expiredTextTask
      ? { task_id: "scenes-task-matrix", status: "recovery_required", error: { code: "stage_task_lease_expired", message: "Inspect for a saved result." } }
      : { task_id: "scenes-task-matrix", status: "completed", accepted: false, revision: { revision_id: "scenes-director-pending", review_status: "pending_director_repair", items: [{ unit_id: "scene-001", content: { title: "Director proposal" } }] } } });
    if (/\/stage-tasks\/scenes-task-matrix\/resolve$/.test(url.pathname) && request.method() === "POST") {
      textResolutionCount += 1;
      return textResolutionCount === 1
        ? route.fulfill({ status: 409, json: { detail: "Original worker is still active." } })
        : route.fulfill({ json: { task_id: "scenes-task-matrix", status: "failed" } });
    }
    if (/\/production\/v2\/runs\/matrix-run-\d+\/story\/tasks$/.test(url.pathname) && request.method() === "POST") {
      automaticStoryTaskKeys.push(request.postDataJSON().idempotency_key);
      return route.fulfill({ status: 202, json: { task_id: "story-task-matrix", status: "queued" } });
    }
    if (/\/production\/v2\/runs\/matrix-run-\d+\/story\/tasks\/story-task-matrix$/.test(url.pathname) && request.method() === "GET") return route.fulfill({ json: simulateExpiredStoryTask
      ? { task_id: "story-task-matrix", status: "recovery_required", error: { code: "stage_task_lease_expired", message: "Inspect for a saved result." } }
      : { task_id: "story-task-matrix", status: "completed", accepted: true, revision: { revision_id: "story-canon-delegated", expanded_story: "A small expanded story.", source_hash: "matrix-source-hash", review_status: "accepted" } } });
    if (/\/production\/v2\/runs\/matrix-run-\d+\/stage-tasks\/story-task-matrix\/resolve$/.test(url.pathname) && request.method() === "POST") { recoveryResolutionCount += 1; return route.fulfill({ json: { task_id: "story-task-matrix", status: "failed" } }); }
    if (/\/production\/v2\/runs$/.test(url.pathname) && request.method() === "POST") {
      const body = request.postDataJSON();
      createdRuns.push(body);
      return route.fulfill({ status: 201, json: { run_id: `matrix-run-${createdRuns.length}`, project_id: project.id, status: "draft", config: body, takes: [] } });
    }
    if (url.pathname.endsWith("/production/v2/canon")) return route.fulfill({ json: { schema_version: 1, project_id: project.id, revision: 0, characters: [], worlds: [] } });
    if (url.pathname.endsWith("/production/v2/assets")) return route.fulfill({ json: { assets: [], total: 0, limit: 50, offset: 0 } });
    if (url.pathname.endsWith("/voice-bindings")) return route.fulfill({ json: { bindings: [] } });
    if (/\/text\/(scenes|dialogue|visual_briefs)\/revisions$/.test(url.pathname) && request.method() === "GET") return route.fulfill({ json: { revisions: [] } });
    if (url.pathname.endsWith("/text/shot_plans/revisions") && request.method() === "GET") {
      if (showDelegatedStoryFixture) return route.fulfill({ json: { revisions: [] } });
      failedStageReadCount += 1; return route.fulfill({ status: 503, json: { detail: "Shot plan service temporarily unavailable." } });
    }
    return route.fulfill({ status: 404, json: { detail: `Unexpected ${request.method()} ${url.pathname}` } });
  });

  const cases = [
    ["manual", "direct_h3"], ["manual", "reference_built"], ["manual", "hybrid"],
    ["semi", "direct_h3"], ["semi", "reference_built"], ["semi", "hybrid"],
    ["fully_automated", "direct_h3"], ["fully_automated", "reference_built"], ["fully_automated", "hybrid"],
  ] as const;
  await page.goto("/production");
  for (const [mode, route] of cases) {
    await page.evaluate(() => { localStorage.removeItem("story-builder.production.project"); localStorage.removeItem("story-builder.production.run"); });
    await page.goto(`/production?case=${mode}-${route}`);
    await page.getByLabel("Project title").fill("Matrix story");
    await page.getByLabel("Story / premise (required)").fill("A small story premise.");
    await page.getByRole("button", { name: "Save story draft" }).click();
    await page.getByLabel("How much should I review?").selectOption(mode);
    await page.getByLabel("How should visuals be made?").selectOption(route);
    const expectedRunNumber = createdRuns.length + 1;
    await page.getByRole("button", { name: "Create production run" }).click();
    await expect(page.getByText(new RegExp(`matrix-run-${expectedRunNumber}`))).toBeVisible();
    expect(createdRuns.at(-1)).toMatchObject({ control_mode: mode, making_route: route });
    expect(createdRuns.at(-1).semi_gates).toEqual(mode === "semi"
      ? { story_review: true, image_candidate_selection: true, voice_selection: true, shot_workflow_render_approval: true }
      : {});
  }
  expect(createdRuns).toHaveLength(9);
  await expect.poll(() => automaticStoryTaskKeys.length).toBe(3);
  expect(new Set(automaticStoryTaskKeys).size).toBe(3);

  await page.evaluate(() => { localStorage.removeItem("story-builder.production.project"); localStorage.removeItem("story-builder.production.run"); });
  showDelegatedStoryFixture = true;
  await page.goto("/production?case=semi-story-review-delegated");
  await page.getByLabel("Project title").fill("Delegated story review");
  await page.getByLabel("Story / premise (required)").fill("A small story premise.");
  await page.getByRole("button", { name: "Save story draft" }).click();
  await page.getByLabel("How much should I review?").selectOption("semi");
  await page.getByLabel("Story and scene review").uncheck();
  await page.getByRole("button", { name: "Create production run" }).click();
  await expect(page.getByText(/matrix-run-10 · semi · direct_h3/)).toBeVisible();
  await page.getByRole("button", { name: "Ask Director to expand story" }).click();
  await expect(page.getByLabel("Expanded story proposal")).toHaveAttribute("readonly", "");
  await page.getByRole("button", { name: /Shot composer/ }).click();
  await page.getByLabel("Stage", { exact: true }).selectOption("scenes");
  await page.getByLabel("Stable-ID units (JSON)").fill(JSON.stringify([{ unit_id: "scene-delegated", source_chunk_ids: [], content: { title: "Delegated scene" } }]));
  await page.getByRole("button", { name: "Ask Director to draft this stage" }).click();
  await expect(page.getByText("pending director repair")).toBeVisible();
  await expect(page.getByRole("button", { name: "Accept this text revision" })).toHaveCount(0);
  expect(createdRuns.at(-1)).toMatchObject({ control_mode: "semi", semi_gates: { story_review: false } });
  expiredTextTask = true;
  const draftStage = page.getByRole("button", { name: "Ask Director to draft this stage" });
  page.once("dialog", (dialog) => dialog.dismiss());
  await draftStage.click();
  await expect(draftStage).toBeEnabled();
  expect(textResolutionCount).toBe(0);
  page.once("dialog", (dialog) => dialog.accept());
  await draftStage.click();
  await expect(page.getByText("Original worker is still active.")).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await draftStage.click();
  await expect(page.getByText("Task reconciled. Submit a new text-stage attempt when ready.")).toBeVisible();
  expect(textResolutionCount).toBe(2);
  expect(textRetryKeys).toHaveLength(3);
  expect(new Set(textRetryKeys).size).toBe(1);
  expiredTextTask = false;
  simulateExpiredStoryTask = true;
  await page.getByRole("button", { name: /Story & direction/ }).click();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Ask Director to expand story" }).click();
  await expect(page.getByText("Task reconciled. Start a new story attempt when ready.")).toBeVisible();
  expect(recoveryResolutionCount).toBe(1);
  showDelegatedStoryFixture = false;

  await page.emulateMedia({ reducedMotion: "reduce" });
  const stages = page.getByRole("navigation", { name: "Production stages" });
  const storyStage = stages.getByRole("button", { name: /Story & direction/ });
  await storyStage.focus();
  await page.keyboard.press("Tab");
  const assetsStage = stages.getByRole("button", { name: /Assets & world/ });
  await expect(assetsStage).toBeFocused();
  expect(await assetsStage.evaluate((element) => element.matches(":focus-visible"))).toBe(true);
  expect(await assetsStage.evaluate((element) => getComputedStyle(element).transitionProperty)).toBe("none");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Character & world bible" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Character & world bible" })).toBeVisible();
  await expect(stages.getByRole("button", { name: /Assets & world/ })).toHaveAttribute("aria-current", "step");
  await page.getByLabel("Production stage navigation").getByRole("button", { name: "Back" }).click();
  await expect(page.getByRole("heading", { name: "Choose or create a project" })).toBeVisible();
  await stages.getByRole("button", { name: /Assets & world/ }).click();
  await expect(page.getByRole("heading", { name: "Character & world bible" })).toBeVisible();
  await stages.getByRole("button", { name: /Shot composer/ }).click();
  await expect(page.getByText("Shot plan service temporarily unavailable.")).toBeVisible();
  expect(failedStageReadCount).toBe(1);
  await expect(stages.getByRole("button", { name: /Assets & world/ })).toHaveAttribute("aria-current", "step");
});
