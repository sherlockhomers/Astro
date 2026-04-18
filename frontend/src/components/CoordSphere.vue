<!-- 坐标转换的空白区填充：
     上半部分：纯 SVG 的"天球示意图"，输入/输出点分别用红/青标出，
              同时画出赤道（横线）和黄道（23.44° 倾斜线）两条参考环，
              肉眼能看出两个坐标系差别
     下半部分：6~8 个热门深空天体的"点一下就填入"速查卡，
              选一下自动把 RA/Dec 写到父组件的输入框里，点击转换 -->

<script setup lang="ts">
import { computed } from "vue";
import { Target, Orbit } from "lucide-vue-next";

type Frame = "equatorial" | "ecliptic";

const props = defineProps<{
  inputRa: number;
  inputDec: number;
  inputFrame: Frame;
  outputRa?: number;
  outputDec?: number;
  outputFrame?: Frame;
}>();

const emit = defineEmits<{
  (e: "pick-object", payload: { ra: number; dec: number; frame: Frame; to: Frame }): void;
}>();

// 黄赤交角
const OBLIQUITY = 23.4393;

// 把 (ra, dec) 球面坐标投到 2D 正交投影上。经度负责水平，纬度负责垂直。
// 只是用来画示意图，不需要严格的球面正投影。
function projectToXY(ra: number, dec: number, cx: number, cy: number, radius: number) {
  // ra 归 0~360，把它映射到 -180~180，然后压缩到 -radius~radius；dec -90~90 压到 -radius~radius
  let lon = ra;
  if (lon > 180) lon -= 360;
  const x = cx + (lon / 180) * radius;
  const y = cy - (dec / 90) * radius;
  return { x, y };
}

// 画椭圆表示赤道圈（正视图投影近似）
const viewBoxWidth = 360;
const viewBoxHeight = 220;
const centerX = viewBoxWidth / 2;
const centerY = viewBoxHeight / 2;
const sphereRadius = 90;

// 赤道环：水平椭圆
const equatorEllipse = {
  cx: centerX,
  cy: centerY,
  rx: sphereRadius,
  ry: sphereRadius * 0.3,
};

// 黄道环：倾斜 23.44° 的椭圆
const eclipticRotate = OBLIQUITY;

const inputPoint = computed(() =>
  projectToXY(props.inputRa, props.inputDec, centerX, centerY, sphereRadius)
);

const hasOutput = computed(
  () => typeof props.outputRa === "number" && typeof props.outputDec === "number"
);

const outputPoint = computed(() => {
  if (!hasOutput.value) return null;
  return projectToXY(
    Number(props.outputRa),
    Number(props.outputDec),
    centerX,
    centerY,
    sphereRadius
  );
});

// ──── 热门天体速查 ────────────────────────────────
// 坐标来源：SIMBAD 主流目录，赤道坐标 J2000

type FamousObject = {
  id: string;
  name: string;
  type: string;
  ra: number;    // deg
  dec: number;   // deg
  color: string;
  blurb: string;
};

const famousObjects: FamousObject[] = [
  { id: "m42", name: "M42 猎户座大星云", type: "发射星云", ra: 83.822, dec: -5.391, color: "#fca5a5", blurb: "夜空中最亮的星云之一，肉眼可见" },
  { id: "m31", name: "M31 仙女座星系", type: "旋涡星系", ra: 10.685, dec: 41.269, color: "#c4b5fd", blurb: "本星系群最大成员，250 万光年外" },
  { id: "m45", name: "M45 昴星团", type: "疏散星团", ra: 56.750, dec: 24.117, color: "#93c5fd", blurb: "七姐妹星团，肉眼可见 6~7 颗" },
  { id: "m1",  name: "M1 蟹状星云",     type: "超新星遗迹", ra: 83.633, dec: 22.015, color: "#fcd34d", blurb: "1054 年超新星爆发留下的遗骸" },
  { id: "m13", name: "M13 武仙座球状星团", type: "球状星团", ra: 250.423, dec: 36.461, color: "#fdba74", blurb: "北天最亮球状星团，含数十万颗恒星" },
  { id: "m57", name: "M57 环状星云",     type: "行星状星云", ra: 283.396, dec: 33.029, color: "#86efac", blurb: "天琴座里的烟圈，望远镜里像甜甜圈" },
  { id: "ngc224", name: "NGC 4594 草帽星系", type: "旋涡星系", ra: 189.998, dec: -11.623, color: "#a5b4fc", blurb: "侧面观看的星系，中心凸起像草帽" },
  { id: "sgra",  name: "Sgr A* 银心黑洞",  type: "超大质量黑洞", ra: 266.4168, dec: -29.0078, color: "#fda4af", blurb: "银河系中心黑洞，400 万倍太阳质量" },
];

