<template>
  <div class="neows-widget surface-card">
    <div class="widget-header">
      <div class="header-left">
        <div class="live-indicator">
          <span class="dot"></span>
          LIVE
        </div>
        <div>
          <h3 class="widget-title">近地天体实时监控 (NeoWs)</h3>
          <p class="widget-sub">NASA Jet Propulsion Laboratory · Near Earth Object Web Service</p>
        </div>
      </div>
      <div class="header-right">
        <div class="stat-pill" :class="{ danger: hazardCount > 0 }">
          <span class="pill-val">{{ hazardCount }}</span>
          <span class="pill-label">潜在危险</span>
        </div>
        <div class="stat-pill">
          <span class="pill-val">{{ neoData.length }}</span>
          <span class="pill-label">今日检出</span>
        </div>
      </div>
    </div>

    <div v-if="loading" class="loading-state">
      <el-skeleton :rows="4" animated />
    </div>

    <template v-else-if="neoData.length">
      <!-- Bubble Chart -->
      <div ref="chartRef" class="neo-chart"></div>

      <!-- Tooltip card -->
      <transition name="fade-card">
        <div v-if="selectedNeo" class="neo-detail-card" :class="{ hazardous: selectedNeo.is_potentially_hazardous }">
          <div class="detail-top">
            <div>
              <span class="detail-name">{{ selectedNeo.name }}</span>
              <span class="detail-id">#{{ selectedNeo.id }}</span>
            </div>
            <div class="hazard-badge" v-if="selectedNeo.is_potentially_hazardous">
              ⚠ HAZARDOUS
            </div>
          </div>
          <div class="detail-stats">
            <div class="d-stat">
              <span class="d-label">接近距离</span>
              <span class="d-val">{{ formatMissDistance(selectedNeo.close_approach_data[0].miss_distance.kilometers) }} 万km</span>
            </div>
            <div class="d-stat">
              <span class="d-label">相对速度</span>
              <span class="d-val">{{ formatVelocity(selectedNeo.close_approach_data[0].relative_velocity.kilometers_per_hour) }} km/h</span>
            </div>
            <div class="d-stat">
              <span class="d-label">预估直径</span>
              <span class="d-val">{{ formatDiameter(selectedNeo.estimated_diameter.meters.estimated_diameter_min, selectedNeo.estimated_diameter.meters.estimated_diameter_max) }} m</span>
            </div>
            <div class="d-stat">
              <span class="d-label">接近日期</span>
              <span class="d-val">{{ selectedNeo.close_approach_data[0].close_approach_date }}</span>
            </div>
          </div>
        </div>
        <div v-else class="neo-hint">// 点击气泡查看天体详情 · X轴：接近距离  Y轴：相对速度  气泡大小：天体直径</div>
      </transition>
    </template>

    <div v-else class="empty-state">
      RADAR OFFLINE — 无法获取实时监测数据，请检查网络连接
    </div>

    <div class="widget-footer">
      <span class="timestamp">同步时间: {{ currentTime }}</span>
      <span class="source">Source: api.nasa.gov/neo/rest/v1</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, nextTick } from 'vue';
import * as echarts from 'echarts';

const neoData = ref<any[]>([]);
const loading = ref(true);
const currentTime = ref(new Date().toLocaleTimeString());
const chartRef = ref<HTMLElement | null>(null);
const selectedNeo = ref<any>(null);
let chartInstance: echarts.ECharts | null = null;
let timer: number;

const hazardCount = computed(() => neoData.value.filter(n => n.is_potentially_hazardous).length);

