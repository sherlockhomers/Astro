<!-- 今夜高度曲线 + 未来 7 天窗口。所有图都是手搓 SVG，不拉 echarts，省一大堆 KB。
     布局：上面两张卡并排（曲线 | 当晚关键时刻），下面一张横贯 7 天卡。 -->

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { TrendingUp, Sunrise, Sunset, Crosshair, Calendar } from "lucide-vue-next";
import { callPlanetSchedule } from "../api";

type Sample = {
  time_utc: string;
  time_local: string;
  altitude_deg: number;
  azimuth_deg: number;
  visible: boolean;
};

type TonightPayload = {
  date: string;
  samples: Sample[];
  peak_altitude: number;
  peak_time_local: string;
  rise_time_local: string | null;
  set_time_local: string | null;
  visible_minutes: number;
};

type DaySummary = {
  date: string;
  peak_altitude: number;
  peak_time_local: string;
  visible_minutes: number;
  quality: "great" | "good" | "ok" | "poor";
};

type Props = {
  planet: string;
  city: string;
};

const props = defineProps<Props>();

const loading = ref(false);
const error = ref("");
const tonight = ref<TonightPayload | null>(null);
const week = ref<DaySummary[]>([]);

async function load() {
  if (!props.planet || !props.city) return;
  loading.value = true;
  error.value = "";
  try {
    const payload = await callPlanetSchedule({
      planet: props.planet,
      city: props.city
    });
    tonight.value = payload?.tonight || null;
    week.value = Array.isArray(payload?.week) ? payload.week : [];
  } catch (err: any) {
    error.value = err?.response?.data?.detail || "时间表接口请求失败";
    tonight.value = null;
    week.value = [];
  } finally {
    loading.value = false;
  }
}

// 父组件切了行星/城市都重新加载
watch(() => [props.planet, props.city], load, { immediate: true });

// ──── SVG 曲线计算（scoped style 里定义具体颜色） ─────────────────────

const chartWidth = 520;   // viewBox 宽
const chartHeight = 150;  // viewBox 高
const paddingL = 36;
const paddingR = 14;
const paddingT = 12;
const paddingB = 24;

const curveGeom = computed(() => {
  const samples = tonight.value?.samples ?? [];
  if (samples.length < 2) return null;

  const altMin = -10;
  const altMax = Math.max(60, Math.ceil((tonight.value?.peak_altitude ?? 60) / 10) * 10);
  const plotW = chartWidth - paddingL - paddingR;
  const plotH = chartHeight - paddingT - paddingB;

  const toX = (idx: number) => paddingL + (idx / (samples.length - 1)) * plotW;
  const toY = (alt: number) => {
    const clamped = Math.max(altMin, Math.min(altMax, alt));
    return paddingT + plotH - ((clamped - altMin) / (altMax - altMin)) * plotH;
  };

  // 上面曲线（高度）
  const lineD = samples
    .map((s, i) => `${i === 0 ? "M" : "L"} ${toX(i).toFixed(1)} ${toY(s.altitude_deg).toFixed(1)}`)
    .join(" ");

  // 闭合的面积（填充）到 altitude=0 基线
  const baselineY = toY(0);
  const areaD =
    `M ${toX(0).toFixed(1)} ${baselineY.toFixed(1)} ` +
    samples.map((s, i) => `L ${toX(i).toFixed(1)} ${toY(s.altitude_deg).toFixed(1)}`).join(" ") +
    ` L ${toX(samples.length - 1).toFixed(1)} ${baselineY.toFixed(1)} Z`;

  // y 轴刻度（0°、30°、60°、altMax）
  const yTicks: number[] = [];
  for (let v = 0; v <= altMax; v += 30) yTicks.push(v);

  // x 轴刻度：每 3 小时一个
  const xLabels = samples
    .map((s, i) => ({ x: toX(i), label: s.time_local, show: i % 6 === 0 }))
    .filter((t) => t.show);

  // 峰值点坐标
  let peak = { x: 0, y: 0, label: "", alt: 0 };
  let peakIdx = 0;
  for (let i = 1; i < samples.length; i++) {
    if (samples[i].altitude_deg > samples[peakIdx].altitude_deg) peakIdx = i;
  }
  peak = {
    x: toX(peakIdx),
    y: toY(samples[peakIdx].altitude_deg),
    label: samples[peakIdx].time_local,
    alt: samples[peakIdx].altitude_deg
  };

  return { lineD, areaD, baselineY, yTicks, toY, xLabels, peak, altMax };
});

