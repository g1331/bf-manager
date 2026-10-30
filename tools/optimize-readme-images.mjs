// 把 docs/images/_raw/ 下的原始截图加工成 README 用的精致 webp：
//   trim 去纯色边 → 圆角 → 细边框 → 柔和投影 → 压缩。
// 用法：node tools/optimize-readme-images.mjs
// sharp 非直接依赖，运行时从 pnpm store 解析，无需改 lockfile。
import { createRequire } from "node:module";
import { readdirSync, existsSync, mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const require = createRequire(import.meta.url);
function loadSharp() {
  try {
    return require("sharp");
  } catch {
    const pnpmDir = join(process.cwd(), "node_modules", ".pnpm");
    const hit = readdirSync(pnpmDir).find((d) => /^sharp@/.test(d));
    if (!hit) throw new Error("找不到 sharp，请先 pnpm install");
    return require(join(pnpmDir, hit, "node_modules", "sharp"));
  }
}
const sharp = loadSharp();

const RAW = join("docs", "images", "_raw");
const OUT = join("docs", "images");
if (!existsSync(OUT)) mkdirSync(OUT, { recursive: true });

// 每个原图（_raw/<src>.png）→ 输出 <out>.webp，按用途给不同处理参数。
//   trim:   去掉四周纯色边（仅对纯色背景截图有效，战场底图类关掉）
//   radius: 圆角半径
//   pad:    投影留白（0 = 不加投影）
//   shadow: 投影不透明度
//   crop:   按像素裁出 [left, top, width, height]，桌面截图用它去掉左侧游戏栏和右侧空白
// 桌面原图按 1440x900 截，手机原图按 390x844@2x 截，保留 2x 分辨率。
const DESKTOP_CONTENT = [172, 0, 920, 900];
const PLAN = [
  { src: "portal", out: "banner", maxWidth: 1600, radius: 14, pad: 0, shadow: 0, trim: false, border: false, crop: [0, 72, 1600, 656] },
  { src: "server", out: "server", maxWidth: 920, radius: 12, pad: 0, shadow: 0, trim: false, crop: DESKTOP_CONTENT },
  { src: "servers", out: "servers", maxWidth: 920, radius: 12, pad: 0, shadow: 0, trim: false, crop: DESKTOP_CONTENT },
  { src: "server-players", out: "server-players", maxWidth: 920, radius: 12, pad: 0, shadow: 0, trim: false, crop: [172, 80, 920, 820] },
  { src: "server-rounds", out: "server-rounds", maxWidth: 920, radius: 12, pad: 0, shadow: 0, trim: false, crop: [172, 80, 920, 820] },
  { src: "player", out: "player", maxWidth: 920, radius: 12, pad: 0, shadow: 0, trim: false, crop: DESKTOP_CONTENT },
  { src: "mobile-server", out: "mobile-server", maxWidth: 780, radius: 36, pad: 0, shadow: 0, trim: false },
  { src: "mobile-player", out: "mobile-player", maxWidth: 780, radius: 36, pad: 0, shadow: 0, trim: false },
];

function findRaw(src) {
  return readdirSync(RAW).find((f) => f.replace(/\.[^.]+$/, "") === src);
}

async function processOne(cfg) {
  const { src, out, maxWidth, radius, pad, shadow, trim, crop, cropV, vignette, border = true } = cfg;
  const file = findRaw(src);
  if (!file) {
    console.log(`跳过 ${src}（_raw 下没有对应原图）`);
    return;
  }
  // 1) trim 去纯色边 / 按比例垂直裁剪（去掉渐变背景的大片留白）+ 限宽
  let base = sharp(join(RAW, file));
  if (crop) {
    const [left, top, width, height] = crop;
    base = base.extract({ left, top, width, height });
  }
  if (trim) base = base.trim({ threshold: 12 });
  if (cropV) {
    const m0 = await sharp(join(RAW, file)).metadata();
    const top = Math.round(m0.height * cropV[0]);
    const height = Math.round(m0.height * (cropV[1] - cropV[0]));
    base = base.extract({ left: 0, top, width: m0.width, height });
  }
  base = base.resize({ width: maxWidth, withoutEnlargement: true });
  let flat = await base.png().toBuffer();
  const meta = await sharp(flat).metadata();
  const W = meta.width;
  const H = meta.height;
  // 可选暗角（vignette）：压暗四角、聚焦左下标题区
  if (vignette) {
    const vig = Buffer.from(
      `<svg width="${W}" height="${H}"><defs><radialGradient id="v" cx="34%" cy="62%" r="80%"><stop offset="42%" stop-color="#000" stop-opacity="0"/><stop offset="100%" stop-color="#000" stop-opacity="0.5"/></radialGradient></defs><rect width="${W}" height="${H}" fill="url(#v)"/></svg>`,
    );
    flat = await sharp(flat).composite([{ input: vig }]).png().toBuffer();
  }

  // 2) 圆角（dest-in 遮罩）
  const roundMask = Buffer.from(
    `<svg width="${W}" height="${H}"><rect width="${W}" height="${H}" rx="${radius}" ry="${radius}" fill="#fff"/></svg>`,
  );
  const rounded = await sharp(flat)
    .composite([{ input: roundMask, blend: "dest-in" }])
    .png()
    .toBuffer();

  // 3) 细内描边
  const borderSvg = Buffer.from(
    `<svg width="${W}" height="${H}"><rect x="0.5" y="0.5" width="${W - 1}" height="${H - 1}" rx="${radius}" ry="${radius}" fill="none" stroke="rgba(255,255,255,0.12)" stroke-width="1"/></svg>`,
  );
  const card = border
    ? await sharp(rounded).composite([{ input: borderSvg }]).png().toBuffer()
    : rounded;

  // 4) 柔和投影 + 输出
  let outImg;
  if (pad > 0) {
    const CW = W + pad * 2;
    const CH = H + pad * 2;
    const dy = Math.round(pad * 0.35);
    const shadowSvg = Buffer.from(
      `<svg width="${CW}" height="${CH}"><rect x="${pad}" y="${pad + dy}" width="${W}" height="${H}" rx="${radius}" ry="${radius}" fill="rgba(0,0,0,${shadow})"/></svg>`,
    );
    const shadowBuf = await sharp(shadowSvg).blur(Math.max(1, pad * 0.5)).png().toBuffer();
    outImg = sharp({
      create: { width: CW, height: CH, channels: 4, background: { r: 0, g: 0, b: 0, alpha: 0 } },
    }).composite([
      { input: shadowBuf, top: 0, left: 0 },
      { input: card, top: pad, left: pad },
    ]);
  } else {
    outImg = sharp(card);
  }
  const outPath = join(OUT, `${out}.webp`);
  await outImg.webp({ quality: 88 }).toFile(outPath);
  const kb = (readFileSync(outPath).length / 1024).toFixed(0);
  console.log(`${file}  ->  ${out}.webp  (${W}x${H}, ${kb} KB)`);
}

for (const cfg of PLAN) await processOne(cfg);
