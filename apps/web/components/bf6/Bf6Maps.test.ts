import { describe, expect, it } from "vitest";
import type { Bf6MapStats, Bf6PlayerStats } from "@/lib/api/bf6";
import { mapCards } from "./Bf6Maps";

const map = (id: string): Bf6MapStats =>
  ({ id, matches: 3, wins: 1, losses: 2, time_seconds: 600, win_rate: 1 / 3 }) as Bf6MapStats;

describe("mapCards", () => {
  const maps = [map("mpabbasid"), map("ftpgranite")];

  it("有大逃杀汇总时，禁区地图交给大逃杀面板", () => {
    const stats = { maps, redsec: { matches: 3 } } as unknown as Bf6PlayerStats;
    expect(mapCards(stats).map((m) => m.id)).toEqual(["mpabbasid"]);
  });

  it("没有大逃杀汇总时，禁区地图照常显示", () => {
    const stats = { maps, redsec: null } as unknown as Bf6PlayerStats;
    expect(mapCards(stats).map((m) => m.id)).toEqual(["mpabbasid", "ftpgranite"]);
  });
});
