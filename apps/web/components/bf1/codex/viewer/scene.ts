/**
 * 狗牌、勋章的 3D 检视场景（three.js，只在检视器里按需加载）。
 *
 * 两种物件都是用原图现搭的，不需要模型文件：
 *   - 狗牌：圆片挤出厚度、倒角，挂孔开在 y = -0.718R 处（量自 300px 原图），一面贴一张狗牌图，
 *     另一面贴搭配的狗牌或留空白金属；挂孔里穿一个开口圈。
 *   - 勋章：同一张带透明通道的图叠 16 层，按透明度裁出轮廓，叠出约 0.08 的厚度；
 *     最后一层只渲染背面，从背后看是正面的镜像，轮廓和中间各层严格对齐。
 * 颜色贴图同时当凹凸贴图用，转动时金属上的花纹会随光线起伏。
 */

import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";

export type ViewerSubject =
  { kind: "tag"; front: string | null; back: string | null } | { kind: "medal"; image: string };

export interface Viewer {
  show(subject: ViewerSubject): Promise<void>;
  flip(): void;
  reset(): void;
  setAutoRotate(on: boolean): void;
  /** 暂停 / 恢复渲染循环（滚出视口时省电） */
  setActive(on: boolean): void;
  dispose(): void;
}

const TAG_RADIUS = 1;
const TAG_THICKNESS = 0.06;
const TAG_HOLE_Y = -0.718;
const TAG_HOLE_R = 0.1;
const MEDAL_SIZE = 2.6;
const MEDAL_THICKNESS = 0.08;
const MEDAL_LAYERS = 16;
/** 拖动结束多久后恢复自动旋转 */
const IDLE_MS = 4000;