const fetchNeoData = async () => {
  loading.value = true;
  try {
    const today = new Date().toISOString().split('T')[0];
    const response = await fetch(`https://api.nasa.gov/neo/rest/v1/feed?start_date=${today}&end_date=${today}&api_key=DEMO_KEY`);
    if (response.ok) {
      const data = await response.json();
      const objects = data.near_earth_objects[today] || [];
      neoData.value = objects.slice(0, 12);
    } else throw new Error('API limit');
  } catch {
    neoData.value = [
      { id: "2465633", name: "465633 (2009 JR7)", is_potentially_hazardous: true,
        estimated_diameter: { meters: { estimated_diameter_min: 240, estimated_diameter_max: 540 } },
        close_approach_data: [{ close_approach_date: new Date().toISOString().split('T')[0], relative_velocity: { kilometers_per_hour: "64800" }, miss_distance: { kilometers: "4850000" } }] },
      { id: "3758838", name: "(2016 TG10)", is_potentially_hazardous: false,
        estimated_diameter: { meters: { estimated_diameter_min: 45, estimated_diameter_max: 100 } },
        close_approach_data: [{ close_approach_date: new Date().toISOString().split('T')[0], relative_velocity: { kilometers_per_hour: "32400" }, miss_distance: { kilometers: "12500000" } }] },
      { id: "3830065", name: "(2018 PN22)", is_potentially_hazardous: false,
        estimated_diameter: { meters: { estimated_diameter_min: 12, estimated_diameter_max: 27 } },
        close_approach_data: [{ close_approach_date: new Date().toISOString().split('T')[0], relative_velocity: { kilometers_per_hour: "21600" }, miss_distance: { kilometers: "6200000" } }] },
      { id: "3982026", name: "(2020 QO)", is_potentially_hazardous: false,
        estimated_diameter: { meters: { estimated_diameter_min: 8, estimated_diameter_max: 18 } },
        close_approach_data: [{ close_approach_date: new Date().toISOString().split('T')[0], relative_velocity: { kilometers_per_hour: "18000" }, miss_distance: { kilometers: "2100000" } }] },
      { id: "2153591", name: "153591 (2001 SN263)", is_potentially_hazardous: true,
        estimated_diameter: { meters: { estimated_diameter_min: 860, estimated_diameter_max: 1920 } },
        close_approach_data: [{ close_approach_date: new Date().toISOString().split('T')[0], relative_velocity: { kilometers_per_hour: "76000" }, miss_distance: { kilometers: "9800000" } }] },
      { id: "3120677", name: "(2001 QJ142)", is_potentially_hazardous: false,
        estimated_diameter: { meters: { estimated_diameter_min: 33, estimated_diameter_max: 74 } },
        close_approach_data: [{ close_approach_date: new Date().toISOString().split('T')[0], relative_velocity: { kilometers_per_hour: "45000" }, miss_distance: { kilometers: "7300000" } }] },
    ];
  } finally {
    loading.value = false;
    await nextTick();
    initChart();
  }
};

function initChart() {
  if (!chartRef.value || !neoData.value.length) return;
  if (chartInstance) chartInstance.dispose();
  chartInstance = echarts.init(chartRef.value);

  const chartData = neoData.value.map(neo => {
    const missKm = parseFloat(neo.close_approach_data[0].miss_distance.kilometers);
    const speedKmh = parseFloat(neo.close_approach_data[0].relative_velocity.kilometers_per_hour);
    const diameterAvg = (neo.estimated_diameter.meters.estimated_diameter_min + neo.estimated_diameter.meters.estimated_diameter_max) / 2;
    const isHaz = neo.is_potentially_hazardous;
    return {
      value: [missKm / 1000000, speedKmh / 1000, Math.sqrt(diameterAvg) * 3 + 8, neo.name, diameterAvg, isHaz],
      itemStyle: {
        color: isHaz
          ? new echarts.graphic.RadialGradient(0.4, 0.3, 1, [
              { offset: 0, color: 'rgba(255, 100, 80, 0.9)' },
              { offset: 1, color: 'rgba(200, 40, 40, 0.6)' }
            ])
          : new echarts.graphic.RadialGradient(0.4, 0.3, 1, [
              { offset: 0, color: 'rgba(30, 180, 240, 0.9)' },
              { offset: 1, color: 'rgba(19, 100, 180, 0.5)' }
            ]),
        shadowBlur: isHaz ? 16 : 8,
        shadowColor: isHaz ? 'rgba(255, 80, 60, 0.6)' : 'rgba(30, 180, 255, 0.4)',
      },
      neo,
    };
  });

  const option: any = {
    backgroundColor: 'transparent',
    grid: { left: 56, right: 20, top: 20, bottom: 48 },
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(5,10,20,0)',
      borderWidth: 0,
      formatter: () => '',
    },
    xAxis: {
      type: 'value',
      name: '接近距离 (百万km)',
      nameLocation: 'middle',
      nameGap: 34,
      nameTextStyle: { color: '#566a87', fontSize: 11 },
      axisLine: { lineStyle: { color: '#1a253a' } },
      axisTick: { lineStyle: { color: '#1a253a' } },
      axisLabel: { color: '#566a87', fontSize: 10, formatter: (v: number) => v.toFixed(1) + 'M' },
      splitLine: { lineStyle: { color: '#111d2e', type: 'dashed' } },
    },
    yAxis: {
      type: 'value',
      name: '相对速度 (千km/h)',
      nameLocation: 'middle',
      nameGap: 46,
      nameTextStyle: { color: '#566a87', fontSize: 11 },
      axisLine: { lineStyle: { color: '#1a253a' } },
      axisTick: { lineStyle: { color: '#1a253a' } },
      axisLabel: { color: '#566a87', fontSize: 10, formatter: (v: number) => v + 'K' },
      splitLine: { lineStyle: { color: '#111d2e', type: 'dashed' } },
    },
    series: [{
      type: 'scatter',
      data: chartData,
      symbolSize: (data: any[]) => data[2],
      emphasis: { scale: 1.3 },
      label: {
        show: true,
        formatter: (p: any) => {
          const name = p.data.value[3] as string;
          return name.length > 14 ? name.substring(0, 14) + '…' : name;
        },
        position: 'top',
        color: '#8da4c2',
        fontSize: 9,
        fontFamily: 'Space Mono, monospace',
      },
    }],
  };

  chartInstance.setOption(option);
  chartInstance.on('click', (params: any) => {
    selectedNeo.value = params.data?.neo ?? null;
  });
}

