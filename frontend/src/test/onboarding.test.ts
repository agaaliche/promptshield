import { describe, it, expect, beforeEach } from "vitest";
import { hasCompletedOnboarding, recordOnboardingComplete } from "../components/OnboardingWizard";

describe("OnboardingWizard helpers", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("hasCompletedOnboarding returns false initially", () => {
    expect(hasCompletedOnboarding()).toBe(false);
  });

  it("hasCompletedOnboarding returns true after recording", () => {
    recordOnboardingComplete();
    expect(hasCompletedOnboarding()).toBe(true);
  });

  it("hasCompletedOnboarding returns false for old version", () => {
    localStorage.setItem("promptshield_onboarding_completed", "0");
    expect(hasCompletedOnboarding()).toBe(false);
  });
});
