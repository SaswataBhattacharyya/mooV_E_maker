import { expect, test } from "@playwright/test";

for (const mode of ["fully_automated", "semi"]) {
test(`${mode} saves one reproducible automatic voice choice per active character`, async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const projectId = "voice-project";
  const runId = "22222222-2222-4222-8222-222222222222";
  const characters = [
    { character_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", display_name: "Maya", status: "active" },
    { character_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", display_name: "Arjun", status: "active" },
  ];
  const bindings: any[] = [];
  const calls: any[] = [];
  const dialogueCalls: any[] = [];
  const voiceMaster = { asset_id: "voice-master-1", kind: "audio", roles: ["voice_master"], filename: "voice.wav", source: "project_upload", media: { duration_seconds: 35 }, sha256: "a".repeat(64) };
  const assets: any[] = [voiceMaster,
    { asset_id: "excerpt-maya", kind: "audio", roles: ["voice_excerpt"], filename: "maya.wav", media: { duration_seconds: 5 }, metadata: { approval_status: "accepted", run_id: runId, character_id: characters[0].character_id, source_voice_asset_id: "voice-master-1" } },
    { asset_id: "excerpt-arjun", kind: "audio", roles: ["voice_excerpt"], filename: "arjun.wav", media: { duration_seconds: 5 }, metadata: { approval_status: "accepted", run_id: runId, character_id: characters[1].character_id, source_voice_asset_id: "voice-master-1" } },
  ];
  const project = { id: projectId, title: "Voice test", story_input: "Maya and Arjun leave before the storm." };
  const run = { run_id: runId, project_id: projectId, status: "draft", config: { control_mode: mode, making_route: "direct_h3", semi_gates: { voice_selection: false } }, takes: [] };
  await page.addInitScript(({ projectKey, runKey, projectValue, runValue }) => {
    localStorage.setItem(projectKey, projectValue);
    localStorage.setItem(runKey, runValue);
    localStorage.setItem(`story-builder.production.workspace-stage.${runValue}`, "assets");
  }, { projectKey: "story-builder.production.project", runKey: "story-builder.production.run", projectValue: projectId, runValue: runId });
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/projects" && request.method() === "GET") return route.fulfill({ json: [project] });
    if (url.pathname === `/api/projects/${projectId}/production/v2/runs` && request.method() === "GET") return route.fulfill({ json: { runs: [run] } });
    if (url.pathname === `/api/projects/${projectId}/production/v2/runs/${runId}` && request.method() === "GET") return route.fulfill({ json: run });
    if (url.pathname === `/api/projects/${projectId}/production/v2/runs/${runId}/story/revisions`) return route.fulfill({ json: { revisions: [] } });
    if (url.pathname === `/api/projects/${projectId}/production/v2/runs/${runId}/text/scenes/revisions`) return route.fulfill({ json: { revisions: [] } });
    if (url.pathname === `/api/projects/${projectId}/production/v2/canon`) return route.fulfill({ json: { schema_version: 1, project_id: projectId, revision: 1, characters, worlds: [] } });
    if (url.pathname === `/api/projects/${projectId}/production/v2/assets`) return route.fulfill({ json: { assets, total: assets.length, limit: 50, offset: 0 } });
    if (url.pathname === `/api/projects/${projectId}/production/v2/runs/${runId}/voice-bindings` && request.method() === "GET") return route.fulfill({ json: { bindings } });
    if (url.pathname === `/api/projects/${projectId}/production/v2/runs/${runId}/voices/bind` && request.method() === "POST") {
      const body = request.postDataJSON(); calls.push(body);
      const binding = { run_id: runId, character_id: body.character_id, voice_asset_id: "voice-master-1", strategy: body.strategy, seed: calls.length * 101, speaker_id: `S${calls.length}` };
      bindings.push(binding);
      return route.fulfill({ status: 201, json: binding });
    }
    if (url.pathname === `/api/projects/${projectId}/production/v2/runs/${runId}/dialogue-tts` && request.method() === "POST") {
      const body = request.postDataJSON(); dialogueCalls.push(body);
      return route.fulfill({ status: 202, json: { job_id: "dialogue-job-test", run_id: runId, status: "queued", prompt_id: "prompt-test" } });
    }
    if (url.pathname === `/api/projects/${projectId}/production/v2/runs/${runId}/audio-sidecars/dialogue-job-test`) {
      return route.fulfill({ json: { job_id: "dialogue-job-test", run_id: runId, status: "completed", production_asset_id: "dialogue-asset-test" } });
    }
    return route.fulfill({ status: 404, json: { detail: "Not mocked" } });
  });

  await page.goto("/production");
  await expect(page.getByRole("heading", { name: "Production workspace" })).toBeVisible();
  const initialWidth = await page.evaluate(() => ({ page: document.documentElement.scrollWidth, viewport: window.innerWidth }));
  expect(initialWidth.page, JSON.stringify(initialWidth)).toBeLessThanOrEqual(initialWidth.viewport);
  const voiceStage = page.getByRole("button", { name: /Voices & audio/ });
  await voiceStage.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Character voice bindings" })).toBeVisible();
  const voiceWidth = await page.evaluate(() => ({ page: document.documentElement.scrollWidth, viewport: window.innerWidth, overflow: Array.from(document.querySelectorAll("body *")).map((node) => ({ tag: node.tagName, id: (node as HTMLElement).id, text: (node as HTMLElement).innerText?.slice(0, 80), aria: (node as HTMLElement).getAttribute("aria-label"), className: String((node as HTMLElement).className || "").slice(0, 180), right: node.getBoundingClientRect().right, parent: node.parentElement?.outerHTML.slice(0, 200) })).filter((node) => node.right > window.innerWidth + 0.1).sort((a, b) => b.right - a.right).slice(0, 10) }));
  expect(voiceWidth.page, JSON.stringify(voiceWidth)).toBeLessThanOrEqual(voiceWidth.viewport);
  await expect(page.getByRole("list", { name: "Saved character voice choices" }).getByText(/Maya → voice\.wav \(S1\) · saved random choice/)).toBeVisible();
  await expect(page.getByRole("list", { name: "Saved character voice choices" }).getByText(/Arjun → voice\.wav \(S2\) · saved random choice/)).toBeVisible();
  expect(calls).toHaveLength(2);
  expect(calls.every((body) => body.strategy === "seeded_random" && !("voice_asset_id" in body))).toBe(true);
  await expect(page.getByRole("heading", { name: "Generate bound two-character dialogue" })).toBeVisible();
  await page.getByLabel("Speaker 1 exact dialogue").fill("The road is clear.");
  await page.getByLabel("Speaker 2 exact dialogue").fill("Then let us go.");
  await page.getByRole("button", { name: "Generate dialogue audio" }).click();
  await expect.poll(() => dialogueCalls.length).toBe(1);
  expect(dialogueCalls[0].speakers).toEqual([
    { character_id: characters[0].character_id, voice_excerpt_asset_id: "excerpt-maya" },
    { character_id: characters[1].character_id, voice_excerpt_asset_id: "excerpt-arjun" },
  ]);
  expect(dialogueCalls[0].lines.map((line: any) => line.text)).toEqual(["The road is clear.", "Then let us go."]);
  expect(dialogueCalls[0].lines.map((line: any) => [line.start_seconds, line.end_seconds])).toEqual([[0, 4], [4, 8]]);
  await expect(page.getByRole("status", { name: "Generated dialogue status" })).toContainText("completed");
  await expect(page.getByRole("status", { name: "Generated dialogue status" }).locator("audio")).toHaveAttribute("src", /dialogue-asset-test\/content$/);
  const dialogueWidth = await page.evaluate(() => ({ page: document.documentElement.scrollWidth, viewport: window.innerWidth }));
  expect(dialogueWidth.page, JSON.stringify(dialogueWidth)).toBeLessThanOrEqual(dialogueWidth.viewport);
  await page.reload();
  await page.getByRole("button", { name: /Voices & audio/ }).click();
  expect(calls).toHaveLength(2);
});

}