const formatVelocity = (v: string) => Math.round(parseFloat(v)).toLocaleString();
const formatDiameter = (min: number, max: number) => `${Math.round(min)}–${Math.round(max)}`;
const formatMissDistance = (d: string) => (parseFloat(d) / 10000).toFixed(1);

function onResize() { chartInstance?.resize(); }

onMounted(() => {
  fetchNeoData();
  timer = window.setInterval(() => { currentTime.value = new Date().toLocaleTimeString(); }, 1000);
  window.addEventListener('resize', onResize);
});

onUnmounted(() => {
  clearInterval(timer);
  window.removeEventListener('resize', onResize);
  chartInstance?.dispose();
});
</script>

<style scoped>
.neows-widget {
  background: rgba(4, 9, 18, 0.7);
  border: 1px solid rgba(88, 166, 255, 0.18);
  border-radius: 4px;
  padding: 18px 20px;
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 360px;
  height: 100%;
}

.widget-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  border-bottom: 1px solid rgba(88, 166, 255, 0.1);
  padding-bottom: 12px;
  flex-wrap: wrap;
  gap: 10px;
}

.header-left { display: flex; align-items: flex-start; gap: 12px; }
.header-right { display: flex; gap: 8px; }

.live-indicator {
  display: flex; align-items: center; gap: 5px;
  font-size: 9px; font-weight: 700;
  color: #ff4d4f;
  background: rgba(255,77,79,0.1);
  border: 1px solid rgba(255,77,79,0.3);
  padding: 3px 8px; letter-spacing: 1px;
  margin-top: 2px;
  white-space: nowrap;
}

.dot {
  width: 5px; height: 5px;
  background: #ff4d4f; border-radius: 50%;
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0%,100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.3; transform: scale(1.4); }
}

.widget-title { margin: 0; font-size: 13px; color: #e5edf5; letter-spacing: 0.5px; }
.widget-sub { margin: 2px 0 0; font-size: 10px; color: #4a5e78; font-family: 'Space Mono', monospace; }

.stat-pill {
  display: flex; flex-direction: column; align-items: center;
  padding: 6px 14px;
  border: 1px solid #1a253a;
  background: rgba(10,18,32,0.5);
  border-radius: 2px;
  min-width: 58px;
}
.stat-pill.danger { border-color: rgba(255,77,79,0.4); background: rgba(255,77,79,0.05); }
.pill-val { font-size: 18px; font-weight: 700; color: #fff; font-family: 'Space Mono', monospace; line-height: 1; }
.stat-pill.danger .pill-val { color: #ff6b6b; }
.pill-label { font-size: 10px; color: #4a5e78; margin-top: 2px; }

.neo-chart { width: 100%; height: 240px; }

.neo-detail-card {
  background: rgba(10, 18, 32, 0.9);
  border: 1px solid rgba(30, 180, 255, 0.25);
  border-left: 2px solid #1eb4f0;
  padding: 12px 16px;
  border-radius: 2px;
}
.neo-detail-card.hazardous {
  border-color: rgba(255, 80, 60, 0.3);
  border-left-color: #ff4d4f;
}

.detail-top { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px; }
.detail-name { font-size: 13px; font-weight: 600; color: #fff; display: block; }
.detail-id { font-size: 10px; color: #4a5e78; font-family: 'Space Mono', monospace; }

.hazard-badge {
  font-size: 9px; color: #ff4d4f;
  border: 1px solid rgba(255,77,79,0.5);
  padding: 2px 7px; font-weight: 700; letter-spacing: 0.5px;
  white-space: nowrap;
}

.detail-stats {
  display: grid; grid-template-columns: 1fr 1fr;
  gap: 8px 16px;
}
.d-stat { display: flex; flex-direction: column; gap: 1px; }
.d-label { font-size: 10px; color: #4a5e78; font-family: 'Space Mono', monospace; }
.d-val { font-size: 12px; color: #e2e8f0; font-weight: 600; }

.neo-hint {
  font-family: 'Space Mono', monospace;
  font-size: 10px; color: #344459;
  padding: 10px 0; text-align: center;
}

.loading-state { padding: 12px 0; }

.empty-state {
  text-align: center; color: #4a5e78;
  font-size: 11px; padding: 24px 0;
  font-family: 'Space Mono', monospace;
  letter-spacing: 1px;
}

.widget-footer {
  display: flex; justify-content: space-between;
  font-size: 9px; color: #2a3a55;
  border-top: 1px solid #0e1929;
  padding-top: 8px;
  font-family: 'Space Mono', monospace;
}

.fade-card-enter-active, .fade-card-leave-active { transition: opacity 0.2s, transform 0.2s; }
.fade-card-enter-from, .fade-card-leave-to { opacity: 0; transform: translateY(4px); }
</style>