export function createViewer(
  canvas: HTMLCanvasElement,
  opts: { reducedMotion: boolean; onSide?: (front: boolean) => void },
): Viewer {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  // ACES 会把旧图压灰，Neutral 能保住原图的颜色
  renderer.toneMapping = THREE.NeutralToneMapping;

  const scene = new THREE.Scene();
  const pmrem = new THREE.PMREMGenerator(renderer);
  const envMap = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environment = envMap;
  scene.environmentIntensity = 0.85;

  const camera = new THREE.PerspectiveCamera(30, 1, 0.05, 60);
  const key = new THREE.DirectionalLight(0xfff0d8, 1.7);
  key.position.set(2.5, 3.5, 4);
  const rim = new THREE.DirectionalLight(0xa8b8ff, 0.7);
  rim.position.set(-3, 1.5, -3.5);
  scene.add(key, rim, new THREE.AmbientLight(0xffffff, 0.15));

  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.enablePan = false;
  controls.rotateSpeed = 0.8;
  controls.zoomSpeed = 0.9;
  controls.autoRotateSpeed = 1.4;
  let autoWanted = !opts.reducedMotion;
  controls.autoRotate = autoWanted;
  let idle: ReturnType<typeof setTimeout> | undefined;
  controls.addEventListener("start", () => {
    controls.autoRotate = false;
    clearTimeout(idle);
  });
  controls.addEventListener("end", () => {
    idle = setTimeout(() => (controls.autoRotate = autoWanted), IDLE_MS);
  });

  // 物件下方一团柔和的影子，让它看起来悬在桌面上方
  const shadowCanvas = document.createElement("canvas");
  shadowCanvas.width = shadowCanvas.height = 256;
  const g2d = shadowCanvas.getContext("2d")!;
  const grad = g2d.createRadialGradient(128, 128, 0, 128, 128, 128);
  grad.addColorStop(0, "rgba(0,0,0,0.55)");
  grad.addColorStop(1, "rgba(0,0,0,0)");
  g2d.fillStyle = grad;
  g2d.fillRect(0, 0, 256, 256);
  const shadowTex = new THREE.CanvasTexture(shadowCanvas);
  const shadow = new THREE.Mesh(
    new THREE.PlaneGeometry(1, 1),
    new THREE.MeshBasicMaterial({ map: shadowTex, transparent: true, depthWrite: false }),
  );
  shadow.rotation.x = -Math.PI / 2;
  scene.add(shadow);

  const holder = new THREE.Group();
  scene.add(holder);

  const steel = new THREE.MeshStandardMaterial({ color: 0xa7a39a, metalness: 1, roughness: 0.32 });
  const edge = new THREE.MeshStandardMaterial({ color: 0x15120d, roughness: 0.85 });
  const loader = new THREE.TextureLoader();
  const anisotropy = renderer.capabilities.getMaxAnisotropy();

  async function texture(url: string): Promise<THREE.Texture> {
    const t = await loader.loadAsync(url);
    t.colorSpace = THREE.SRGBColorSpace;
    t.anisotropy = anisotropy;
    return t;
  }

  /** 让 ShapeGeometry 的 UV 正好铺满 w×h 的贴图 */
  function faceGeometry(shape: THREE.Shape, w: number, h: number) {
    const geo = new THREE.ShapeGeometry(shape, 48);
    const pos = geo.attributes.position;
    const uv = geo.attributes.uv;
    for (let i = 0; i < pos.count; i++) uv.setXY(i, pos.getX(i) / w + 0.5, pos.getY(i) / h + 0.5);
    return geo;
  }

  async function buildTag(front: string | null, back: string | null) {
    const [ft, bt] = await Promise.all([
      front ? texture(front) : null,
      back ? texture(back) : null,
    ]);
    const shape = new THREE.Shape();
    shape.absarc(0, 0, TAG_RADIUS, 0, Math.PI * 2, false);
    const hole = new THREE.Path();
    hole.absarc(0, TAG_HOLE_Y, TAG_HOLE_R, 0, Math.PI * 2, true);
    shape.holes.push(hole);

    const body = new THREE.ExtrudeGeometry(shape, {
      depth: TAG_THICKNESS,
      bevelEnabled: true,
      bevelThickness: 0.012,
      bevelSize: 0.012,
      bevelSegments: 3,
      curveSegments: 48,
    });
    body.translate(0, 0, -TAG_THICKNESS / 2);
    const group = new THREE.Group();
    group.add(new THREE.Mesh(body, [edge, steel]));

    const face = faceGeometry(shape, 2 * TAG_RADIUS, 2 * TAG_RADIUS);
    const z = TAG_THICKNESS / 2 + 0.0125;
    const faceMaterial = (t: THREE.Texture | null) =>
      t
        ? new THREE.MeshStandardMaterial({
            map: t,
            bumpMap: t,
            bumpScale: 2,
            metalness: 0.55,
            roughness: 0.38,
            alphaTest: 0.4,
          })
        : steel;
    const f = new THREE.Mesh(face, faceMaterial(ft));
    f.position.z = z;
    const b = new THREE.Mesh(face, faceMaterial(bt));
    b.rotation.y = Math.PI;
    b.position.z = -z;
    // 开口圈立在 YZ 平面里，穿过挂孔与下缘之间那段金属
    const ring = new THREE.Mesh(new THREE.TorusGeometry(0.16, 0.022, 14, 48), steel);
    ring.rotation.y = Math.PI / 2;
    ring.position.y = TAG_HOLE_Y - TAG_HOLE_R - 0.091;
    group.add(f, b, ring);
    return { object: group, height: 2.3, width: 2.1 };
  }

  async function buildMedal(image: string) {
    const t = await texture(image);
    const geo = new THREE.PlaneGeometry(MEDAL_SIZE, MEDAL_SIZE);
    const common = { map: t, alphaTest: 0.5 };
    const front = new THREE.MeshStandardMaterial({
      ...common,
      bumpMap: t,
      bumpScale: 2.5,
      metalness: 0.5,
      roughness: 0.35,
    });
    const back = new THREE.MeshStandardMaterial({
      ...common,
      bumpMap: t,
      bumpScale: 2.5,
      color: 0x9c907c,
      metalness: 0.65,
      roughness: 0.4,
      side: THREE.BackSide,
    });
    const mid = new THREE.MeshStandardMaterial({
      ...common,
      color: 0x5d4b2c,
      metalness: 0.9,
      roughness: 0.35,
      side: THREE.DoubleSide,
    });
    const group = new THREE.Group();
    for (let i = 0; i < MEDAL_LAYERS; i++) {
      const mat = i === MEDAL_LAYERS - 1 ? front : i === 0 ? back : mid;
      const layer = new THREE.Mesh(geo, mat);
      layer.position.z = -MEDAL_THICKNESS / 2 + (MEDAL_THICKNESS * i) / (MEDAL_LAYERS - 1);
      group.add(layer);
    }
    return { object: group, height: MEDAL_SIZE * 0.95, width: MEDAL_SIZE * 0.55 };
  }

  /** 按物件尺寸和画布比例取景，缩放上下限跟着距离走 */
  function frame(height: number, width: number) {
    const fov = (camera.fov * Math.PI) / 180;
    const dist = (Math.max(height / 2, width / 2 / camera.aspect) / Math.tan(fov / 2)) * 1.28;
    controls.target.set(0, 0, 0);
    camera.position.set(0, height * 0.06, dist);
    controls.minDistance = dist * 0.32;
    controls.maxDistance = dist * 1.8;
    controls.update();
    controls.saveState();
    shadow.position.y = -height / 2 - 0.28;
    shadow.scale.set(width * 1.5, width * 0.7, 1);
  }

  let current: THREE.Object3D | null = null;
  let lastSize = { height: 2, width: 2 };
  let flipTarget = 0;
  let token = 0;

  function disposeObject(obj: THREE.Object3D) {
    obj.traverse((o) => {
      if (!(o instanceof THREE.Mesh)) return;
      o.geometry.dispose();
      for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
        if (m === steel || m === edge) continue;
        (m as THREE.MeshStandardMaterial).map?.dispose();
        m.dispose();
      }
    });
  }

  function resize() {
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    // 画面整体上移一点，给底部的按钮条让出位置，旋转中心仍在物件上
    camera.setViewOffset(w, h, 0, Math.round(h * 0.05), w, h);
    camera.updateProjectionMatrix();
    frame(lastSize.height, lastSize.width);
  }
  const ro = new ResizeObserver(resize);
  ro.observe(canvas);

  const facing = new THREE.Vector3();
  const toCamera = new THREE.Vector3();
  let lastFront: boolean | null = null;
  const loop = () => {
    holder.rotation.y += (flipTarget - holder.rotation.y) * (opts.reducedMotion ? 1 : 0.12);
    controls.update();
    // 物件正面朝向和相机方向同向，就是在看正面
    facing.set(0, 0, 1).applyQuaternion(holder.quaternion);
    toCamera.copy(camera.position).normalize();
    const front = facing.dot(toCamera) >= 0;
    if (front !== lastFront) {
      lastFront = front;
      opts.onSide?.(front);
    }
    renderer.render(scene, camera);
  };
  renderer.setAnimationLoop(loop);

  return {
    async show(subject) {
      const my = ++token;
      const built =
        subject.kind === "tag"
          ? await buildTag(subject.front, subject.back)
          : await buildMedal(subject.image);
      if (my !== token) {
        disposeObject(built.object);
        return;
      }
      if (current) {
        holder.remove(current);
        disposeObject(current);
      }
      current = built.object;
      holder.add(current);
      holder.rotation.y = 0;
      flipTarget = 0;
      lastFront = null;
      lastSize = { height: built.height, width: built.width };
      resize();
    },
    flip() {
      flipTarget += Math.PI;
    },
    reset() {
      controls.reset();
      // 回到最近的一个正面朝前的角度，而不是倒着转回去好几圈
      flipTarget = Math.round(holder.rotation.y / (Math.PI * 2)) * Math.PI * 2;
    },
    setAutoRotate(on) {
      autoWanted = on;
      controls.autoRotate = on;
    },
    setActive(on) {
      renderer.setAnimationLoop(on ? loop : null);
    },
    dispose() {
      token++;
      clearTimeout(idle);
      ro.disconnect();
      renderer.setAnimationLoop(null);
      controls.dispose();
      if (current) disposeObject(current);
      steel.dispose();
      edge.dispose();
      shadow.geometry.dispose();
      (shadow.material as THREE.Material).dispose();
      shadowTex.dispose();
      envMap.dispose();
      pmrem.dispose();
      renderer.dispose();
    },
  };
}

/** 浏览器能不能开 WebGL；不能时检视器退回静态图 */
export function webglAvailable(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") ?? c.getContext("webgl"));
  } catch {
    return false;
  }
}
