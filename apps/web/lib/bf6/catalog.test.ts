import { describe, expect, it } from "vitest";
import { gadgetInfo, mapInfo, modeInfo, vehicleInfo, weaponInfo } from "./catalog";
import { bf6PlayerHref, parsePlatform, platformLabel } from "./player-link";

describe("BF6 图鉴", () => {
  it("武器按 ID 前缀归大类，图鉴里有的带图片", () => {
    expect(weaponInfo("mg_l110")).toMatchObject({
      name: "L110",
      category: "mg",
      categoryZh: "机枪",
      img: "/bf6/weapons/mg_l110.webp",
    });
  });

  it("图鉴里没有的条目回落到 ID，不给图片", () => {
    expect(weaponInfo("xx_unknown")).toMatchObject({
      name: "xx_unknown",
      category: null,
      img: null,
    });
    expect(gadgetInfo("rl_newthing")).toMatchObject({
      name: "rl_newthing",
      group: "launcher",
      img: null,
    });
  });

  it("地图优先用 EA 官网中文名，ftp 开头的是禁区冲突", () => {
    expect(mapInfo("mpbadlands").zh).toBe("布莱克韦尔农场");
    expect(mapInfo("ftpgranite").redsec).toBe(true);
  });

  it("没有核对过中文名的模式显示英文，大逃杀模式用禁区冲突的配图", () => {
    expect(modeInfo("op").name).toBe("Operations");
    expect(modeInfo("strike").name).toBe("打击点");
    expect(modeInfo("rr_solo").art).toBe("/bf6/mode-art/granite.webp");
    expect(modeInfo("graniteSolo").art).toBe("/bf6/mode-art/granite.webp");
  });

  it("水面载具单独分组", () => {
    expect(vehicleInfo("sur_rhib").group).toBe("naval");
    expect(vehicleInfo("air_panthera").group).toBe("air");
  });
});

describe("BF6 玩家链接", () => {
  it("带上显示名和由命名空间换算的平台参数", () => {
    expect(bf6PlayerHref({ nucleus_id: 42, display_name: "A B", platform: "ps3" })).toBe(
      "/bf6/player/42?name=A+B&platform=psn",
    );
    expect(bf6PlayerHref({ nucleus_id: 42, display_name: null, platform: null })).toBe(
      "/bf6/player/42",
    );
  });

  it("只接受已知平台", () => {
    expect(parsePlatform("xbox")).toBe("xbox");
    expect(parsePlatform("nintendo")).toBeNull();
    expect(platformLabel("cem_ea_id")).toBe("EA");
    expect(platformLabel("unknown")).toBeNull();
  });
});
