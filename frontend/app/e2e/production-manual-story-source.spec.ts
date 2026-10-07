import { expect, test } from "@playwright/test";

test("Manual Production V2 can review the saved source story without calling a provider", async ({ page }) => {
  const sourceStory = "Mira warns Arjun about the storm. After a pause, they leave for the station.";
  const sourceHash = "a".repeat(64);
  const runId = "11111111-1111-4111-8111-111111111111";
  let project: any = null;
  let run: any = null;
  let manualSourceCalls = 0;
  let directorTaskCalls = 0;

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    if (url.pathname === "/api/projects" && method === "GET") {
      return route.fulfill({ json: project ? [project] : [] });
    }
    if (url.pathname === "/api/projects" && method === "POST") {
      const body = request.postDataJSON();
      project = { id: "manual-project", title: body.title, story_input: body.story_input, automation_mode: false };
      return route.fulfill({ status: 201, json: project });
    }
    if (url.pathname === "/api/projects/manual-project/draft" && method === "PUT") {
      project = { ...project, ...request.postDataJSON() };
      return route.fulfill({ json: project });
    }
    if (url.pathname === "/api/production/v2/styles") {
      return route.fulfill({ json: { production_types: [{ production_type: "story_film", variants: [] }] } });
    }
    if (url.pathname === "/api/reasoning/provider") {
      return route.fulfill({ json: { provider: "codex", providers: [
        { id: "codex", label: "Codex CLI", model: "test", available: true, compatibility: false },
        { id: "ollama", label: "Ollama", model: "test", available: true, compatibility: true },
      ] } });
    }
    if (url.pathname === "/api/production/v2/image-workflows") return route.fulfill({ json: { workflows: [] } });
    if (url.pathname === "/api/projects/manual-project/production/v2/runs" && method === "POST") {
      const body = request.postDataJSON();
      run = { run_id: runId, project_id: project.id, status: "draft", stage_tasks: [], config: {
        control_mode: body.control_mode, making_route: body.making_route, production_type: body.production_type,
        source_story_hash: sourceHash, semi_gates: body.semi_gates || {},
      } };
      return route.fulfill({ status: 201, json: run });
    }
    if (url.pathname === "/api/projects/manual-project/production/v2/canon" && method === "GET") {
      return route.fulfill({ json: { schema_version: 1, project_id: project.id, revision: 0, characters: [], worlds: [] } });
    }
    if (url.pathname === "/api/projects/manual-project/production/v2/assets" && method === "GET") {
      return route.fulfill({ json: { assets: [], total: 0, limit: 50, offset: 0 } });
    }
    if (url.pathname.endsWith("/story/manual-source") && method === "POST") {
      manualSourceCalls += 1;
      expect(request.postDataJSON()).toEqual({ expected_source_hash: sourceHash });
      return route.fulfill({ json: { revision: {
        revision_id: "story-canon-aabbccddeeff", expanded_story: sourceStory,
        review_status: "pending_review", source_hash: sourceHash, chunks: [],
      }, accepted: false, review_required: true, reused: false } });
    }
    if (url.pathname.endsWith("/story/revisions/story-canon-aabbccddeeff/accept") && method === "POST") {
      return route.fulfill({ json: { accepted: true, review_status: "accepted" } });
    }
    if (url.pathname.endsWith("/story/tasks") && method === "POST") directorTaskCalls += 1;
    return route.fulfill({ json: {} });
  });

  await page.goto("/production");
  await page.getByLabel("Project title").fill("Manual source story acceptance");
  await page.getByLabel("Story / premise (required)").fill(sourceStory);
  await page.getByRole("button", { name: "Save story draft" }).click();
  await expect(page.getByText("Story draft saved.")).toBeVisible();
  await page.getByRole("button", { name: "Create production run" }).click();
  await expect(page.getByText(runId)).toBeVisible();

  await page.getByRole("button", { name: "Use saved story as my canon" }).click();
  await expect(page.getByLabel("Expanded story proposal")).toHaveValue(sourceStory);
  await expect(page.getByText("pending review", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Accept story canon" }).click();
  await expect(page.getByText("accepted", { exact: true })).toBeVisible();
  expect(manualSourceCalls).toBe(1);
  expect(directorTaskCalls).toBe(0);
  expect(run).not.toBeNull();
});
