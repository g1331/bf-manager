import { cn } from "@/lib/utils";

type AvatarSize = "sm" | "md" | "lg";

const SIZE_CLASS: Record<AvatarSize, string> = {
  sm: "size-9 text-sm",
  md: "size-11 text-base",
  lg: "size-20 text-2xl sm:size-24",
};

/**
 * 玩家圆形头像：有 avatar_url 时渲染图片，否则降级显示昵称首字母。
 *
 * EA 头像域不在 next/image remotePatterns 内，沿用原生 <img>。online 给定时画在线（绿）/
 * 离线（灰）色环；缺省（如搜索结果无在线信息）则不画环。
 */
export function PlayerAvatar({
  avatarUrl,
  displayName,
  size = "md",
  online,
}: {
  avatarUrl: string | null;
  displayName: string;
  size?: AvatarSize;
  online?: boolean | null;
}) {
  const ring = online === undefined ? undefined : online ? "#3aca6b" : "#6b6b72";
  return (
    <div
      className={cn(
        "flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-gradient-to-br from-zinc-700 to-zinc-900 font-bold text-white",
        SIZE_CLASS[size],
        ring ? "border-4" : "",
      )}
      style={ring ? { borderColor: ring } : undefined}
    >
      {avatarUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={avatarUrl}
          alt={displayName}
          loading="lazy"
          className="size-full rounded-full object-cover"
        />
      ) : (
        displayName.slice(0, 1).toUpperCase()
      )}
    </div>
  );
}
