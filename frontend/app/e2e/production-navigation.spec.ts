import { expect, test } from "@playwright/test";

const projectId = "legacy-project-navigation-test";
const rolloutMode = process.env.PRODUCTION_NAV_TEST_MODE || "enabled";
const rolloutEnabled = rolloutMode === "enabled";

function mockShellAndProductionApis(page: import("@playwright/test").Page) {
  return page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const method = route.request().method();
    if (path === "/api/projects" && method === "GET") return route.fulfill({ json: [projectFixture] });
    if (path === `/api/projects/${projectId}`) return route.fulfill({ json: projectFixture });
    if (path === `/api/projects/${projectId}/production/run`) return route.fulfill({ json: { status: "idle" } });
    if (path === `/api/projects/${projectId}/production/start` && method === "POST") {
      const body = route.request().postDataJSON();
      legacyStartCalls.push({ projectId, body });
      return route.fulfill({ json: { project_id: projectId, status: "completed", stage: "completed", progress: 100 } });
    }
    if (path === "/api/automation/projects") return route.fulfill({ json: [] });
    if (path === "/api/reasoning/provider") return route.fulfill({ json: { provider: "codex", providers: [{ id: "codex", label: "Codex", model: "gpt-6-luna", available: false, compatibility: false }] } });
    if (path === "/api/automation/styles") return route.fulfill({ json: [] });
    if (path === "/api/automation/blocks") return route.fulfill({ json: [] });
    if (path === "/api/production/v2/styles") return route.fulfill({ json: { production_types: [] } });
    if (path.endsWith("/production/v2/runs") && method === "GET") return route.fulfill({ json: { runs: [] } });
    return route.fulfill({ json: {} });
  });
}

const projectFixture = {
  id: projectId,
  title: "Navigation project",
  story_input: "A concise story draft for navigation coverage.",
  automation_mode: false,
  status: "draft",
  current_stage: "story",
  created_at: "2026-10-06T00:00:00Z",
  updated_at: "2026-10-06T00:00:00Z",
  runtime: { job_id: null, state: "idle", current_task: "", progress: 0, completed_tasks: [], last_error: null, automation_active: false },
  artifacts: Object.fromEntries(["story", "characters", "scenes", "subscenes", "dialogue", "image_jobs"].map((type) => [type, { type, status: "pending", path: "", content: null }])),
  image_queue: { current_index: 0, batches: [], accepted: [] },
  logs: [],
};

let legacyStartCalls: Array<{ projectId: string; body: unknown }> = [];
test.beforeEach(() => { legacyStartCalls = []; });

test("Automation Studio routes to Production V2 with its selected project when rollout is enabled", async ({ page }) => {
  test.skip(!rolloutEnabled, "Run against the opt-in Vite instance.");
  await page.addInitScript(() => {
    localStorage.setItem("story-builder.currentProjectId", "legacy-project-navigation-test");
    localStorage.setItem("story-builder.production.project", "old-project");
    localStorage.setItem("story-builder.production.run", "old-run");
  });
  await mockShellAndProductionApis(page);

  await page.goto("/automation");
  await page.getByRole("button", { name: "Open production workspace" }).click();

  await expect(page).toHaveURL(/\/production$/);
  await expect(page.getByRole("heading", { name: "Production workspace" })).toBeVisible();
  await expect(page.getByLabel("Existing project")).toHaveValue(projectId);
  await expect(page.getByLabel("Story / premise (required)")).toHaveValue("A concise story draft for navigation coverage.");
  await expect.poll(() => page.evaluate(() => localStorage.getItem("story-builder.production.project"))).toBe(projectId);
  await expect.poll(() => page.evaluate(() => localStorage.getItem("story-builder.production.run"))).toBeNull();
  expect(legacyStartCalls).toHaveLength(0);
});

test("Story Builder keeps the legacy production start when rollout is off", async ({ page }) => {
  test.skip(rolloutEnabled, "Run against the default-off Vite instance.");
  await page.addInitScript(() => localStorage.setItem("story-builder.currentProjectId", "legacy-project-navigation-test"));
  await mockShellAndProductionApis(page);

  await page.goto("/story");
  await page.getByRole("button", { name: "Start full production" }).click();

  await expect.poll(() => legacyStartCalls).toHaveLength(1);
  expect(legacyStartCalls[0]).toEqual({ projectId, body: { execute_media: true } });
  await expect(page).toHaveURL(/\/story$/);
});

test("Story Builder routes to Production V2 without calling legacy production start when rollout is enabled", async ({ page }) => {
  test.skip(!rolloutEnabled, "Run against the opt-in Vite instance.");
  await page.addInitScript(() => {
    localStorage.setItem("story-builder.currentProjectId", "legacy-project-navigation-test");
    localStorage.setItem("story-builder.production.project", "old-project");
    localStorage.setItem("story-builder.production.run", "old-run");
  });
  await mockShellAndProductionApis(page);

  await page.goto("/story");
  await page.getByRole("button", { name: "Open production workspace" }).click();

  await expect(page).toHaveURL(/\/production$/);
  await expect(page.getByRole("heading", { name: "Production workspace" })).toBeVisible();
  await expect(page.getByLabel("Existing project")).toHaveValue(projectId);
  await expect(page.getByLabel("Story / premise (required)")).toHaveValue("A concise story draft for navigation coverage.");
  await expect.poll(() => page.evaluate(() => localStorage.getItem("story-builder.production.project"))).toBe(projectId);
  await expect.poll(() => page.evaluate(() => localStorage.getItem("story-builder.production.run"))).toBeNull();
  expect(legacyStartCalls).toHaveLength(0);
});
