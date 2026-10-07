import { afterEach, describe, expect, it } from "vitest";
import { PRODUCTION_PROJECT_KEY, PRODUCTION_RUN_KEY, selectProductionProject } from "@/lib/production-navigation";

describe("production workspace navigation context", () => {
  afterEach(() => localStorage.clear());

  it("selects the requested project and preserves its selected run", () => {
    localStorage.setItem(PRODUCTION_PROJECT_KEY, "project-a");
    localStorage.setItem(PRODUCTION_RUN_KEY, "run-a");

    selectProductionProject("project-a");

    expect(localStorage.getItem(PRODUCTION_PROJECT_KEY)).toBe("project-a");
    expect(localStorage.getItem(PRODUCTION_RUN_KEY)).toBe("run-a");
  });

  it("clears a saved run when navigation switches to another project", () => {
    localStorage.setItem(PRODUCTION_PROJECT_KEY, "project-a");
    localStorage.setItem(PRODUCTION_RUN_KEY, "run-a");

    selectProductionProject("project-b");

    expect(localStorage.getItem(PRODUCTION_PROJECT_KEY)).toBe("project-b");
    expect(localStorage.getItem(PRODUCTION_RUN_KEY)).toBeNull();
  });

  it("clears an unscoped run when selecting its first known project", () => {
    localStorage.setItem(PRODUCTION_RUN_KEY, "run-a");

    selectProductionProject("project-a");

    expect(localStorage.getItem(PRODUCTION_RUN_KEY)).toBeNull();
  });
});
