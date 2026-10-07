import { expect, test } from "@playwright/test";

test("Full image generation binds an active canon identity and waits for the Director decision", async ({ page }) => {
  const projectId = "project-full-image";
  const runId = "11111111-1111-4111-8111-111111111111";
  const characterId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  const batchId = "image-director-batch";
  let project: any = null;
  let requestBody: any = null;
  let batchPolls = 0;
  let assets: any[] = [];
  const consoleErrors: string[] = [];
  const missingApiCalls: string[] = [];
  const character = { character_id: characterId, display_name: "Traveler", status: "active", description: "A traveler", appearance: "Red coat" };
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("pageerror", (error) => consoleErrors.push(error.message));

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    if (url.pathname === "/api/projects" && method === "GET") return route.fulfill({ json: project ? [project] : [] });
    if (url.pathname === "/api/projects" && method === "POST") {
      project = { id: projectId, title: "Traveler", story_input: "A traveler reaches a station.", automation_mode: false };
      return route.fulfill({ status: 201, json: project });
    }
    if (url.pathname === `/api/projects/${projectId}/draft` && method === "PUT") return route.fulfill({ json: project });
    if (url.pathname === "/api/production/v2/styles") return route.fulfill({ json: { production_types: [{ production_type: "story_film", variants: [] }] } });
    if (url.pathname === "/api/automation/projects") return route.fulfill({ json: [] });
    if (url.pathname === "/api/audio/rvc/models") return route.fulfill({ json: [] });
    if (url.pathname === "/api/production/v2/image-workflows") return route.fulfill({ json: { workflows: ["z_image_turbo", "qwen_image_2512", "qwen_image_edit_2511"].map((workflow_id) => ({ workflow_id, label: workflow_id, available: true })) } });
    if (url.pathname === "/api/reasoning/provider") return route.fulfill({ json: { provider: "codex", providers: [{ id: "codex", available: true }] } });
    if (url.pathname.endsWith("/production/v2/runs") && method === "POST") return route.fulfill({ status: 201, json: { run_id: runId, project_id: projectId, status: "draft", config: { control_mode: "fully_automated", making_route: "reference_built", production_type: "story_film", semi_gates: {} } } });
    if (url.pathname === `/api/projects/${projectId}/production/v2/runs/${runId}`) return route.fulfill({ json: { run_id: runId, project_id: projectId, status: "draft", config: { control_mode: "fully_automated", making_route: "reference_built", production_type: "story_film", semi_gates: {} } } });
    if (url.pathname.endsWith(`/production/v2/runs/${runId}/story/revisions`)) return route.fulfill({ json: { revisions: [] } });
    if (url.pathname.endsWith(`/production/v2/runs/${runId}/story/tasks`) && method === "POST") return route.fulfill({ status: 202, json: { task_id: "auto-story-task", status: "completed", accepted: true, revision: { revision_id: "story-canon-0123456789ab", expanded_story: "A traveler reaches a station.", source_hash: "source", review_status: "accepted", created_at: "2026-10-04T00:00:00Z" } } });
    if (url.pathname === `/api/projects/${projectId}/production/v2/canon`) return route.fulfill({ json: { project_id: projectId, revision: 1, characters: [character], worlds: [] } });
    if (url.pathname === `/api/projects/${projectId}/production/v2/assets`) return route.fulfill({ json: { assets, total: assets.length } });
    if (url.pathname.endsWith("/image-jobs") && method === "POST") {
      requestBody = request.postDataJSON();
      return route.fulfill({ status: 202, json: {
        batch_id: batchId, reused: false,
        jobs: [{ job_id: "image-job-1", batch_id: batchId, candidate_index: 1, workflow_id: "z_image_turbo", asset_role: "character_master", status: "queued" }],
        generation_policy: { initial_candidates: 1, selection_authority: "director", retake_supported: true, full_retake_budget: 2 },
      } });
    }
    if (url.pathname === `/api/projects/${projectId}/production/v2/image-jobs/${batchId}` && method === "GET") {
      batchPolls += 1;
      const assetId = "pa-director-image-0001";
      const reviewStatus = batchPolls === 1 ? "reviewing" : "accepted";
      assets = [{ asset_id: assetId, kind: "image", roles: batchPolls === 1 ? ["image_candidate"] : ["image_candidate", "character_master"], filename: "traveler-master.png", source: "project_output", media: { width: 1280, height: 720 }, metadata: { approval_status: batchPolls === 1 ? "pending" : "accepted", character_id: characterId, production_image_job: { intended_role: "character_master", accepted: batchPolls > 1 } } }];
      return route.fulfill({ json: {
        batch_id: batchId,
        generation_policy: { initial_candidates: 1, selection_authority: "director", retake_supported: true, full_retake_budget: 2 },
        jobs: [{ job_id: "image-job-1", batch_id: batchId, candidate_index: 1, workflow_id: "z_image_turbo", asset_role: "character_master", status: "completed", output_asset_id: assetId,
          director_review: reviewStatus === "reviewing" ? { resolution_status: reviewStatus, attempt_count: 1 } : { resolution_status: reviewStatus, decision: { action: "accept", reason: "Identity and requested appearance are clear." } } }],
      } });
    }
    if (url.pathname.endsWith("/pa-director-image-0001/content")) return route.fulfill({ status: 200, contentType: "image/png", body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/mWQAAAAASUVORK5CYII=", "base64") });
    missingApiCalls.push(`${method} ${url.pathname}`);
    return route.fulfill({ status: 404, json: { detail: `Not mocked: ${method} ${url.pathname}` } });
  });

  await page.goto("/production");
  await page.getByLabel("Project title").fill("Traveler");
  await page.getByLabel("Story / premise (required)").fill("A traveler reaches a station.");
  await page.getByRole("button", { name: "Save story draft" }).click();
  await page.getByLabel("How much should I review?").selectOption("fully_automated");
  await page.getByLabel("How should visuals be made?").selectOption("reference_built");
  await page.getByRole("button", { name: "Create production run" }).click();
  const assetsStage = page.getByRole("button", { name: /Stage 2 Assets & world/ });
  await expect(assetsStage).toBeEnabled();
  await assetsStage.click();
  await page.getByLabel("Canon identity for automatic review").selectOption(characterId);
  await page.getByLabel("Image prompt").fill("Traveler in a red coat, clear face");
  await page.getByRole("button", { name: "Generate image candidates" }).click();
  expect(requestBody).toMatchObject({ asset_role: "character_master", entity_id: characterId, prompt: "Traveler in a red coat, clear face" });
  await expect(page.getByText("Director review in progress (attempt 1).")).toBeVisible({ timeout: 10000 });
  await expect(page.getByLabel("Image candidate job status").getByText("accepted", { exact: true })).toBeVisible({ timeout: 10000 });
  await expect(page.getByRole("img", { name: "traveler-master.png" })).toBeVisible();
  expect(batchPolls).toBeGreaterThanOrEqual(2);
  expect(missingApiCalls).toEqual([]);
  expect(consoleErrors).toEqual([]);
});