const bestWindowLabel = computed(() => {
  const t = tonight.value;
  if (!t) return "";
  if (!t.rise_time_local && !t.set_time_local) {
    // 整晚都在地平线之上或之下
    return t.peak_altitude > 5 ? "整晚可见" : "今晚基本不可见";
  }
  const from = t.rise_time_local || tonight.value?.samples[0]?.time_local || "";
  const to = t.set_time_local || tonight.value?.samples[tonight.value.samples.length - 1]?.time_local || "";
  return `${from} → ${to}`;
});

// ──── 7 天格子图 ───────────────────────────────────────────────────

const weekCells = computed(() =>
  week.value.map((d) => {
    const ratio = Math.min(1, Math.max(0, d.peak_altitude / 90));
    return {
      ...d,
      shortDate: d.date.slice(5),     // MM-DD
      weekday: weekdayOf(d.date),
      heightRatio: ratio,
      isToday: tonight.value?.date === d.date
    };
  })
);

function weekdayOf(dateStr: string) {
  try {
    const d = new Date(dateStr + "T00:00:00");
    return ["周日", "周一", "周二", "周三", "周四", "周五", "周六"][d.getDay()];
  } catch {
    return "";
  }
}

function qualityLabel(q: string) {
  return { great: "极佳", good: "不错", ok: "一般", poor: "很差" }[q] || "";
}
</script>

<template>
  <div v-if="!loading && !tonight && !error" class="schedule-placeholder">
    等待参数...
  </div>

  <div v-if="loading" class="schedule-loading">正在计算今夜和未来 7 天观测窗口...</div>

  <div v-if="error" class="schedule-error">{{ error }}</div>

  <div v-if="tonight && !loading" class="schedule-grid">
    <!-- 左：高度曲线 -->
    <section class="panel wide surface-card">
      <header class="panel-header">
        <TrendingUp :size="15" class="panel-ico" />
        <span class="panel-title">今夜地平高度曲线</span>
        <span class="panel-date">{{ tonight.date }} · {{ props.city }}</span>
      </header>

      <svg
        v-if="curveGeom"
        class="curve-svg"
        :viewBox="`0 0 ${chartWidth} ${chartHeight}`"
        preserveAspectRatio="none"
      >
        <!-- Y 轴刻度线 -->
        <g class="grid">
          <line
            v-for="tick in curveGeom.yTicks"
            :key="tick"
            :x1="paddingL"
            :y1="curveGeom.toY(tick)"
            :x2="chartWidth - paddingR"
            :y2="curveGeom.toY(tick)"
          />
        </g>
        <!-- 地平线（0°） -->
        <line
          class="horizon"
          :x1="paddingL"
          :y1="curveGeom.baselineY"
          :x2="chartWidth - paddingR"
          :y2="curveGeom.baselineY"
        />

        <!-- 面积填充 -->
        <path class="curve-area" :d="curveGeom.areaD" />
        <!-- 曲线 -->
        <path class="curve-line" :d="curveGeom.lineD" />

        <!-- 峰值标记 -->
        <circle class="peak-dot" :cx="curveGeom.peak.x" :cy="curveGeom.peak.y" r="4" />
        <text
          class="peak-label"
          :x="curveGeom.peak.x"
          :y="curveGeom.peak.y - 8"
          text-anchor="middle"
        >
          ★ {{ curveGeom.peak.label }} · {{ curveGeom.peak.alt }}°
        </text>

        <!-- Y 轴刻度标签 -->
        <g class="axis-labels">
          <text
            v-for="tick in curveGeom.yTicks"
            :key="`yt-${tick}`"
            :x="paddingL - 6"
            :y="curveGeom.toY(tick) + 3"
            text-anchor="end"
          >{{ tick }}°</text>
        </g>

        <!-- X 轴刻度标签 -->
        <g class="axis-labels">
          <text
            v-for="(t, i) in curveGeom.xLabels"
            :key="`xl-${i}`"
            :x="t.x"
            :y="chartHeight - 6"
            text-anchor="middle"
          >{{ t.label }}</text>
        </g>
      </svg>
      <div v-else class="curve-empty">数据不足</div>

      <p class="curve-hint">
        曲线越高越适合观测。地平线以下为看不到，峰值 ★ 标出最佳时刻。
      </p>
    </section>

    <!-- 右：关键时刻快览 -->
    <section class="panel surface-card">
      <header class="panel-header">
        <Crosshair :size="15" class="panel-ico" />
        <span class="panel-title">关键时刻</span>
      </header>

      <ul class="metric-list">
        <li>
          <Sunrise :size="13" class="metric-ico up" />
          <span class="metric-k">升起</span>
          <span class="metric-v">{{ tonight.rise_time_local || "—" }}</span>
        </li>
        <li>
          <TrendingUp :size="13" class="metric-ico peak" />
          <span class="metric-k">最高</span>
          <span class="metric-v">{{ tonight.peak_time_local }} · {{ tonight.peak_altitude }}°</span>
        </li>
        <li>
          <Sunset :size="13" class="metric-ico down" />
          <span class="metric-k">落下</span>
          <span class="metric-v">{{ tonight.set_time_local || "—" }}</span>
        </li>
        <li class="highlight">
          <span class="metric-k">最佳窗口</span>
          <span class="metric-v">{{ bestWindowLabel }}</span>
        </li>
        <li>
          <span class="metric-k">今夜可见</span>
          <span class="metric-v">{{ Math.round(tonight.visible_minutes / 60 * 10) / 10 }} 小时</span>
        </li>
      </ul>
    </section>

    <!-- 底：7 天条形预报 -->
    <section class="panel full-row surface-card">
      <header class="panel-header">
        <Calendar :size="15" class="panel-ico" />
        <span class="panel-title">未来 7 天观测质量</span>
        <span class="panel-sub">柱高 = 最高地平角，颜色 = 观测质量</span>
      </header>

      <div class="week-grid">
        <button
          v-for="cell in weekCells"
          :key="cell.date"
          class="week-cell"
          :class="['q-' + cell.quality, { today: cell.isToday }]"
          :title="`${cell.date} 最高 ${cell.peak_altitude}° @ ${cell.peak_time_local}`"
        >
          <div class="bar-track">
            <div class="bar-fill" :style="{ height: `${cell.heightRatio * 100}%` }"></div>
          </div>
          <div class="cell-peak">{{ cell.peak_altitude }}°</div>
          <div class="cell-date">{{ cell.shortDate }}</div>
          <div class="cell-weekday">{{ cell.weekday }}</div>
          <div class="cell-quality">{{ qualityLabel(cell.quality) }}</div>
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.schedule-placeholder,
.schedule-loading,
.schedule-error {
  padding: 22px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 12.5px;
  border: 1px dashed var(--astro-border);
  border-radius: 2px;
}

