import { expect, test } from "@playwright/test";

test("Generate dashboard exposes Phase 2 and 3 production sections", async ({ page }) => {
  await page.goto("/generate");
  await expect(page.getByRole("heading", { name: "Generate" })).toBeVisible();
  await expect(page.getByText("Automatic mixed dialogue")).toBeVisible();
  await expect(page.getByText("ACE-Step music and Control-Foley")).toBeVisible();
  await expect(page.getByText("Local video workflows")).toBeVisible();
});

test("Audio Reconstruct exposes calibration and highlighted part recording", async ({ page }) => {
  await page.goto("/audio-reconstruct");
  await expect(page.getByRole("heading", { name: "Part-by-part dialogue recording" })).toBeVisible();
  await expect(page.getByText("Character calibration")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Highlighted dialogue part" })).toBeVisible();
  await expect(page.getByLabel("Raw recording")).toBeVisible();
});
