import { expect, test } from "@playwright/test";

test("Story Builder and Automation use the shared, accessible production style picker", async ({ page }) => {
  const catalog = { production_types: [{ production_type: "story_film", display_name: "Story / film", variants: [{ variant_id: "variant-quiet-123", display_name: "Quiet suspense", version: 2 }] }, { production_type: "news_report", display_name: "News / reporting", variants: [] }] };
  const styles = [{ style_id: "story_film", name: "Story / film", version: 1, description: "", stages: {} }, { style_id: "news_report", name: "News / reporting", version: 1, description: "", stages: {} }];
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/production/v2/styles") return route.fulfill({ json: catalog });
    if (path === "/api/automation/styles") return route.fulfill({ json: styles });
    if (path === "/api/automation/projects" || path === "/api/projects" || path === "/api/automation/blocks") return route.fulfill({ json: [] });
    if (path === "/api/reasoning/provider") return route.fulfill({ json: { provider: "codex", providers: [{ id: "codex", label: "Codex", model: "gpt-6-luna", available: true, compatibility: false }] } });
    return route.fulfill({ status: 404, json: { detail: "Not mocked" } });
  });

  await page.setViewportSize({ width: 390, height: 844 });
  for (const path of ["/story", "/automation"]) {
    await page.goto(path);
    const productionType = page.getByLabel("Production type");
    await expect(productionType).toBeVisible();
    await productionType.focus();
    await page.keyboard.press("ArrowDown");
    await expect(productionType).toHaveValue("news_report");
    await page.keyboard.press("ArrowUp");
    await expect(productionType).toHaveValue("story_film");
    const variant = page.getByLabel("Narrative variant");
    await expect(variant).toBeEnabled();
    await expect(variant.locator("option", { hasText: "Quiet suspense · v2" })).toHaveCount(1);
    await variant.selectOption("variant-quiet-123");
    await expect(variant).toHaveValue("variant-quiet-123");
    const bounds = await variant.boundingBox();
    expect(bounds).not.toBeNull();
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390);
  }
});
