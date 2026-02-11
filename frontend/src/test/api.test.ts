import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { logError, cancelAllRequests, getPageBitmapUrl, setBaseUrl } from "../api";

describe("logError", () => {
  let consoleSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    consoleSpy.mockRestore();
  });

  it("should return a function", () => {
    const handler = logError("test-context");
    expect(typeof handler).toBe("function");
  });

  it("should log non-AbortError to console", () => {
    const handler = logError("test-context");
    const error = new Error("network fail");
    handler(error);
    expect(consoleSpy).toHaveBeenCalledWith("[test-context]", error);
  });

  it("should silently ignore AbortError", () => {
    const handler = logError("test-context");
    const error = new DOMException("The operation was aborted", "AbortError");
    handler(error);
    expect(consoleSpy).not.toHaveBeenCalled();
  });
});

describe("cancelAllRequests", () => {
  it("should not throw when called", () => {
    expect(() => cancelAllRequests()).not.toThrow();
  });
});

describe("getPageBitmapUrl", () => {
  it("should return a bitmap URL with doc id and page number", () => {
    const url = getPageBitmapUrl("doc-abc", 3);
    expect(url).toContain("doc-abc");
    expect(url).toContain("3");
    expect(url).toContain("bitmap");
  });
});

describe("setBaseUrl", () => {
  it("should not throw when called", () => {
    expect(() => setBaseUrl("http://localhost:1234")).not.toThrow();
  });
});
