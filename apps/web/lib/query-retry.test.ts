import { describe, expect, it } from "vitest";
import { ApiException } from "@/lib/api-client";
import { shouldRetryQuery } from "@/lib/query-retry";

const ex = (status: number, code = "X") => new ApiException(status, { code, message: "m" });

describe("shouldRetryQuery", () => {
  it.each([400, 401, 403, 404, 422, 429])("%i 不重试", (status) => {
    expect(shouldRetryQuery(0, ex(status))).toBe(false);
  });

  it("查询繁忙和超时不重试", () => {
    expect(shouldRetryQuery(0, ex(503, "EA_BUSY"))).toBe(false);
    expect(shouldRetryQuery(0, ex(0, "TIMEOUT"))).toBe(false);
  });

  it("5xx 与网络失败最多再试两次", () => {
    for (const error of [ex(503, "EA_UNAVAILABLE"), ex(0, "NETWORK_ERROR"), new Error("x")]) {
      expect(shouldRetryQuery(0, error)).toBe(true);
      expect(shouldRetryQuery(1, error)).toBe(true);
      expect(shouldRetryQuery(2, error)).toBe(false);
    }
  });
});
