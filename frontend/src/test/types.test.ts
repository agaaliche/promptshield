import { describe, it, expect } from "vitest";
import { PII_COLORS } from "../types";

describe("Types", () => {
  it("should have color mappings for all PII types", () => {
    const expectedTypes = [
      "PERSON",
      "EMAIL",
      "PHONE",
      "SSN",
      "CREDIT_CARD",
      "ADDRESS",
      "DATE",
      "ORG",
      "LOCATION",
      "IP_ADDRESS",
      "IBAN",
      "PASSPORT",
      "DRIVER_LICENSE",
      "CUSTOM",
      "UNKNOWN",
    ];
    for (const t of expectedTypes) {
      expect(PII_COLORS[t as keyof typeof PII_COLORS]).toBeDefined();
      expect(PII_COLORS[t as keyof typeof PII_COLORS]).toMatch(/^#/);
    }
  });

  it("should have a fallback color for UNKNOWN type", () => {
    expect(PII_COLORS["UNKNOWN"]).toBeDefined();
  });
});
