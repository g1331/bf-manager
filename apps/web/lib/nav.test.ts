import { describe, expect, it } from "vitest";
import { isBf6Path } from "./nav";

describe("isBf6Path", () => {
  it("只认 /bf6 本身和它下面的路径", () => {
    expect(isBf6Path("/bf6")).toBe(true);
    expect(isBf6Path("/bf6/player/1")).toBe(true);
    expect(isBf6Path("/bf60")).toBe(false);
    expect(isBf6Path("/bf1/servers")).toBe(false);
    expect(isBf6Path("/")).toBe(false);
  });
});