function pickObject(obj: FamousObject) {
  // 从赤道 J2000 转到用户当前输入坐标系。默认输入是赤道，输出是黄道 —— 选完直接填入触发计算
  emit("pick-object", {
    ra: obj.ra,
    dec: obj.dec,
    frame: "equatorial",
    to: "ecliptic",
  });
}

// 在天球上也标出这些天体（红点），让人直观感受"它们分布在整个天空"
const famousDots = computed(() =>
  famousObjects.map((o) => {
    const p = projectToXY(o.ra, o.dec, centerX, centerY, sphereRadius);
    return { ...o, ...p };
  })
);
</script>

<template>
  <div class="coord-wrap">
    <!-- 天球示意图 -->
    <section class="panel surface-card">
      <header class="panel-header">
        <Orbit :size="15" class="panel-ico" />
        <span class="panel-title">天球示意</span>
        <span class="panel-sub">赤道坐标 ↔ 黄道坐标 · 23.44° 黄赤交角</span>
      </header>

      <div class="sphere-body">
        <svg
          :viewBox="`0 0 ${viewBoxWidth} ${viewBoxHeight}`"
          class="sphere-svg"
        >
          <!-- 外圆（天球边界） -->
          <circle
            :cx="centerX"
            :cy="centerY"
            :r="sphereRadius"
            class="sphere-outline"
          />

          <!-- 赤道：水平椭圆 -->
          <ellipse
            :cx="equatorEllipse.cx"
            :cy="equatorEllipse.cy"
            :rx="equatorEllipse.rx"
            :ry="equatorEllipse.ry"
            class="ring-equator"
          />
          <text
            :x="centerX + sphereRadius + 6"
            :y="centerY + 2"
            class="ring-label eq"
          >赤道</text>

          <!-- 黄道：旋转 23.44° 椭圆 -->
          <ellipse
            :cx="centerX"
            :cy="centerY"
            :rx="sphereRadius"
            :ry="sphereRadius * 0.3"
            class="ring-ecliptic"
            :transform="`rotate(${eclipticRotate} ${centerX} ${centerY})`"
          />
          <text
            :x="centerX + sphereRadius * 0.9"
            :y="centerY - 22"
            class="ring-label ec"
          >黄道</text>

          <!-- 热门天体浅色散点 -->
          <g class="famous-dots">
            <circle
              v-for="dot in famousDots"
              :key="`fd-${dot.id}`"
              :cx="dot.x"
              :cy="dot.y"
              r="2"
              :fill="dot.color"
              opacity="0.55"
            />
          </g>

          <!-- 输入点（当前用户输入的 RA/Dec） -->
          <g v-if="inputPoint">
            <circle
              :cx="inputPoint.x"
              :cy="inputPoint.y"
              r="6"
              class="point-input"
            />
            <text
              :x="inputPoint.x"
              :y="inputPoint.y - 10"
              text-anchor="middle"
              class="point-label"
            >输入 · {{ inputFrame === 'equatorial' ? '赤道' : '黄道' }}</text>
          </g>

          <!-- 输出点（转换后） -->
          <g v-if="outputPoint">
            <circle
              :cx="outputPoint.x"
              :cy="outputPoint.y"
              r="5"
              class="point-output"
            />
            <line
              v-if="inputPoint"
              :x1="inputPoint.x"
              :y1="inputPoint.y"
              :x2="outputPoint.x"
              :y2="outputPoint.y"
              class="point-arrow"
              marker-end="url(#arrow-head)"
            />
            <text
              :x="outputPoint.x"
              :y="outputPoint.y + 14"
              text-anchor="middle"
              class="point-label output"
            >输出 · {{ outputFrame === 'equatorial' ? '赤道' : '黄道' }}</text>
          </g>

          <!-- 箭头 marker -->
          <defs>
            <marker
              id="arrow-head"
              markerWidth="8"
              markerHeight="8"
              refX="7"
              refY="4"
              orient="auto"
            >
              <path d="M 0 0 L 8 4 L 0 8 Z" class="arrow-head-fill" />
            </marker>
          </defs>
        </svg>

        <div class="sphere-legend">
          <div class="legend-row">
            <span class="legend-sq red"></span>
            <span>输入 <code>({{ inputRa }}°, {{ inputDec }}°)</code></span>
          </div>
          <div class="legend-row" v-if="hasOutput">
            <span class="legend-sq cyan"></span>
            <span>输出 <code>({{ outputRa }}°, {{ outputDec }}°)</code></span>
          </div>
          <div class="legend-row muted">
            <span class="legend-sq dot"></span>
            <span>速查列表里 8 个热门天体投影位置</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 热门天体速查 -->
    <section class="panel surface-card">
      <header class="panel-header">
        <Target :size="15" class="panel-ico" />
        <span class="panel-title">热门深空天体</span>
        <span class="panel-sub">点卡片自动填入坐标并转换</span>
      </header>

      <div class="object-grid">
        <button
          v-for="obj in famousObjects"
          :key="obj.id"
          class="object-card"
          @click="pickObject(obj)"
        >
          <span class="obj-dot" :style="{ background: obj.color }"></span>
          <span class="obj-name">{{ obj.name }}</span>
          <span class="obj-type">{{ obj.type }}</span>
          <span class="obj-blurb">{{ obj.blurb }}</span>
          <span class="obj-coord">
            RA <strong>{{ obj.ra }}</strong>° · Dec <strong>{{ obj.dec }}</strong>°
          </span>
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.coord-wrap {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.panel {
  padding: 14px 18px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  border-radius: 2px;
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  padding-bottom: 8px;
  border-bottom: 1px dashed var(--astro-border);
}

.panel-ico {
  color: var(--astro-primary);
}

.panel-title {
  color: var(--text-primary);
  font-weight: 600;
  font-size: 13px;
}

.panel-sub {
  margin-left: auto;
  color: var(--text-secondary);
  font-size: 11px;
}

/* 天球 */
.sphere-body {
  display: grid;
  grid-template-columns: minmax(260px, 1.6fr) 1fr;
  gap: 16px;
  align-items: center;
}

.sphere-svg {
  width: 100%;
  max-height: 260px;
  background: radial-gradient(circle at 50% 50%, rgba(19, 210, 184, 0.04), transparent 70%);
  border: 1px solid var(--astro-border);
  border-radius: 2px;
}

.sphere-outline {
  fill: none;
  stroke: rgba(148, 163, 184, 0.35);
  stroke-dasharray: 2 3;
}

.ring-equator {
  fill: none;
  stroke: rgba(96, 165, 250, 0.7);
  stroke-width: 1.2;
}

.ring-ecliptic {
  fill: none;
  stroke: rgba(245, 158, 11, 0.75);
  stroke-width: 1.2;
  stroke-dasharray: 4 3;
}

.ring-label {
  font-size: 9px;
  font-family: "Space Mono", monospace;
  letter-spacing: 0.6px;
}

.ring-label.eq {
  fill: #60a5fa;
}

.ring-label.ec {
  fill: #fbbf24;
}

.famous-dots circle {
  opacity: 0.55;
}

.point-input {
  fill: #fca5a5;
  stroke: #fff;
  stroke-width: 1;
  filter: drop-shadow(0 0 6px rgba(248, 113, 113, 0.5));
}

.point-output {
  fill: var(--astro-primary);
  stroke: #fff;
  stroke-width: 1;
  filter: drop-shadow(0 0 6px rgba(19, 210, 184, 0.5));
}

.point-arrow {
  stroke: rgba(255, 255, 255, 0.45);
  stroke-width: 1;
  stroke-dasharray: 3 2;
}

.arrow-head-fill {
  fill: rgba(255, 255, 255, 0.55);
}

.point-label {
  fill: #fff;
  font-size: 9px;
  font-family: "Space Mono", monospace;
}

.point-label.output {
  fill: var(--astro-primary);
}

/* 图例 */
.sphere-legend {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 11.5px;
  color: var(--text-secondary);
}

.sphere-legend code {
  font-family: "Space Mono", monospace;
  color: var(--text-primary);
  font-size: 10.5px;
  background: rgba(6, 12, 22, 0.6);
  padding: 1px 5px;
  border-radius: 2px;
}

.legend-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.legend-row.muted {
  opacity: 0.75;
}

.legend-sq {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.legend-sq.red  { background: #fca5a5; }
.legend-sq.cyan { background: var(--astro-primary); }
.legend-sq.dot  { background: rgba(148, 163, 184, 0.7); }

/* 热门天体 */
.object-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
}

.object-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px 11px;
  border: 1px solid var(--astro-border);
  background: rgba(6, 12, 22, 0.55);
  color: inherit;
  text-align: left;
  cursor: pointer;
  border-radius: 2px;
  transition: all 0.15s;
  position: relative;
}

.object-card:hover {
  transform: translateY(-1px);
  border-color: rgba(19, 210, 184, 0.5);
  background: rgba(19, 210, 184, 0.04);
}

.obj-dot {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.obj-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 0.3px;
  padding-right: 14px;
}

.obj-type {
  font-size: 10.5px;
  color: var(--astro-primary);
  letter-spacing: 0.5px;
  padding: 1px 5px;
  border: 1px solid rgba(19, 210, 184, 0.3);
  border-radius: 2px;
  width: fit-content;
}

.obj-blurb {
  font-size: 11.5px;
  color: var(--text-secondary);
  line-height: 1.5;
  min-height: 32px;
}

.obj-coord {
  font-family: "Space Mono", monospace;
  font-size: 10.5px;
  color: var(--text-secondary);
  letter-spacing: 0.3px;
}

.obj-coord strong {
  color: var(--text-primary);
}

@media (max-width: 720px) {
  .sphere-body {
    grid-template-columns: 1fr;
  }
}
</style>
