import { expect, test } from "@playwright/test";

test("Style Library keeps extracted evidence review separate from publish", async ({ page }) => {
  const sourceId = "style-source-0123456789abcdef";
  const variantId = "variant-0123456789abcdef";
  let sources: any[] = [];
  let drafts: any[] = [];
  let variants: any[] = [];
  const payload = { base_style_id: "story_film", display_name: "Quiet suspense", source_ids: [sourceId],
    rules_by_stage: { story: "Slow reveals", scene_direction: "Use quiet beats", image: "", audio: "", video: "", review: "Check pacing" },
    director_behavior_overrides: {}, evidence: [{ source_id: sourceId, locator: "line:1-2", quote: "Prefer quiet reveals.", statement: "Favor restrained reveals.", kind: "explicit", confidence: 0.9 }], negative_constraints: [], example_brief: "A new example." };
  const draft = { schema_version: 1, variant_id: variantId, version: 1, draft_revision: 1, status: "draft", ...payload };

  await page.route("**/api/**", async (route) => {
    const request = route.request(); const url = new URL(request.url()); const method = request.method();
    if (url.pathname === "/api/production/v2/style-sources" && method === "GET") return route.fulfill({ json: { sources } });
    if (url.pathname === "/api/production/v2/style-sources" && method === "POST") { sources = [{ source_id: sourceId, filename: "writing-guide.md", source_type: "markdown", text_character_count: 41 }]; return route.fulfill({ status: 201, json: sources[0] }); }
    if (url.pathname === "/api/production/v2/styles/drafts" && method === "GET") return route.fulfill({ json: { drafts } });
    if (url.pathname === "/api/production/v2/styles/drafts" && method === "POST") { drafts = [draft]; return route.fulfill({ status: 201, json: draft }); }
    if (url.pathname === "/api/production/v2/styles/drafts/" + variantId && method === "PUT") { const updated = { ...draft, ...request.postDataJSON(), draft_revision: 2 }; drafts = [updated]; return route.fulfill({ json: updated }); }
    if (url.pathname === `/api/production/v2/styles/drafts/${variantId}/publish`) { variants = [{ variant_id: variantId, version: 1, base_style_id: "story_film", display_name: "Quiet suspense", status: "published" }]; drafts = []; return route.fulfill({ json: { ...draft, status: "published", published_at: "2026-10-02T00:00:00Z", content_hash: "abcdef0123456789" } }); }
    if (url.pathname === "/api/production/v2/styles/variants") return route.fulfill({ json: { variants } });
    if (url.pathname === `/api/production/v2/styles/${variantId}/versions`) return route.fulfill({ json: { versions: [{ ...draft, status: "published", published_at: "2026-10-02T00:00:00Z", content_hash: "abcdef0123456789" }] } });
    if (url.pathname === "/api/production/v2/styles/analyze") return route.fulfill({ json: { status: "draft_proposal", persisted: false, provider: "codex", evidence_hash: "abc123", payload } });
    if (url.pathname === "/api/automation/projects") return route.fulfill({ json: [] });
    if (url.pathname === "/api/reasoning/provider") return route.fulfill({ json: { provider: "codex", providers: [{ id: "codex", label: "Codex", model: "gpt-6-luna", available: true, compatibility: false }] } });
    return route.fulfill({ status: 404, json: { detail: `Not mocked: ${method} ${url.pathname}` } });
  });

  await page.goto("/style-library");
  await expect(page.getByRole("heading", { name: "Narrative Style Library" })).toBeVisible();
  await page.locator("#style-source-upload").setInputFiles({ name: "writing-guide.md", mimeType: "text/markdown", buffer: Buffer.from("Prefer quiet reveals.") });
  await expect(page.getByText("writing-guide.md", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Analyze selected sources" }).click();
  await expect(page.getByText("Favor restrained reveals.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Create unpublished draft" }).click();
  await expect(page.getByText("Unpublished · revision 1")).toBeVisible();
  const draftEditor = page.getByLabel("Style draft JSON");
  const originalDraft = await draftEditor.inputValue();
  await draftEditor.fill(originalDraft.replace("Quiet suspense", "Unsaved change"));
  await expect(page.getByRole("button", { name: "Publish immutable version" })).toBeDisabled();
  await draftEditor.fill(originalDraft);
  await page.getByRole("button", { name: "Publish immutable version" }).click();
  await expect(page.getByRole("heading", { name: "Quiet suspense", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Version history" }).click();
  await expect(page.getByText("Version 1")).toBeVisible();
});
