<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch, nextTick } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { celestialBodies, type CelestialBody } from '../data/celestials';
import { ChevronLeft, FileText, Sparkles, Database, Orbit, Telescope, Rocket, Radar } from 'lucide-vue-next';
import * as echarts from 'echarts';

const route = useRoute();
const router = useRouter();

const currentBody = ref<CelestialBody | null>(null);
const chartRef = ref<HTMLElement | null>(null);
let chartInstance: echarts.ECharts | null = null;

const renderChart = () => {
  if (!chartRef.value || currentBody.value?.id === 'sun') return;
  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value);
  }
  
  const body = currentBody.value!;
  
  // Extract values, default to 0 if parsing fails
  const parseVal = (str: string | undefined): number => {
    if (!str) return 0;
    const match = str.match(/[\d.]+/);
    return match ? parseFloat(match[0]) : 0;
  };

  const ecc = parseVal(body.orbitData['轨道偏心率']);
  const inc = parseVal(body.orbitData['轨道倾角']);
  const dist = parseVal(body.basicData['距太阳'] || body.basicData['距地球']);
  
  // Set scale dimensions based on object type
  const maxDist = body.type === '卫星' ? 400000 : 45; // Moon distance vs solar system AU
  
  const option = {
    tooltip: {
      position: 'top',
      backgroundColor: 'rgba(10, 16, 26, 0.9)',
      borderColor: 'rgba(88, 166, 255, 0.4)',
      textStyle: { color: '#e5edf5', fontSize: 12 }
    },
    radar: {
      indicator: [
        { name: '轨道偏心率', max: 0.3 },
        { name: '轨道倾角', max: 20 },
        { name: '主星距离', max: maxDist }
      ],
      radius: '65%',
      center: ['50%', '50%'],
      splitNumber: 4,
      axisName: { color: '#8da4c2', fontSize: 11 },
      splitLine: {
        lineStyle: {
          color: [
            'rgba(255, 255, 255, 0.05)',
            'rgba(255, 255, 255, 0.1)',
            'rgba(255, 255, 255, 0.15)',
            'rgba(255, 255, 255, 0.2)'
          ].reverse()
        }
      },
      splitArea: { show: false },
      axisLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.1)' } }
    },
    series: [
      {
        name: 'Orbit Profile',
        type: 'radar',
        data: [
          {
            value: [ecc, inc, dist],
            name: body.name,
            symbol: 'circle',
            symbolSize: 6,
            itemStyle: { color: '#13d2b8' },
            areaStyle: { color: 'rgba(19, 210, 184, 0.25)' },
            lineStyle: { width: 2, color: '#13d2b8' }
          }
        ]
      }
    ]
  };
  
  chartInstance.setOption(option);
};

const handleResize = () => {
  chartInstance?.resize();
};

const timelineObserver = ref<IntersectionObserver | null>(null);

const setupObserver = () => {
  if (timelineObserver.value) {
    timelineObserver.value.disconnect();
  }
  
  timelineObserver.value = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('in-view');
      }
    });
  }, {
    threshold: 0.15,
    rootMargin: '0px 0px -60px 0px'
  });

  nextTick(() => {
    setTimeout(() => {
      document.querySelectorAll('.el-timeline-item').forEach(el => {
        el.classList.remove('in-view');
        timelineObserver.value?.observe(el);
      });
    }, 150);
  });
};

const loadData = () => {
  const id = route.params.id as string;
  const match = celestialBodies.find(c => c.id === id);
  if (match) {
    currentBody.value = match;
    window.scrollTo({ top: 0, behavior: 'smooth' });
    // setTimeout to ensure DOM updates and chartRef is bound
    setTimeout(renderChart, 100);
    // Bind timeline scroll observer
    setupObserver();
  } else {
    router.push('/');
  }
};

onMounted(() => {
  loadData();
  window.addEventListener('resize', handleResize);
});

onUnmounted(() => {
  window.removeEventListener('resize', handleResize);
  chartInstance?.dispose();
  timelineObserver.value?.disconnect();
});

watch(
  () => route.params.id,
  () => {
    loadData();
  }
);

function goHome() {
  router.push('/');
}

function goToBody(id: string) {
  router.push(`/celestial/${id}`);
}
</script>

