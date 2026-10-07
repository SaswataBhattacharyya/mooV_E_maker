import { describe, expect, it } from "vitest";
import { isProductionImageBatchSettled, type ProductionImageJobBatch } from "@/lib/project-api";

const batch = (review: string | undefined): ProductionImageJobBatch => ({
  batch_id: "batch-1",
  generation_policy: { selection_authority: "director" },
  jobs: [{
    job_id: "job-1",
    batch_id: "batch-1",
    candidate_index: 1,
    workflow_id: "qwen_image_edit_2511",
    asset_role: "character_master",
    status: "completed",
    output_asset_id: "asset-1",
    director_review: review ? { resolution_status: review, attempt_count: 1 } : null,
  }],
});

describe("production image review polling", () => {
  it.each(["pending", "reviewing", "review_recovery_pending"])("keeps polling while review is %s", (status) => {
    expect(isProductionImageBatchSettled(batch(status))).toBe(false);
  });

  it.each(["accepted", "rejected", "blocked"])("settles after terminal review status %s", (status) => {
    expect(isProductionImageBatchSettled(batch(status))).toBe(true);
  });

  it("keeps a retake batch open until every descendant candidate is resolved", () => {
    const value = batch("retake_queued");
    expect(isProductionImageBatchSettled(value)).toBe(false);
    value.jobs[0].director_review!.retake_jobs = [{
      ...value.jobs[0],
      job_id: "job-2",
      director_review: { resolution_status: "reviewing" },
    }];
    expect(isProductionImageBatchSettled(value)).toBe(false);
    value.jobs[0].director_review!.retake_jobs![0].director_review = { resolution_status: "accepted" };
    expect(isProductionImageBatchSettled(value)).toBe(true);
  });

  it("does not treat an incomplete Full-mode job list as settled", () => {
    expect(isProductionImageBatchSettled({ batch_id: "empty", jobs: [], generation_policy: { selection_authority: "director" } })).toBe(false);
  });
});
