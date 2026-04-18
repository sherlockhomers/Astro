<!-- 月相日历 + 下个重大月相倒计时 + 未来三个月主要月相日期表。
     纯前端计算：月相只取决于时间（相对一个已知新月的时刻 + 朔望月周期）。
     后端有自己的一份公式，前端这边独立算，方便离线也能展示。 -->

<script setup lang="ts">
import { computed, ref } from "vue";
import { Moon, CalendarDays } from "lucide-vue-next";

const props = defineProps<{
  /** 基准日期，传空就是今天 */
  baseDate?: string;
}>();

// 2000-01-06 18:14 UTC 是一个已知的新月时刻（Julian Day 2451550.1）
const KNOWN_NEW_MOON_JD = 2451550.1;
const SYNODIC_PERIOD = 29.53058867;

function julianDay(date: Date): number {
  let y = date.getUTCFullYear();
  let m = date.getUTCMonth() + 1;
  const d =
    date.getUTCDate() +
    (date.getUTCHours() + date.getUTCMinutes() / 60 + date.getUTCSeconds() / 3600) / 24;
  if (m <= 2) {
    y -= 1;
    m += 12;
  }
  const a = Math.floor(y / 100);
  const b = 2 - a + Math.floor(a / 4);
  return Math.floor(365.25 * (y + 4716)) + Math.floor(30.6001 * (m + 1)) + d + b - 1524.5;
}

function phaseFraction(date: Date): number {
  // 0 = 新月，0.25 = 上弦，0.5 = 满月，0.75 = 下弦
  const jd = julianDay(date);
  const age = (((jd - KNOWN_NEW_MOON_JD) % SYNODIC_PERIOD) + SYNODIC_PERIOD) % SYNODIC_PERIOD;
  return age / SYNODIC_PERIOD;
}

function illumination(fraction: number): number {
  return (1 - Math.cos(2 * Math.PI * fraction)) / 2;
}

function phaseName(fraction: number): string {
  if (fraction < 0.03 || fraction >= 0.97) return "新月";
  if (fraction < 0.22) return "蛾眉月";
  if (fraction < 0.28) return "上弦月";
  if (fraction < 0.47) return "盈凸月";
  if (fraction < 0.53) return "满月";
  if (fraction < 0.72) return "亏凸月";
  if (fraction < 0.78) return "下弦月";
  return "残月";
}

function ageDays(date: Date): number {
  const jd = julianDay(date);
  return (((jd - KNOWN_NEW_MOON_JD) % SYNODIC_PERIOD) + SYNODIC_PERIOD) % SYNODIC_PERIOD;
}

function formatDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function formatShortDate(d: Date): string {
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

// ──── 日历数据 ───────────────────────────────────────────

const baseDate = computed(() => {
  if (props.baseDate) {
    const parsed = new Date(props.baseDate + "T12:00:00");
    if (!isNaN(parsed.getTime())) return parsed;
  }
  return new Date();
});

const todayKey = computed(() => formatDate(baseDate.value));

const calendarCells = computed(() => {
  const cells: Array<{
    date: string;
    short: string;
    weekday: string;
    fraction: number;
    illum: number;
    name: string;
    isToday: boolean;
    isKey: boolean; // 新月/上弦/满月/下弦 附近
  }> = [];
  // 从今天开始 28 天（4 周）
  for (let i = 0; i < 28; i++) {
    const d = new Date(baseDate.value);
    d.setDate(d.getDate() + i);
    d.setHours(12, 0, 0, 0);
    const frac = phaseFraction(d);
    const illum = illumination(frac);
    const name = phaseName(frac);
    const isKey = ["新月", "上弦月", "满月", "下弦月"].includes(name);
    cells.push({
      date: formatDate(d),
      short: formatShortDate(d),
      weekday: ["日", "一", "二", "三", "四", "五", "六"][d.getDay()],
      fraction: frac,
      illum,
      name,
      isToday: formatDate(d) === todayKey.value,
      isKey,
    });
  }
  return cells;
});

// ──── 寻找接下来的关键月相 ────────────────────────────

function findNextEvent(targetFraction: number, fromDate: Date): Date {
  // 从 fromDate 开始往后找，最近一次月相 fraction 跨过 targetFraction 的时刻（线性插值）
  // 采样到天级别即可，再精到小时用二分
  const cur = new Date(fromDate);
  cur.setHours(12, 0, 0, 0);
  for (let i = 0; i < 60; i++) {
    const d0 = new Date(cur);
    d0.setDate(d0.getDate() + i);
    const d1 = new Date(d0);
    d1.setDate(d1.getDate() + 1);
    const f0 = phaseFraction(d0);
    const f1 = phaseFraction(d1);

    // 跨过目标（考虑 1.0 -> 0.0 的回绕）
    const passesForward =
      (f0 <= targetFraction && targetFraction < f1) ||
      (f0 > f1 && (targetFraction >= f0 || targetFraction < f1));
    if (passesForward) {
      // 二分精细化到分钟
      let lo = d0.getTime();
      let hi = d1.getTime();
      for (let k = 0; k < 12; k++) {
        const mid = (lo + hi) / 2;
        const midDate = new Date(mid);
        const fm = phaseFraction(midDate);
        if (fm < f0 && f0 > f1) {
          // 已经跨过回绕点
          hi = mid;
        } else if (fm < targetFraction) {
          lo = mid;
        } else {
          hi = mid;
        }
      }
      return new Date((lo + hi) / 2);
    }
  }
  return new Date(cur);
}

const upcomingEvents = computed(() => {
  const events: Array<{
    label: string;
    date: Date;
    dateLabel: string;
    daysLeft: number;
    tone: "primary" | "amber" | "cyan" | "slate";
  }> = [];

  const specs: Array<{ frac: number; label: string; tone: "primary" | "amber" | "cyan" | "slate" }> = [
    { frac: 0.0,  label: "新月",   tone: "slate" },
    { frac: 0.25, label: "上弦月", tone: "cyan" },
    { frac: 0.5,  label: "满月",   tone: "amber" },
    { frac: 0.75, label: "下弦月", tone: "cyan" },
  ];

  // 从今天起，接下来三个月里每种月相可能出现 2~3 次
  for (const s of specs) {
    let cursor = new Date(baseDate.value);
    for (let rep = 0; rep < 3; rep++) {
      const next = findNextEvent(s.frac, cursor);
      if (next.getTime() - baseDate.value.getTime() > 95 * 24 * 3600 * 1000) break;
      const daysLeft = Math.floor((next.getTime() - baseDate.value.getTime()) / (24 * 3600 * 1000));
      events.push({
        label: s.label,
        date: next,
        dateLabel: `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}-${String(next.getDate()).padStart(2, "0")}`,
        daysLeft,
        tone: s.tone,
      });
      cursor = new Date(next.getTime() + 2 * 24 * 3600 * 1000);
    }
  }

  // 按时间顺序排
  events.sort((a, b) => a.date.getTime() - b.date.getTime());
  return events;
});

const nextFullMoon = computed(() => upcomingEvents.value.find((e) => e.label === "满月"));
const nextNewMoon = computed(() => upcomingEvents.value.find((e) => e.label === "新月"));

// ──── SVG 小月相绘制：用两个圆 + 椭圆投影近似相位 ────
// 0 = 新月（全暗），0.5 = 满月（全亮），渲染的关键：
//   - fraction < 0.5：右半边亮，亮宽从 0 到 2r
//   - fraction >= 0.5：左半边亮，对称

function moonPath(fraction: number, radius: number): string {
  // 绘制被照亮的半月+椭圆交界线，椭圆的水平半径决定相位宽度
  // cos(2πf) = -1 at full moon(照亮整个)，= 1 at new moon（全暗）
  const r = radius;
  const waxing = fraction < 0.5;
  const cosPhase = Math.cos(2 * Math.PI * fraction);
  const ellipseWidth = Math.abs(cosPhase) * r;

  // 大外圆起点
  const cx = 0;
  const cy = 0;
  const largeArcFlag = 1;
  const sweepRight = waxing ? 0 : 1;
  const sweepEllipse = waxing ? 0 : 1;

  if (fraction < 0.001 || fraction > 0.999) {
    // 新月：几乎全暗，画一个最细的月牙
    return `M ${cx},${-r} A ${r},${r} 0 0,1 ${cx},${r} A ${0.02 * r},${r} 0 0,0 ${cx},${-r} Z`;
  }

  if (Math.abs(fraction - 0.5) < 0.02) {
    // 满月：完全亮的圆
    return `M ${cx},${-r} A ${r},${r} 0 1,1 ${cx},${r} A ${r},${r} 0 1,1 ${cx},${-r} Z`;
  }

  // 半月偏新 / 偏满：
  // 可见亮弧 + 椭圆终止线
  return [
    `M ${cx},${-r}`,
    `A ${r},${r} 0 ${largeArcFlag},${sweepRight} ${cx},${r}`,
    `A ${ellipseWidth},${r} 0 ${largeArcFlag},${sweepEllipse} ${cx},${-r}`,
    "Z",
  ].join(" ");
}

function toneLabel(tone: string) {
  return { primary: "", amber: "", cyan: "", slate: "" }[tone] || "";
}

const hovered = ref<string>("");
</script>

<template>
  <div class="moon-wrap">
    <!-- 上排：倒计时 × 2 -->
    <div class="countdown-row">
      <div v-if="nextFullMoon" class="countdown-card full">
        <div class="cd-head">
          <Moon :size="14" class="cd-ico" />
          <span class="cd-title">距离下一次满月</span>
        </div>
        <div class="cd-number">
          <span class="cd-big">{{ nextFullMoon.daysLeft }}</span>
          <span class="cd-unit">天</span>
        </div>
        <div class="cd-date">{{ nextFullMoon.dateLabel }}</div>
      </div>
      <div v-if="nextNewMoon" class="countdown-card new">
        <div class="cd-head">
          <Moon :size="14" class="cd-ico" />
          <span class="cd-title">距离下一次新月</span>
        </div>
        <div class="cd-number">
          <span class="cd-big">{{ nextNewMoon.daysLeft }}</span>
          <span class="cd-unit">天</span>
        </div>
        <div class="cd-date">{{ nextNewMoon.dateLabel }}</div>
      </div>
    </div>

    <!-- 中：28 天月相日历 -->
    <section class="panel surface-card">
      <header class="panel-header">
        <CalendarDays :size="15" class="panel-ico" />
        <span class="panel-title">接下来 4 周月相</span>
        <span class="panel-sub">鼠标悬停看详情</span>
      </header>

      <div class="cal-grid">
        <div class="cal-head" v-for="wd in ['日', '一', '二', '三', '四', '五', '六']" :key="wd">
          {{ wd }}
        </div>
        <button
          v-for="cell in calendarCells"
          :key="cell.date"
          class="cal-cell"
          :class="{ today: cell.isToday, key: cell.isKey }"
          @mouseenter="hovered = cell.date"
          @mouseleave="hovered = ''"
          :title="`${cell.date} ${cell.name} · 亮度 ${Math.round(cell.illum * 100)}%`"
        >
          <div class="cell-date-row">
            <span class="cell-date-num">{{ cell.short }}</span>
            <span class="cell-weekday">周{{ cell.weekday }}</span>
          </div>
          <svg class="moon-icon" viewBox="-14 -14 28 28" width="26" height="26">
            <circle cx="0" cy="0" r="12" class="moon-dark" />
            <path :d="moonPath(cell.fraction, 12)" class="moon-light" />
            <circle cx="0" cy="0" r="12" class="moon-outline" />
          </svg>
          <span v-if="cell.isKey" class="cell-key">{{ cell.name }}</span>
          <span v-else class="cell-illum">{{ Math.round(cell.illum * 100) }}%</span>
        </button>
      </div>
    </section>

    <!-- 下：三个月关键月相日期表 -->
    <section class="panel surface-card">
      <header class="panel-header">
        <Moon :size="15" class="panel-ico" />
        <span class="panel-title">未来三个月主要月相</span>
        <span class="panel-sub">共 {{ upcomingEvents.length }} 次</span>
      </header>

      <div class="event-list">
        <div
          v-for="(ev, idx) in upcomingEvents"
          :key="`${ev.label}-${ev.dateLabel}-${idx}`"
          class="event-row"
          :class="`tone-${ev.tone}`"
        >
          <span class="ev-dot"></span>
          <span class="ev-label">{{ ev.label }}</span>
          <span class="ev-date">{{ ev.dateLabel }}</span>
          <span class="ev-left">还有 {{ ev.daysLeft }} 天</span>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.moon-wrap {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 倒计时 */
.countdown-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.countdown-card {
  padding: 14px 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  border: 1px solid var(--astro-border);
  background: rgba(6, 12, 22, 0.55);
  border-radius: 2px;
  transition: border-color 0.15s;
}

.countdown-card.full {
  border-color: rgba(245, 158, 11, 0.35);
  background: linear-gradient(120deg, rgba(245, 158, 11, 0.06), transparent 70%);
}

.countdown-card.new {
  border-color: rgba(19, 210, 184, 0.35);
  background: linear-gradient(120deg, rgba(19, 210, 184, 0.06), transparent 70%);
}

.cd-head {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--text-secondary);
  font-size: 11.5px;
  letter-spacing: 0.5px;
}

.cd-ico {
  color: var(--astro-primary);
}

.countdown-card.full .cd-ico {
  color: #fbbf24;
}

.cd-number {
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.cd-big {
  font-size: 32px;
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

.cd-unit {
  font-size: 13px;
  color: var(--text-secondary);
}

.cd-date {
  font-family: "Space Mono", monospace;
  font-size: 11px;
  color: var(--text-secondary);
  letter-spacing: 0.4px;
}

/* panel 通用 */
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

/* 日历 */
.cal-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 6px;
}

.cal-head {
  padding: 4px 0;
  text-align: center;
  color: var(--text-secondary);
  font-size: 11px;
  letter-spacing: 1px;
  border-bottom: 1px dashed var(--astro-border);
}

.cal-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 8px 4px 6px;
  border: 1px solid var(--astro-border);
  background: rgba(6, 12, 22, 0.4);
  color: inherit;
  cursor: pointer;
  border-radius: 2px;
  transition: all 0.15s;
}

.cal-cell:hover {
  transform: translateY(-1px);
  border-color: rgba(19, 210, 184, 0.45);
}

.cal-cell.today {
  border-color: var(--astro-primary);
  box-shadow: 0 0 0 1px rgba(19, 210, 184, 0.2) inset;
  background: rgba(19, 210, 184, 0.05);
}

.cal-cell.key {
  background: rgba(245, 158, 11, 0.04);
}

.cell-date-row {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10.5px;
  font-variant-numeric: tabular-nums;
}

.cell-date-num {
  font-weight: 600;
  color: var(--text-primary);
}

.cell-weekday {
  color: var(--text-secondary);
}

.moon-icon {
  display: block;
}

.moon-dark {
  fill: rgba(10, 18, 32, 0.95);
  stroke: none;
}

.moon-light {
  fill: #f3f4f6;
}

.moon-outline {
  fill: none;
  stroke: rgba(148, 163, 184, 0.4);
  stroke-width: 0.5;
}

.cell-illum,
.cell-key {
  font-size: 9.5px;
  color: var(--text-secondary);
  letter-spacing: 0.3px;
  font-variant-numeric: tabular-nums;
}

.cal-cell.key .cell-key {
  color: #fcd34d;
  font-weight: 600;
}

/* 事件列表 */
.event-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.event-row {
  display: grid;
  grid-template-columns: 12px 60px 1fr auto;
  align-items: center;
  gap: 10px;
  padding: 8px 4px;
  border-bottom: 1px dashed var(--astro-border);
  font-size: 12.5px;
}

.event-row:last-child {
  border-bottom: none;
}

.ev-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #64748b;
}

.tone-primary .ev-dot { background: var(--astro-primary); }
.tone-amber .ev-dot   { background: #fbbf24; }
.tone-cyan .ev-dot    { background: #38bdf8; }
.tone-slate .ev-dot   { background: #94a3b8; }

.ev-label {
  color: var(--text-primary);
  font-weight: 600;
  letter-spacing: 0.3px;
}

.tone-amber .ev-label { color: #fcd34d; }
.tone-cyan .ev-label  { color: #7dd3fc; }
.tone-slate .ev-label { color: #cbd5e1; }

.ev-date {
  font-family: "Space Mono", monospace;
  color: var(--text-secondary);
  font-size: 11.5px;
  letter-spacing: 0.3px;
}

.ev-left {
  color: var(--text-secondary);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
</style>
