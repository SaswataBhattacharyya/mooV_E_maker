import { expect, test } from "@playwright/test";

test("restored Full run discovers a controller-created take and keeps it after reload", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.stack || error.message));
  page.on("console", (message) => { if (message.type() === "error") pageErrors.push(message.text()); });
  const projectId = "project-auto-take";
  const runId = "22222222-2222-4222-8222-222222222222";
  const take = { take_id: "take-controller-001", job_id: "job-controller-001", shot_id: "shot-01",
    attempt: 1, status: "queued", parent_take_id: null, input_snapshot: { prompt_preparation_task_id: "task-prompt-001" },
    director_review: { resolution_status: "review_recovery_pending", decision: { action: "retake", reason: "Keep the train centered." },
      retake_preparation: { task_id: "retake-prompt-task", status: "running" } } };
  const acceptedTake = { ...take, status: "accepted", director_review: { resolution_status: "accepted" } };
  const nextTake = { take_id: "take-controller-002", job_id: "job-controller-002", shot_id: "shot-02",
    attempt: 1, status: "queued", parent_take_id: take.take_id, input_snapshot: { prompt_preparation_task_id: "task-prompt-002" } };
  const retakeTake = { take_id: "take-controller-retake-001", job_id: "job-controller-retake-001", shot_id: "shot-01",
    attempt: 2, status: "queued", parent_take_id: null, input_snapshot: { prompt_preparation_task_id: "retake-prompt-task" },
    director_review: { resolution_status: "retake_queued", decision: { action: "retake", reason: "Keep the train centered." },
      retake_preparation: { task_id: "retake-prompt-task", status: "completed" } } };
  const run = { run_id: runId, project_id: projectId, status: "draft", config: {
    control_mode: "fully_automated", making_route: "direct_h3", production_type: "story_film",
    semi_gates: {}, narrative_style_variant_id: "variant-quiet-suspense" }, takes: [], stage_tasks: [] };
  let runReads = 0;
  let progressionPublished = false;
  let retakePublished = false;

  await page.addInitScript(({ projectId: savedProjectId, runId: savedRunId }) => {
    localStorage.setItem("story-builder.production.project", savedProjectId);
    localStorage.setItem("story-builder.production.run", savedRunId);
    localStorage.setItem(`story-builder.production.workspace-stage.${savedRunId}`, "shots");
    localStorage.setItem(`story-builder.production.stage.${savedRunId}`, "shot_plans");
  }, { projectId, runId });

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (path === "/api/projects" && request.method() === "GET")
      return route.fulfill({ json: [{ id: projectId, title: "Automatic take", story_input: "A test story." }] });
    if (path === "/api/automation/projects") return route.fulfill({ json: [] });
    if (path === "/api/reasoning/provider") return route.fulfill({ json: { provider: "codex", providers: [
      { id: "codex", label: "Codex", model: "gpt-6-luna", available: false, compatibility: false },
      { id: "ollama", label: "Ollama", model: "local", available: false, compatibility: false },
    ] } });
    if (path === "/api/production/v2/styles")
      return route.fulfill({ json: { production_types: [{ production_type: "story_film", variants: [{ variant_id: "variant-quiet-suspense", display_name: "Quiet suspense", version: 1 }] }] } });
    if (path === "/api/production/v2/image-workflows") return route.fulfill({ json: { workflows: [] } });
    if (path === "/api/audio/rvc/models") return route.fulfill({ json: [] });
    if (path === `/api/projects/${projectId}/production/v2/runs`)
      return route.fulfill({ json: { runs: [run] } });
    if (path === `/api/projects/${projectId}/production/v2/runs/${runId}`) {
      runReads += 1;
      const takes = retakePublished ? [acceptedTake, nextTake, retakeTake]
        : progressionPublished ? [acceptedTake, nextTake] : runReads === 1 ? [] : [take];
      return route.fulfill({ json: { ...run, takes, stage_tasks: [] } });
    }
    if (path === `/api/projects/${projectId}/production/v2/runs/${runId}/story/revisions`)
      return route.fulfill({ json: { revisions: [{ revision_id: "story-accepted-001", expanded_story: "A test story.", review_status: "accepted", source_hash: "source-test" }] } });
    if (path === `/api/projects/${projectId}/production/v2/runs/${runId}/text/shot_plans/revisions`)
      return route.fulfill({ json: { revisions: [{ revision_id: "shot-plans-001", review_status: "accepted", items: [{ unit_id: "shot-01", content: { prompt: "A test shot." } }] }] } });
    if (path === `/api/projects/${projectId}/production/v2/canon`)
      return route.fulfill({ json: { revision: 0, characters: [], worlds: [] } });
    if (path === `/api/projects/${projectId}/production/v2/assets`)
      return route.fulfill({ json: { assets: [], total: 0 } });
    if (path === `/api/projects/${projectId}/production/v2/runs/${runId}/voice-bindings`)
      return route.fulfill({ json: { bindings: [] } });
    return route.fulfill({ json: {} });
  });

  await page.goto("/production");
  await expect(page.getByRole("heading", { name: "Production job queue" }), pageErrors.join("\n")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("shot-01 · take 1")).toBeVisible();
  await expect(page.getByText("queued", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /shot-01 · take 1/ }).click();
  await expect(page.getByLabel("Selected take review")).toBeVisible();
  await expect(page.getByText("Fresh retake prompt preparation: running.")).toBeVisible();
  expect(pageErrors).toEqual([]);

  await page.reload();
  await expect(page.getByRole("heading", { name: "Production job queue" })).toBeVisible();
  await expect(page.getByText("take-controller-001")).toBeVisible();
  expect(pageErrors).toEqual([]);
  expect(runReads).toBeGreaterThanOrEqual(3);

  // Model the durable API after the worker accepted cut one and scheduled cut two.
  // The reopened workspace must show the controller's new child and its exact parent.
  progressionPublished = true;
  await page.reload();
  await expect(page.getByRole("button", { name: /shot-02 · take 1/ })).toContainText(`after ${take.take_id}`);
  await expect(page.getByRole("button", { name: /shot-01 · take 1/ })).toContainText("accepted");
  await page.getByRole("button", { name: /shot-02 · take 1/ }).click();
  await expect(page.getByLabel("Selected take review")).toContainText(nextTake.take_id);

  // Replay of a saved Director retake decision publishes one deterministic child.
  retakePublished = true;
  await page.reload();
  const retakeRow = page.getByRole("button", { name: /shot-01 · take 2/ });
  await expect(retakeRow).toHaveCount(1);
  await retakeRow.click();
  await expect(page.getByLabel("Director video review")).toContainText("retake queued");
  await expect(page.getByLabel("Director video review")).toContainText("Fresh retake prompt preparation: completed.");
  expect(pageErrors).toEqual([]);
});