.schedule-error {
  border-color: rgba(239, 68, 68, 0.4);
  color: #fca5a5;
  background: rgba(239, 68, 68, 0.05);
}

.schedule-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 14px;
}

.panel {
  padding: 14px 18px 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  border-radius: 2px;
}

.panel.full-row {
  grid-column: 1 / -1;
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary);
  letter-spacing: 0.5px;
  padding-bottom: 8px;
  border-bottom: 1px dashed var(--astro-border);
}

.panel-ico {
  color: var(--astro-primary);
  flex-shrink: 0;
}

.panel-title {
  color: var(--text-primary);
  font-weight: 600;
  font-size: 13px;
  letter-spacing: 0.3px;
}

.panel-date,
.panel-sub {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-secondary);
}

/* ── SVG 曲线 ───────────────────────────── */
.curve-svg {
  width: 100%;
  height: auto;
  max-height: 180px;
}

.curve-svg .grid line {
  stroke: var(--astro-border);
  stroke-width: 0.5;
  stroke-dasharray: 2 3;
  opacity: 0.5;
}

.curve-svg .horizon {
  stroke: rgba(239, 68, 68, 0.55);
  stroke-width: 1;
  stroke-dasharray: 4 2;
}

.curve-svg .curve-area {
  fill: rgba(19, 210, 184, 0.18);
}

.curve-svg .curve-line {
  fill: none;
  stroke: var(--astro-primary);
  stroke-width: 1.8;
  stroke-linejoin: round;
  filter: drop-shadow(0 0 2px rgba(19, 210, 184, 0.35));
}

.curve-svg .peak-dot {
  fill: var(--astro-primary);
  stroke: #fff;
  stroke-width: 1;
}

