<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import * as echarts from "echarts";

type Planet = {
  id: string;
  name: string;
  orbitAu: number;
  orbitalPeriod: string;
  eccentricity: number;
  color: string;
  size: number;
  category: string;
  speedFactor: number;
};

const chartRef = ref<HTMLElement | null>(null);
const selectedPlanetId = ref<string | null>(null);
const hoveredPlanet = ref<Planet | null>(null);

let chartInstance: echarts.ECharts | null = null;
let animationFrameId: number | null = null;
let resizeObserver: ResizeObserver | null = null;
let currentAngle = 0;

const planets: Planet[] = [
  { id: "mercury", name: "水星", orbitAu: 0.39, orbitalPeriod: "88 天", eccentricity: 0.205, color: "#b8b8b8", size: 6, category: "类地行星", speedFactor: 4.74 },
  { id: "venus", name: "金星", orbitAu: 0.72, orbitalPeriod: "225 天", eccentricity: 0.007, color: "#f0c98a", size: 7, category: "类地行星", speedFactor: 1.62 },
  { id: "earth", name: "地球", orbitAu: 1.0, orbitalPeriod: "365 天", eccentricity: 0.017, color: "#5ea8ff", size: 8, category: "类地行星", speedFactor: 1.0 },
  { id: "mars", name: "火星", orbitAu: 1.52, orbitalPeriod: "687 天", eccentricity: 0.093, color: "#d8704b", size: 7, category: "类地行星", speedFactor: 0.53 },
  { id: "jupiter", name: "木星", orbitAu: 5.2, orbitalPeriod: "11.86 年", eccentricity: 0.049, color: "#c6a06c", size: 15, category: "气态巨行星", speedFactor: 0.084 },
  { id: "saturn", name: "土星", orbitAu: 9.58, orbitalPeriod: "29.46 年", eccentricity: 0.057, color: "#dec47a", size: 13, category: "气态巨行星", speedFactor: 0.034 },
  { id: "uranus", name: "天王星", orbitAu: 19.2, orbitalPeriod: "84 年", eccentricity: 0.046, color: "#73cce0", size: 11, category: "冰巨行星", speedFactor: 0.012 },
  { id: "neptune", name: "海王星", orbitAu: 30.1, orbitalPeriod: "164.8 年", eccentricity: 0.009, color: "#4a75ef", size: 11, category: "冰巨行星", speedFactor: 0.006 }
];

const visiblePlanets = computed(() => {
  if (!selectedPlanetId.value) return planets;
  return planets.filter((planet) => planet.id === selectedPlanetId.value);
});

function scaleOrbit(orbitAu: number): number {
  return Math.log(orbitAu + 1) * 118 + 34;
}

function buildStarField() {
  return Array.from({ length: 140 }, () => ({
    value: [(Math.random() - 0.5) * 760, (Math.random() - 0.5) * 760],
    symbolSize: Math.random() * 1.8 + 0.4
  }));
}

function buildOrbitPoints(planet: Planet): [number, number][] {
  const semiMajorAxis = scaleOrbit(planet.orbitAu);
  const semiMinorAxis = semiMajorAxis * Math.sqrt(1 - planet.eccentricity * planet.eccentricity);
  const points: [number, number][] = [];
  for (let degree = 0; degree <= 360; degree += 2) {
    const radian = (degree * Math.PI) / 180;
    points.push([semiMajorAxis * Math.cos(radian), semiMinorAxis * Math.sin(radian)]);
  }
  return points;
}

function buildPlanetPoint(planet: Planet, angle: number) {
  const semiMajorAxis = scaleOrbit(planet.orbitAu);
  const semiMinorAxis = semiMajorAxis * Math.sqrt(1 - planet.eccentricity * planet.eccentricity);
  const currentRadian = (((angle * planet.speedFactor) % 360) * Math.PI) / 180;
  return {
    value: [semiMajorAxis * Math.cos(currentRadian), semiMinorAxis * Math.sin(currentRadian)],
    name: planet.name,
    planetId: planet.id,
    symbolSize: planet.size,
    itemStyle: {
      color: planet.color,
      shadowColor: planet.color,
      shadowBlur: 16
    }
  };
}

