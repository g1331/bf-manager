import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiException, describeApiError } from "@/lib/api-client";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function stubFetch(impl: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>) {
  const fn = vi.fn(impl);
  vi.stubGlobal("fetch", fn);
  return fn;
}

async function caught(promise: Promise<unknown>): Promise<ApiException> {
  try {
    await promise;
  } catch (err) {
    expect(err).toBeInstanceOf(ApiException);
    return err as ApiException;
  }
  throw new Error("expected the request to fail");
}

/** 模拟一个只在 signal 取消时才结束的请求 */
function hangUntilAborted(_input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  return new Promise((_resolve, reject) => {
    init?.signal?.addEventListener("abort", () => reject(init.signal?.reason));
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api 请求", () => {
  it("拼出 /api/v1 路径并带上 cookie", async () => {
    const fetchMock = stubFetch(async () => jsonResponse(200, { ok: true }));
    await expect(api.get("groups")).resolves.toEqual({ ok: true });
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/v1\/groups$/);
    expect(init?.credentials).toBe("include");
    expect(init?.method).toBe("GET");
  });

  it("204 返回 undefined", async () => {
    stubFetch(async () => new Response(null, { status: 204 }));
    await expect(api.delete("/groups/1")).resolves.toBeUndefined();
  });
});

describe("失败响应解析", () => {
  it("读出后端统一的 error 包装", async () => {
    stubFetch(async () =>
      jsonResponse(404, {
        error: { code: "NOT_FOUND", message: "服务器不存在", details: { game_id: 1 } },
      }),
    );
    const err = await caught(api.get("/bf1/servers/1"));
    expect(err.status).toBe(404);
    expect(err.code).toBe("NOT_FOUND");
    expect(err.message).toBe("服务器不存在");
    expect(err.details).toEqual({ game_id: 1 });
  });

  it("5xx 在文案后附错误编号", async () => {
    stubFetch(async () =>
      jsonResponse(500, { error: { code: "INTERNAL", message: "出错了", request_id: "req-1" } }),
    );
    const err = await caught(api.get("/x"));
    expect(err.message).toBe("出错了（错误编号 req-1）");
    expect(err.requestId).toBe("req-1");
  });

  it("503 和 4xx 不附错误编号", async () => {
    stubFetch(async () =>
      jsonResponse(503, {
        error: { code: "EA_UNAVAILABLE", message: "EA 暂时不可用", request_id: "r" },
      }),
    );
    expect((await caught(api.get("/x"))).message).toBe("EA 暂时不可用");

    stubFetch(async () =>
      jsonResponse(422, { error: { code: "EA_REJECTED", message: "EA 拒绝", request_id: "r" } }),
    );
    expect((await caught(api.get("/x"))).message).toBe("EA 拒绝");
  });

  it("FastAPI 的 detail 字符串", async () => {
    stubFetch(async () => jsonResponse(401, { detail: "Not authenticated" }));
    const err = await caught(api.get("/x"));
    expect(err.code).toBe("HTTP_401");
    expect(err.message).toBe("Not authenticated");
  });

  it("FastAPI 的参数校验错误取第一条，去掉 body 前缀", async () => {
    stubFetch(async () =>
      jsonResponse(422, {
        detail: [
          { loc: ["body", "reason"], msg: "too long" },
          { loc: ["body", "other"], msg: "ignored" },
        ],
      }),
    );
    const err = await caught(api.post("/x", { reason: "..." }));
    expect(err.code).toBe("VALIDATION_ERROR");
    expect(err.message).toBe("参数校验失败（reason）：too long");
  });

  it("非 JSON 的错误页兜底成带状态码的文案", async () => {
    stubFetch(async () => new Response("<html>Bad gateway</html>", { status: 502 }));
    const err = await caught(api.get("/x"));
    expect(err.code).toBe("HTTP_502");
    expect(err.message).toBe("请求失败（HTTP 502）");
  });
});

describe("网络失败与取消", () => {
  it("连接失败归为 NETWORK_ERROR", async () => {
    stubFetch(async () => {
      throw new TypeError("fetch failed");
    });
    const err = await caught(api.get("/x"));
    expect(err.status).toBe(0);
    expect(err.code).toBe("NETWORK_ERROR");
  });

  it("超时归为 TIMEOUT", async () => {
    stubFetch(hangUntilAborted);
    const err = await caught(api.get("/x", { timeoutMs: 10 }));
    expect(err.code).toBe("TIMEOUT");
  });

  it("调用方取消时原样抛出，不包装成 ApiException", async () => {
    stubFetch(hangUntilAborted);
    const controller = new AbortController();
    const pending = api.get("/x", { signal: controller.signal });
    controller.abort();
    await expect(pending).rejects.toSatisfy(
      (err) => !(err instanceof ApiException) && (err as Error).name === "AbortError",
    );
  });
});

describe("describeApiError", () => {
  const ex = (status: number, code: string, requestId?: string) =>
    new ApiException(status, { code, message: "m", request_id: requestId });

  it.each([
    [ex(404, "NOT_FOUND"), "not_found", false],
    [ex(429, "RATE_LIMITED"), "busy", true],
    [ex(503, "EA_BUSY"), "busy", true],
    [ex(0, "TIMEOUT"), "timeout", true],
    [ex(0, "NETWORK_ERROR"), "network", true],
    [ex(503, "EA_UNAVAILABLE"), "server", true],
    [new Error("boom"), "server", true],
  ])("%o → %s", (error, kind, retryable) => {
    const view = describeApiError(error);
    expect(view.kind).toBe(kind);
    expect(view.retryable).toBe(retryable);
  });

  it("只有本站 5xx（非 503）带反馈编号", () => {
    expect(describeApiError(ex(500, "INTERNAL", "req-9")).requestId).toBe("req-9");
    expect(describeApiError(ex(503, "EA_UNAVAILABLE", "req-9")).requestId).toBeUndefined();
  });
});
