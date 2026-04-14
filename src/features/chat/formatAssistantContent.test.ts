import { describe, expect, it } from "vitest";

import { stripAssistantMarkdownMarkers } from "./formatAssistantContent";

describe("stripAssistantMarkdownMarkers", () => {
  it("unwraps paired ** markers", () => {
    expect(stripAssistantMarkdownMarkers("**上证指数** +0.1%")).toBe("上证指数 +0.1%");
  });

  it("removes stray **", () => {
    expect(stripAssistantMarkdownMarkers("截至 2026-04-13: **")).toBe("截至 2026-04-13: ");
  });
});