<template>
  <div class="celestial-page" v-if="currentBody">
    <div class="hero-section" :style="{ backgroundImage: `linear-gradient(to bottom, rgba(4, 9, 18, 0.2) 0%, rgba(4, 9, 18, 0.95) 100%), url(${currentBody.heroImage})` }">
      <div class="top-nav">
        <el-button text class="back-btn" @click="goHome">
          <ChevronLeft class="back-icon" /> 返回首页
        </el-button>
      </div>
      
      <div class="hero-center">
        <h1 class="body-title">
          <span class="body-icon">{{ currentBody.icon }}</span>
          {{ currentBody.name }}
        </h1>
        <p class="body-subtitle">{{ currentBody.subtitle }}</p>
      </div>
    </div>

    <main class="content-container">
      <div class="layout-grid">
        <div class="left-col">
          <section class="info-card surface-card">
            <h3 class="card-head"><FileText class="head-icon" /> 简介</h3>
            <p class="intro-text">{{ currentBody.intro }}</p>
          </section>
          
          <section class="info-card surface-card">
            <h3 class="card-head"><Sparkles class="head-icon" /> 特征</h3>
            <ul class="feature-list">
              <li v-for="(feat, idx) in currentBody.features" :key="idx">
                <span class="bullet"></span>
                {{ feat }}
              </li>
            </ul>
          </section>

          <section class="info-card surface-card timeline-section">
            <h3 class="card-head"><Rocket class="head-icon" /> 探测历史</h3>
            <div class="timeline-container">
              <el-timeline>
                <el-timeline-item
                  v-for="(event, index) in currentBody.timeline"
                  :key="index"
                  :timestamp="event.year"
                  placement="top"
                  type="primary"
                  hollow
                >
                  <div class="event-card">
                    <h4 class="event-title">{{ event.title }}</h4>
                    <p class="event-desc">{{ event.desc }}</p>
                  </div>
                </el-timeline-item>
              </el-timeline>
            </div>
          </section>
        </div>

        <div class="right-col">
          <section class="data-card surface-card">
            <h3 class="card-head center"><Database class="head-icon" /> 基本数据</h3>
            <div class="data-list">
              <div class="data-row" v-for="(v, k) in currentBody.basicData" :key="k">
                <span class="data-key">{{ k }}</span>
                <span class="data-val">{{ v }}</span>
              </div>
            </div>
          </section>

          <section class="data-card surface-card">
            <h3 class="card-head center"><Orbit class="head-icon" /> 轨道参数</h3>
            <div class="data-list">
              <div class="data-row" v-for="(v, k) in currentBody.orbitData" :key="k">
                <span class="data-key">{{ k }}</span>
                <span class="data-val">{{ v }}</span>
              </div>
            </div>
          </section>
          
          <section class="data-card surface-card" v-if="currentBody.id !== 'sun'">
            <h3 class="card-head center"><Radar class="head-icon" /> 空间轨道画像</h3>
            <div class="chart-container" ref="chartRef"></div>
            <p class="chart-desc">基于轨道偏心率、倾角与距离的多维对比模型</p>
          </section>
        </div>
      </div>

      <section class="other-bodies surface-card">
        <h3 class="card-head"><Telescope class="head-icon" /> 其他天体</h3>
        <div class="bodies-nav">
          <button 
            v-for="body in celestialBodies.filter(b => b.id !== currentBody?.id)" 
            :key="body.id" 
            class="nav-body-btn"
            @click="goToBody(body.id)"
          >
            <span class="nav-body-icon">{{ body.icon }}</span>
            <span class="nav-body-name">{{ body.name }}</span>
          </button>
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
.celestial-page {
  min-height: 100vh;
  background-color: var(--astro-bg-main);
  color: var(--astro-text-main);
  display: flex;
  flex-direction: column;
}

.hero-section {
  position: relative;
  height: 450px;
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  border-bottom: 1px solid rgba(255,255,255,0.05);
}

.top-nav {
  position: absolute;
  top: 20px;
  left: 20px;
}

.back-btn {
  color: #c7d2e4;
  font-size: 14px;
}

.back-btn:hover {
  color: #fff;
  background: rgba(255,255,255,0.1);
}

.back-icon {
  width: 16px;
  height: 16px;
  margin-right: 4px;
}

.hero-center {
  text-align: center;
}

.body-title {
  font-size: 48px;
  margin: 0;
  color: #fff;
  letter-spacing: 2px;
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: center;
}

