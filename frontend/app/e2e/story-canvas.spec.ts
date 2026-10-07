import { expect, test } from "@playwright/test";

test("Story Canvas is reachable and exposes revision workflow", async ({ page }) => {
  await page.goto("/canvas");
  await expect(page.getByRole("heading", { name: "Novel workspace" })).toBeVisible();
  await expect(page.getByTestId("novel-editor")).toBeVisible();
  await expect(page.getByLabel("Include narrator")).toBeVisible();
  await page.getByRole("tab", { name: "AI analysis" }).click();
  await page.getByRole("tab", { name: "Screenplay" }).click();
  await page.getByRole("tab", { name: /Revisions/ }).click();
});
