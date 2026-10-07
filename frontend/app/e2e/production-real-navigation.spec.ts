import { expect, test } from "@playwright/test";

const projectId = process.env.REAL_NAV_PROJECT_ID;
const enabled = process.env.REAL_NAV_MODE === "enabled";
test.skip(!projectId, "Requires an isolated real persisted API with media supervisors disabled.");

for (const route of ["story", "automation"]) {
  test(`real saved ${route} project preserves the rollout navigation contract`, async ({ page }) => {
    const writes: string[] = [];
    page.on("request", (request) => {
      if (request.method() !== "GET" && new URL(request.url()).pathname.includes("/production/")) {
        writes.push(`${request.method()} ${new URL(request.url()).pathname}`);
      }
    });
    await page.addInitScript((id) => {
      if (sessionStorage.getItem("real-navigation-seeded")) return;
      sessionStorage.setItem("real-navigation-seeded", "true");
      localStorage.setItem("story-builder.currentProjectId", id);
      localStorage.setItem("story-builder.production.project", "stale-project");
      localStorage.setItem("story-builder.production.run", "stale-run");
    }, projectId!);
    await page.goto(`/${route}`);
    if (enabled) {
      await page.getByRole("button", { name: "Open production workspace" }).click();
      await expect(page).toHaveURL(/\/production$/);
      await expect(page.getByRole("heading", { name: "Production workspace" })).toBeVisible();
      await expect(page.getByLabel("Existing project")).toHaveValue(projectId!);
      await expect(page.getByLabel("Story / premise (required)")).not.toHaveValue("");
      expect(await page.evaluate(() => localStorage.getItem("story-builder.production.run"))).toBeNull();
      await page.reload();
      await expect(page.getByLabel("Existing project")).toHaveValue(projectId!);
    } else {
      await expect(page.getByRole("button", { name: "Open production workspace" })).toHaveCount(0);
      if (route === "story") {
        await expect(page.getByRole("button", { name: "Start full production" })).toBeVisible();
      }
      await expect(page).toHaveURL(new RegExp(`/${route}$`));
    }
    expect(writes).toEqual([]);
  });
}