.curve-svg .peak-label {
  fill: #fff;
  font-size: 9px;
  font-family: "Space Mono", monospace;
  letter-spacing: 0.3px;
}

.curve-svg .axis-labels text {
  fill: var(--text-secondary);
  font-size: 9px;
  font-family: "Space Mono", monospace;
}

.curve-hint {
  margin: 0;
  font-size: 11px;
  color: var(--text-secondary);
  letter-spacing: 0.2px;
}

.curve-empty {
  padding: 40px;
  text-align: center;
  color: var(--text-secondary);
}

/* ── 关键时刻 ───────────────────────────── */
.metric-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.metric-list li {
  display: grid;
  grid-template-columns: 18px 1fr auto;
  align-items: center;
  gap: 8px;
  padding: 8px 2px;
  border-bottom: 1px dashed var(--astro-border);
  font-size: 12.5px;
}

.metric-list li:last-child {
  border-bottom: none;
}

.metric-list li.highlight {
  background: rgba(19, 210, 184, 0.05);
  padding-left: 8px;
  padding-right: 8px;
  border: 1px solid rgba(19, 210, 184, 0.25);
  border-radius: 2px;
  margin: 2px 0;
}

.metric-list li.highlight .metric-v {
  color: var(--astro-primary);
}

.metric-ico.up {
  color: #fbbf24;
}

.metric-ico.peak {
  color: var(--astro-primary);
}

.metric-ico.down {
  color: #94a3b8;
}

.metric-k {
  color: var(--text-secondary);
  font-size: 11.5px;
  letter-spacing: 0.5px;
}

.metric-v {
  color: var(--text-primary);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  justify-self: end;
}

/* ── 7 天格子图 ───────────────────────────── */
.week-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 8px;
  padding-top: 2px;
}

.week-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 10px 6px 8px;
  border: 1px solid var(--astro-border);
  background: rgba(6, 12, 22, 0.5);
  color: inherit;
  cursor: pointer;
  border-radius: 2px;
  transition: all 0.15s;
}

.week-cell:hover {
  transform: translateY(-1px);
  border-color: rgba(19, 210, 184, 0.5);
}

.week-cell.today {
  border-color: var(--astro-primary);
  box-shadow: 0 0 0 1px rgba(19, 210, 184, 0.2) inset;
}

.bar-track {
  width: 100%;
  height: 62px;
  display: flex;
  align-items: flex-end;
  background: rgba(0, 0, 0, 0.2);
  border: 1px solid transparent;
  margin-bottom: 4px;
}

.bar-fill {
  width: 100%;
  transition: height 0.5s cubic-bezier(0.2, 0.8, 0.3, 1);
}

.week-cell.q-great .bar-fill {
  background: linear-gradient(180deg, rgba(19, 210, 184, 0.95), rgba(19, 210, 184, 0.5));
}

.week-cell.q-good .bar-fill {
  background: linear-gradient(180deg, rgba(96, 165, 250, 0.9), rgba(96, 165, 250, 0.45));
}

.week-cell.q-ok .bar-fill {
  background: linear-gradient(180deg, rgba(245, 158, 11, 0.85), rgba(245, 158, 11, 0.4));
}

.week-cell.q-poor .bar-fill {
  background: linear-gradient(180deg, rgba(148, 163, 184, 0.6), rgba(148, 163, 184, 0.25));
}

.cell-peak {
  font-family: "Space Mono", monospace;
  font-size: 11px;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}

.cell-date {
  font-size: 10.5px;
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
}

.cell-weekday {
  font-size: 10px;
  color: var(--text-secondary);
}

.cell-quality {
  font-size: 10px;
  letter-spacing: 0.5px;
  padding: 1px 6px;
  border-radius: 2px;
}

.week-cell.q-great .cell-quality {
  background: rgba(19, 210, 184, 0.12);
  color: var(--astro-primary);
}

.week-cell.q-good .cell-quality {
  background: rgba(96, 165, 250, 0.12);
  color: #93c5fd;
}

.week-cell.q-ok .cell-quality {
  background: rgba(245, 158, 11, 0.12);
  color: #fcd34d;
}

.week-cell.q-poor .cell-quality {
  background: rgba(148, 163, 184, 0.12);
  color: #cbd5e1;
}

@media (max-width: 960px) {
  .schedule-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 600px) {
  .week-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}
</style>