function buildOption(angle: number): echarts.EChartsOption {
  const orbitSeries = visiblePlanets.value.map((planet) => ({
    type: "line",
    name: `orbit-${planet.id}`,
    data: buildOrbitPoints(planet),
    showSymbol: false,
    silent: true,
    z: 1,
    lineStyle: {
      color: planet.color,
      opacity: 0.28,
      width: 1.1,
      type: "dashed"
    }
  }));

  const planetPoints = visiblePlanets.value.map((planet) => buildPlanetPoint(planet, angle));

  return {
    animation: false,
    backgroundColor: "transparent",
    grid: { left: 0, right: 0, top: 0, bottom: 0 },
    xAxis: {
      type: "value",
      min: -380,
      max: 380,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { show: false },
      splitLine: { show: false }
    },
    yAxis: {
      type: "value",
      min: -380,
      max: 380,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { show: false },
      splitLine: { show: false }
    },
    tooltip: {
      trigger: "item",
      backgroundColor: "rgba(6, 12, 22, 0.94)",
      borderColor: "rgba(212, 159, 74, 0.35)",
      borderWidth: 1,
      padding: [10, 14],
      textStyle: { color: "#e6edf7", fontSize: 12 },
      formatter: (params: any) => {
        if (params.seriesName !== "planets") return "";
        const planet = planets.find((item) => item.name === params.name);
        if (!planet) return "";
        return [
          `<div style="font-weight:700;color:${planet.color};margin-bottom:6px">${planet.name}</div>`,
          `<div>轨道半径：${planet.orbitAu} AU</div>`,
          `<div>公转周期：${planet.orbitalPeriod}</div>`,
          `<div>类别：${planet.category}</div>`
        ].join("");
      }
    },
    series: [
      {
        type: "scatter",
        name: "stars",
        data: buildStarField(),
        silent: true,
        z: 0,
        itemStyle: { color: "rgba(255,255,255,0.30)" }
      },
      ...orbitSeries,
      {
        type: "scatter",
        name: "sun",
        data: [{ value: [0, 0], symbolSize: 24 }],
        silent: true,
        z: 8,
        itemStyle: {
          color: new echarts.graphic.RadialGradient(0.5, 0.5, 0.6, [
            { offset: 0, color: "#fff1b8" },
            { offset: 0.45, color: "#ffc447" },
            { offset: 1, color: "#ff7a18" }
          ]),
          shadowColor: "#ffc447",
          shadowBlur: 36
        }
      },
      {
        type: "scatter",
        name: "planets",
        z: 6,
        data: planetPoints
      },
      {
        type: "scatter",
        name: "labels",
        z: 7,
        silent: true,
        data: planetPoints.map((point, index) => ({
          ...point,
          symbolSize: 0,
          label: {
            show: true,
            formatter: visiblePlanets.value[index].name,
            position: "top",
            distance: 8,
            color: visiblePlanets.value[index].color,
            fontSize: 10,
            fontFamily: "'Space Mono', monospace"
          }
        }))
      }
    ]
  };
}

function renderChart() {
  if (!chartInstance || !chartRef.value) return;
  chartInstance.resize({
    width: chartRef.value.clientWidth || 900,
    height: chartRef.value.clientHeight || 460
  });
  chartInstance.setOption(buildOption(currentAngle), true);
}

function initChart() {
  if (!chartRef.value) return;
  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value, undefined, { renderer: "canvas" });
    chartInstance.on("mouseover", (params: any) => {
      if (params.seriesName !== "planets") return;
      hoveredPlanet.value = planets.find((planet) => planet.name === params.name) ?? null;
    });
    chartInstance.on("mouseout", (params: any) => {
      if (params.seriesName !== "planets") return;
      hoveredPlanet.value = null;
    });
  }

  renderChart();
  startAnimation();

  resizeObserver?.disconnect();
  resizeObserver = new ResizeObserver(() => renderChart());
  resizeObserver.observe(chartRef.value);
  window.addEventListener("resize", renderChart);
}

function startAnimation() {
  if (animationFrameId !== null) return;
  const tick = () => {
    currentAngle += 0.25;
    if (chartInstance) {
      chartInstance.setOption(buildOption(currentAngle), { replaceMerge: ["series"] });
    }
    animationFrameId = requestAnimationFrame(tick);
  };
  animationFrameId = requestAnimationFrame(tick);
}

