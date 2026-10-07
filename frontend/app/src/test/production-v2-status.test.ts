import { describe, expect, it } from "vitest";
import { productionTakeNeedsPolling } from "@/lib/production-v2-status";

describe("production V2 take polling", () => {
  it("keeps polling while a delegated Director review is pending or recovering", () => {
    for (const resolution_status of [undefined, "pending", "reviewing", "review_recovery_pending"]) {
      expect(productionTakeNeedsPolling({ status: "needs_review", director_review:
        resolution_status ? { resolution_status } : null }, true)).toBe(true);
    }
  });

  it("stops after a terminal Director resolution and never polls human-owned review", () => {
    expect(productionTakeNeedsPolling({ status: "needs_review", director_review:
      { resolution_status: "accepted" } }, true)).toBe(false);
    expect(productionTakeNeedsPolling({ status: "needs_review", director_review:
      { resolution_status: "blocked" } }, true)).toBe(false);
    expect(productionTakeNeedsPolling({ status: "needs_review" }, false)).toBe(false);
  });
});
