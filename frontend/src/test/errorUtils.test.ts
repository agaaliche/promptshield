import { describe, it, expect, vi, beforeEach } from "vitest";
import { toErrorMessage } from "../errorUtils";

describe("errorUtils", () => {
  it("should extract message from Error instance", () => {
    expect(toErrorMessage(new Error("something broke"))).toBe("something broke");
  });

  it("should convert string to message", () => {
    expect(toErrorMessage("connection refused")).toBe("connection refused");
  });

  it("should handle null/undefined", () => {
    expect(toErrorMessage(null)).toBe("null");
    expect(toErrorMessage(undefined)).toBe("undefined");
  });

  it("should handle objects with message property", () => {
    expect(toErrorMessage({ message: "custom error" })).toBe("custom error");
  });
});
