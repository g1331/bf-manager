import { describe, expect, it } from "vitest";
import { formatDuration, safeNextPath } from "@/lib/utils";

describe("safeNextPath", () => {
  it.each([
    ["/me", "/me"],
    ["/bf1/server/1?tab=players#top", "/bf1/server/1?tab=players#top"],
    ["/a/../b", "/b"],
  ])("站内路径 %s 原样保留（规范化后为 %s）", (raw, expected) => {
    expect(safeNextPath(raw, "/fallback")).toBe(expected);
  });

  it.each([
    null,
    undefined,
    "",
    "me",
    "https://evil.example",
    "//evil.example",
    "/\\evil.example",
    "/\t/evil.example",
    "javascript:alert(1)",
  ])("外站或无效值 %o 回落到默认页", (raw) => {
    expect(safeNextPath(raw, "/fallback")).toBe("/fallback");
  });
});

describe("formatDuration", () => {
  it.each([
    [0, "0m"],
    [59, "0m"],
    [600, "10m"],
    [3600, "1h 0m"],
    [5025, "1h 23m"],
  ])("%i 秒 → %s", (seconds, expected) => {
    expect(formatDuration(seconds)).toBe(expected);
  });
});