function stopAnimation() {
  if (animationFrameId !== null) {
    cancelAnimationFrame(animationFrameId);
    animationFrameId = null;
  }
}

function togglePlanet(id: string) {
  selectedPlanetId.value = selectedPlanetId.value === id ? null : id;
  hoveredPlanet.value = null;
}

watch(selectedPlanetId, () => {
  renderChart();
});

onMounted(async () => {
  await nextTick();
  initChart();
});

onUnmounted(() => {
  stopAnimation();
  resizeObserver?.disconnect();
  resizeObserver = null;
  window.removeEventListener("resize", renderChart);
  chartInstance?.dispose();
  chartInstance = null;
});
</script>

<template>
  <div class="solar-system-wrapper">
    <div class="chart-header">
      <div class="header-left">
        <span class="sys-tag">SOLAR SYSTEM VIEW</span>
        <h3 class="chart-title">太阳系轨道演示</h3>
        <p class="chart-sub">展示八大行星的相对轨道层级与公转关系，可点击高亮单个行星。</p>
      </div>

      <div class="header-right">
        <button
          v-for="planet in planets"
          :key="planet.id"
          class="planet-tag"
          :class="{ active: selectedPlanetId === planet.id }"
          :style="{ '--planet-color': planet.color }"
          @click="togglePlanet(planet.id)"
        >
          {{ planet.name }}
        </button>
      </div>
    </div>

    <div ref="chartRef" class="orbit-chart"></div>

    <div v-if="hoveredPlanet" class="planet-info-bar">
      <div class="info-item">
        <span class="info-label">天体</span>
        <span class="info-val">{{ hoveredPlanet.name }}</span>
      </div>
      <div class="info-item">
        <span class="info-label">类别</span>
        <span class="info-val">{{ hoveredPlanet.category }}</span>
      </div>
      <div class="info-item">
        <span class="info-label">轨道半径</span>
        <span class="info-val">{{ hoveredPlanet.orbitAu }} AU</span>
      </div>
      <div class="info-item">
        <span class="info-label">公转周期</span>
        <span class="info-val">{{ hoveredPlanet.orbitalPeriod }}</span>
      </div>
    </div>

    <div v-else class="planet-info-bar placeholder">
      <span class="hover-hint">将鼠标移动到行星上可查看简要信息，点击上方标签可聚焦单个行星。</span>
    </div>
  </div>
</template>

<style scoped>
.solar-system-wrapper {
  width: 100%;
  background: rgba(5, 10, 20, 0.62);
  border: 1px solid #1a253a;
  border-radius: 4px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 20px 24px 12px;
  border-bottom: 1px solid #1a253a;
  flex-wrap: wrap;
  gap: 12px;
}

.header-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sys-tag {
  font-family: "Space Mono", monospace;
  font-size: 10px;
  color: #13d2b8;
  letter-spacing: 1px;
}

.chart-title {
  margin: 0;
  font-size: 18px;
  color: #ffffff;
  font-weight: 700;
}

.chart-sub {
  margin: 0;
  font-size: 12px;
  color: #7f92ab;
}

.header-right {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.planet-tag {
  padding: 4px 10px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: transparent;
  color: #7f92ab;
  font-size: 11px;
  cursor: pointer;
  border-radius: 2px;
  transition: all 0.2s ease;
}

.planet-tag:hover,
.planet-tag.active {
  border-color: var(--planet-color);
  color: var(--planet-color);
  box-shadow: 0 0 8px -2px var(--planet-color);
}

.orbit-chart {
  width: 100%;
  height: 460px;
  min-height: 460px;
}

.planet-info-bar {
  display: flex;
  gap: 32px;
  padding: 12px 24px;
  border-top: 1px solid #1a253a;
  background: rgba(0, 0, 0, 0.2);
  flex-wrap: wrap;
}

.planet-info-bar.placeholder {
  align-items: center;
  min-height: 48px;
}

.hover-hint {
  font-family: "Space Mono", monospace;
  font-size: 11px;
  color: #4a5e78;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.info-label {
  font-family: "Space Mono", monospace;
  font-size: 10px;
  color: #4a5e78;
  text-transform: uppercase;
}

.info-val {
  font-size: 13px;
  color: #e2e8f0;
  font-weight: 600;
}
</style>
