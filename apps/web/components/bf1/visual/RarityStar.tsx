import * as React from "react";
import { type Rarity, rarityHex } from "@/lib/bf1/rarity";

export interface RarityStarProps extends Omit<React.SVGAttributes<SVGSVGElement>, "fill"> {
  rarity?: Rarity;
  size?: number;
}

/**
 * BF1 风格五角星，按 rarity 着色。
 * 同样用于武器卡稀有度框右上角的星 + 数字。
 */
export function RarityStar({ rarity = "white", size = 16, className, ...rest }: RarityStarProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill={rarityHex[rarity]}
      className={className}
      aria-hidden
      {...rest}
    >
      <path d="M12 2l2.39 7.36h7.74l-6.26 4.55 2.39 7.36L12 16.72l-6.26 4.55 2.39-7.36L1.87 9.36h7.74L12 2z" />
    </svg>
  );
}
