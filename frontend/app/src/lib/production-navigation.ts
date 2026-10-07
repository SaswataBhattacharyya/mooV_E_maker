/** Release navigation gate. Keep false until the disposable live acceptance gate passes. */
export const NEW_PRODUCTION_NAV_ENABLED = import.meta.env.VITE_STORY_BUILDER_NEW_PRODUCTION_NAV === "true";

export const PRODUCTION_PROJECT_KEY = "story-builder.production.project";
export const PRODUCTION_RUN_KEY = "story-builder.production.run";

/** Select the project for Production V2 and discard a run only when it belongs to another project. */
export function selectProductionProject(projectId: string): void {
  const previousProjectId = localStorage.getItem(PRODUCTION_PROJECT_KEY);
  if (previousProjectId !== projectId) {
    localStorage.removeItem(PRODUCTION_RUN_KEY);
  }
  localStorage.setItem(PRODUCTION_PROJECT_KEY, projectId);
}
