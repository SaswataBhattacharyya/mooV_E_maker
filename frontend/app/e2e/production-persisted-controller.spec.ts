import { expect, test } from "@playwright/test";
import { access, writeFile } from "node:fs/promises";

const projectId = process.env.PERSISTED_ACCEPTANCE_PROJECT_ID!;
const runId = process.env.PERSISTED_ACCEPTANCE_RUN_ID!;
const originalTakeId = process.env.PERSISTED_ACCEPTANCE_ORIGINAL_TAKE_ID!;
const retakeTakeId = process.env.PERSISTED_ACCEPTANCE_RETAKE_TAKE_ID!;
const nextTakeId = process.env.PERSISTED_ACCEPTANCE_NEXT_TAKE_ID!;

const requiredAcceptanceEnv = [projectId, runId, originalTakeId, retakeTakeId, nextTakeId];
test.skip(requiredAcceptanceEnv.some(value => !value),
  "opt-in persisted acceptance runner did not provide its isolated backend IDs");

test("real SQLite controller retake replay is discovered after browser reload", async ({ page }) => {
  test.setTimeout(90_000);
  expect(projectId && runId && originalTakeId && retakeTakeId && nextTakeId).toBeTruthy();
  const runResponses: Array<{ status: number; takes: Array<{ take_id: string; status: string; parent_take_id: string | null; director_review?: { resolution_status: string; retake_take_id?: string } }> }> = [];
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("response", async response => {
    const responseUrl = new URL(response.url());
    if (responseUrl.pathname === `/api/projects/${projectId}/production/v2/runs/${runId}`) {
      try { runResponses.push({ status: response.status(), takes: (await response.json()).takes || [] }); }
      catch (error) { errors.push(String(error)); }
    }
    if (response.status() >= 500) errors.push(`${response.status()} ${response.url()}`);
  });

  await page.addInitScript(({ selectedProjectId, selectedRunId }) => {
    localStorage.setItem("story-builder.production.project", selectedProjectId);
    localStorage.setItem("story-builder.production.run", selectedRunId);
    localStorage.setItem(`story-builder.production.workspace-stage.${selectedRunId}`, "shots");
    localStorage.setItem(`story-builder.production.stage.${selectedRunId}`, "shot_plans");
  }, { selectedProjectId: projectId, selectedRunId: runId });

  await page.goto("/production");
  await expect(page.getByRole("heading", { name: "Production job queue" })).toBeVisible({ timeout: 15_000 });
  const sourceRow = page.getByRole("button", { name: new RegExp(`${originalTakeId} · no predecessor`) });
  const retakeRow = page.getByRole("button", { name: new RegExp(`${retakeTakeId} · no predecessor`) });
  const nextRow = page.getByRole("button", { name: new RegExp(`${nextTakeId} · after ${retakeTakeId}`) });
  await expect(sourceRow).toContainText(originalTakeId);
  await expect(sourceRow).toContainText("needs review");
  await sourceRow.click();
  await expect(page.getByLabel("Director video review")).toContainText("retake queued");
  await expect(retakeRow).toContainText(retakeTakeId);
  await expect(retakeRow).toContainText("accepted");
  await expect(nextRow).toContainText(nextTakeId);
  await expect(nextRow).toContainText(`after ${retakeTakeId}`);
  await retakeRow.click();
  await expect(page.getByLabel("Selected take review")).toContainText(retakeTakeId);

  const restartReadyFile = process.env.PERSISTED_ACCEPTANCE_RESTART_READY_FILE;
  const restartContinueFile = process.env.PERSISTED_ACCEPTANCE_RESTART_CONTINUE_FILE;
  if (restartReadyFile && restartContinueFile) {
    await writeFile(restartReadyFile, "initial browser state verified\n", "utf-8");
    const deadline = Date.now() + 45_000;
    let continued = false;
    while (Date.now() < deadline) {
      try { await access(restartContinueFile); continued = true; break; }
      catch { await new Promise(resolve => setTimeout(resolve, 100)); }
    }
    expect(continued, "isolated API process restart gate was released").toBeTruthy();
  }
  await page.reload();
  await expect(page.getByRole("heading", { name: "Production job queue" })).toBeVisible();
  await expect(page.getByRole("button", { name: new RegExp(`${retakeTakeId} · no predecessor`) })).toHaveCount(1);
  await expect(page.getByRole("button", { name: new RegExp(`${nextTakeId} · after ${retakeTakeId}`) })).toBeVisible();
  expect(runResponses.length).toBeGreaterThanOrEqual(2);
  expect(runResponses.every(response => response.status === 200)).toBeTruthy();
  const persisted = runResponses.at(-1)!.takes;
  expect(persisted.filter(take => take.take_id === retakeTakeId)).toHaveLength(1);
  expect(persisted.find(take => take.take_id === originalTakeId)?.director_review?.retake_take_id).toBe(retakeTakeId);
  expect(persisted.find(take => take.take_id === retakeTakeId)?.status).toBe("accepted");
  expect(persisted.find(take => take.take_id === nextTakeId)?.parent_take_id).toBe(retakeTakeId);
  expect(errors).toEqual([]);
});
