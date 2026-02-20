import { describe, it, expect, beforeEach, vi } from "vitest";
import { EULA_VERSION, hasAcceptedEula, recordEulaAcceptance } from "../eulaVersion";

describe("eulaVersion", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("hasAcceptedEula returns false when nothing stored", () => {
    expect(hasAcceptedEula()).toBe(false);
  });

  it("hasAcceptedEula returns true after recording acceptance", () => {
    recordEulaAcceptance();
    expect(hasAcceptedEula()).toBe(true);
  });

  it("hasAcceptedEula returns false for outdated version", () => {
    localStorage.setItem("eula_accepted_version", "0.9");
    expect(hasAcceptedEula()).toBe(false);
  });

  it("recordEulaAcceptance stores the current version", () => {
    recordEulaAcceptance();
    expect(localStorage.getItem("eula_accepted_version")).toBe(EULA_VERSION);
  });
});
