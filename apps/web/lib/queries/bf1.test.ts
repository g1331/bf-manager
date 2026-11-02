import { describe, expect, it } from "vitest";
import { bf1Keys } from "@/lib/queries/bf1";

describe("bf1Keys", () => {
  // 失效按前缀匹配：各类查询的首段互不相同，失效一类才不会误伤另一类
  it("每类查询的首段唯一", () => {
    const heads = Object.values(bf1Keys).map((makeKey) => {
      // 首段是常量，参数取什么都不影响；用字符串是为了兼容带 toLowerCase 的键
      const key = (makeKey as (...args: unknown[]) => readonly unknown[])("x", "x");
      return key[0];
    });
    expect(new Set(heads).size).toBe(heads.length);
  });

  it("搜索词不分大小写共用缓存", () => {
    expect(bf1Keys.playerSearch("ABC")).toEqual(bf1Keys.playerSearch("abc"));
    expect(bf1Keys.platoonSearch("Ab")).toEqual(bf1Keys.platoonSearch("aB"));
  });

  it("交换不带日期时落在 latest", () => {
    expect(bf1Keys.exchange(undefined)).toEqual(["bf1-exchange", "latest"]);
  });
});
