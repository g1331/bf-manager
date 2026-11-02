import { describe, expect, it } from "vitest";
import {
  DEFAULT_FILTERS,
  filtersFromSearch,
  filtersToSearch,
  presetActive,
  pruneRules,
  rulesToParams,
  sanitizeFilters,
  setRule,
  togglePreset,
  type FilterState,
} from "@/lib/bf1/server-filters";

const NO_VEHICLES = { "vehicles.L": "off", "vehicles.A": "off" } as const;

describe("server filters URL", () => {
  it("写进 URL 再读回来不变", () => {
    const f: FilterState = {
      ...DEFAULT_FILTERS,
      modes: ["Conquest"],
      sizes: [64],
      emptySlots: ["10+"],
      serverTypes: ["RANKED"],
      rules: { "vehicles.L": "off", "misc.3S": "on", "scales.BD": "BD3" },
      includeEmpty: true,
      nameFilter: " abc ",
    };
    const qs = filtersToSearch(f);
    expect(qs).toContain("rule=misc.3S%3Aon");
    expect(filtersFromSearch(qs)).toEqual({ ...f, nameFilter: "abc" });
  });

  it("没有筛选参数时交给 localStorage", () => {
    expect(filtersFromSearch("")).toBeNull();
    expect(filtersFromSearch("?utm=x")).toBeNull();
  });

  it("丢掉过时或被手改的取值", () => {
    const f = filtersFromSearch(
      "mode=Nope&mode=Rush&size=63&type=UNRANKED&rule=vehicles.L:maybe&rule=bad:on&rule=kits.HERO:off&rule=scales.BD:bd3&rule=scales.TC:TC3",
    );
    expect(f).toEqual({
      ...DEFAULT_FILTERS,
      modes: ["Rush"],
      rules: { "kits.HERO": "off", "scales.TC": "TC3" },
    });
    expect(sanitizeFilters("garbage")).toEqual(DEFAULT_FILTERS);
    expect(sanitizeFilters({ rules: [1, 2], sizes: "64" })).toEqual(DEFAULT_FILTERS);
  });
});

describe("rules", () => {
  it("按键排序转接口参数", () => {
    expect(rulesToParams({ "weapons.SIR": "on", "kits.HERO": "off" })).toEqual([
      "kits.HERO:off",
      "weapons.SIR:on",
    ]);
  });

  it("快捷标签叠加与撤销", () => {
    const on = togglePreset({ "vehicles.L": "on", "misc.FF": "on" }, NO_VEHICLES);
    // 同一开关以标签为准，其它规则保留
    expect(on).toEqual({ "vehicles.L": "off", "vehicles.A": "off", "misc.FF": "on" });
    expect(presetActive(on, NO_VEHICLES)).toBe(true);
    expect(togglePreset(on, NO_VEHICLES)).toEqual({ "misc.FF": "on" });
  });

  it("单个开关设为不限即删除", () => {
    expect(setRule({ "kits.HERO": "off" }, "kits.HERO", null)).toEqual({});
    expect(setRule({}, "kits.HERO", "on")).toEqual({ "kits.HERO": "on" });
  });
});

describe("pruneRules", () => {
  it("按目录裁掉不存在的规则键与取值", () => {
    const catalog = {
      groups: [
        {
          rules: [
            { key: "kits.HERO", options: [{ value: "on" }, { value: "off" }] },
            { key: "scales.BD", options: [{ value: "BD1" }, { value: "BD3" }] },
          ],
        },
      ],
    };
    expect(
      pruneRules(
        { "kits.HERO": "off", "kits.X": "on", "misc.RETIRED": "off", "scales.BD": "BD9" },
        catalog,
      ),
    ).toEqual({ "kits.HERO": "off" });
  });
});
