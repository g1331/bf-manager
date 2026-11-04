import { describe, expect, it } from "vitest";
import type { MyServerRole } from "@/lib/api/bf1";
import type { MembershipRole } from "@/lib/api/memberships";
import { canDo, hasAnyServerAdmin, type ServerAdminAction } from "@/lib/bf1/server-admin-authz";

const role = (r: MembershipRole | null, isPlatformAdmin = false) =>
  ({ role: r, is_platform_admin: isPlatformAdmin }) as MyServerRole;

describe("canDo", () => {
  // 与后端各服管端点的 require_role(min_role) 对照
  const cases: [ServerAdminAction, MembershipRole[]][] = [
    ["kick", ["admin", "owner"]],
    ["move", ["admin", "owner"]],
    ["ban", ["admin", "owner"]],
    ["unban", ["admin", "owner"]],
    ["addVip", ["admin", "owner"]],
    ["removeVip", ["admin", "owner"]],
    ["applyVip", ["admin", "owner"]],
    ["chooseLevel", ["admin", "owner"]],
    ["addAdmin", ["owner"]],
    ["removeAdmin", ["owner"]],
  ];
  const all: MembershipRole[] = ["admin", "owner"];

  it.each(cases)("%s 允许 %o", (action, allowed) => {
    for (const r of all) {
      expect(canDo(action, role(r))).toBe(allowed.includes(r));
    }
  });

  it("平台管理员全部放行，未登录或无角色全部拒绝", () => {
    expect(canDo("addAdmin", role(null, true))).toBe(true);
    expect(canDo("kick", null)).toBe(false);
    expect(canDo("kick", undefined)).toBe(false);
    expect(canDo("kick", role(null))).toBe(false);
  });

  it("hasAnyServerAdmin：管理员、服主、平台管理员有，无角色没有", () => {
    expect(hasAnyServerAdmin(role("admin"))).toBe(true);
    expect(hasAnyServerAdmin(role("owner"))).toBe(true);
    expect(hasAnyServerAdmin(role(null, true))).toBe(true);
    expect(hasAnyServerAdmin(role(null))).toBe(false);
  });
});
