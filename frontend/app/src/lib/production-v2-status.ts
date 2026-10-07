const ACTIVE_TAKE_STATUSES = new Set([
  "queued", "waiting_for_predecessor", "submitting", "running", "collecting",
  "cancel_requested", "recovery_required",
]);
const ACTIVE_DIRECTOR_REVIEW_STATUSES = new Set([
  "pending", "reviewing", "review_recovery_pending",
]);

export function productionTakeNeedsPolling(take: any, directorOwnsRenderApproval: boolean): boolean {
  if (ACTIVE_TAKE_STATUSES.has(String(take?.status || ""))) return true;
  if (!directorOwnsRenderApproval || take?.status !== "needs_review") return false;
  const reviewStatus = take?.director_review?.resolution_status;
  return !reviewStatus || ACTIVE_DIRECTOR_REVIEW_STATUSES.has(String(reviewStatus));
}