.body-icon {
  font-size: 42px;
  opacity: 0.9;
}

.body-subtitle {
  font-size: 18px;
  color: rgba(255, 255, 255, 0.6);
  margin: 8px 0 0;
  letter-spacing: 1px;
}

.content-container {
  max-width: 1100px;
  width: 100%;
  margin: -40px auto 60px;
  padding: 0 20px;
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.layout-grid {
  display: grid;
  grid-template-columns: 1.5fr 1fr;
  gap: 20px;
}

.left-col {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.right-col {
  display: flex;
  flex-direction: column;
  gap: 20px;
  position: sticky;
  top: 80px;
  align-self: flex-start;
  height: max-content;
}

.info-card, .data-card, .other-bodies {
  padding: 24px;
  background: rgba(10, 16, 26, 0.45);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
}

.card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  color: #e5edf5;
  margin: 0 0 16px;
  font-weight: 600;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  padding-bottom: 10px;
}

.card-head.center {
  justify-content: center;
}

.head-icon {
  width: 18px;
  height: 18px;
  stroke-width: 2px;
}

.intro-text {
  font-size: 14px;
  line-height: 1.8;
  color: #b0c4de;
  margin: 0;
}

/* Timeline Customization */
.timeline-container {
  padding: 10px 5px;
}

.event-card {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  padding: 12px 16px;
  margin-top: 5px;
  transition: all 0.4s ease;
}

.event-title {
  margin: 0 0 6px;
  font-size: 15px;
  color: #fff;
}

.event-desc {
  margin: 0;
  font-size: 13px;
  color: #8da4c2;
  line-height: 1.5;
}

/* Base states for Timeline Animation */
:deep(.el-timeline-item) {
  opacity: 0;
  transform: translateY(20px);
  transition: all 0.6s cubic-bezier(0.25, 0.8, 0.25, 1);
  filter: grayscale(80%) brightness(0.7);
}

:deep(.el-timeline-item.in-view) {
  opacity: 1;
  transform: translateY(0);
  filter: grayscale(0%) brightness(1);
}

:deep(.el-timeline-item.in-view .el-timeline-item__node) {
  box-shadow: 0 0 10px 2px rgba(88, 166, 255, 0.6);
  background-color: rgba(88, 166, 255, 0.2) !important;
}

:deep(.el-timeline-item.in-view .event-card) {
  border-color: rgba(88, 166, 255, 0.3);
  background: rgba(88, 166, 255, 0.08);
}

:deep(.el-timeline-item__timestamp) {
  color: #58a6ff;
  font-weight: bold;
  font-family: monospace;
}

:deep(.el-timeline-item__node) {
  background-color: transparent;
  border: 2px solid #58a6ff;
  transition: all 0.6s ease;
}

.feature-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.feature-list li {
  font-size: 14px;
  color: #b0c4de;
  margin-bottom: 12px;
  line-height: 1.6;
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.bullet {
  display: inline-block;
  width: 6px;
  height: 6px;
  background: #5a85dd;
  border-radius: 50%;
  margin-top: 7px;
  flex-shrink: 0;
}

.data-list {
  display: flex;
  flex-direction: column;
}

.data-row {
  display: flex;
  justify-content: space-between;
  padding: 10px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  font-size: 13px;
}

.data-row:last-child {
  border-bottom: none;
}

.data-key {
  color: #8da4c2;
}

.data-val {
  color: #fff;
  font-weight: 500;
  text-align: right;
}

.chart-container {
  width: 100%;
  height: 220px;
}

.chart-desc {
  font-size: 11px;
  color: #6e7681;
  text-align: center;
  margin: 5px 0 0;
}

.other-bodies {
  margin-top: 10px;
}

.bodies-nav {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: center;
}

.nav-body-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  background: rgba(14, 22, 34, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.1);
  padding: 12px 24px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  min-width: 90px;
}

.nav-body-btn:hover {
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(255, 255, 255, 0.25);
  transform: translateY(-2px);
}

.nav-body-icon {
  font-size: 20px;
}

.nav-body-name {
  color: #c7d2e4;
  font-size: 12px;
}

@media (max-width: 900px) {
  .layout-grid {
    grid-template-columns: 1fr;
  }
  
  .content-container {
    margin-top: -20px;
  }
}
</style>
