<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import { celestialBodies } from "../data/celestials";
import { getGraphStatus, getLandingApod, getLandingFrontier, getLandingNews } from "../api";

import landingBg from "../assets/landing-bg.png";

const ThreeUniverse = defineAsyncComponent(() => import("../components/ThreeUniverse.vue"));
const NeoWsWidget = defineAsyncComponent(() => import("../components/NeoWsWidget.vue"));
const AladinPlanetarium = defineAsyncComponent(() => import("../components/AladinPlanetarium.vue"));
const SolarSystemChart = defineAsyncComponent(() => import("../components/SolarSystemChart.vue"));

const solarVisible = ref(false);
const aladinVisible = ref(false);
const solarRef = ref<HTMLElement | null>(null);
const aladinRef = ref<HTMLElement | null>(null);
let solarObserver: IntersectionObserver | null = null;
let aladinObserver: IntersectionObserver | null = null;
const APOD_FALLBACK_IMAGE = "https://images.unsplash.com/photo-1462331940025-496dfbfc7564?q=80&w=2574&auto=format&fit=crop";

type NewsItem = {
  title: string;
  url: string;
  image_url: string;
  source: string;
  summary: string;
  date: string;
};

type ScienceCard = {
  name: string;
  type: string;
  image_url: string;
  desc: string;
  facts: Record<string, string>;
  url: string;
};

type FrontierPaper = {
  title: string;
  url: string;
  date: string;
  summary: string;
  journal_ref?: string;
  category?: string;
  source?: string;
  authors?: string[];
};

type FrontierTopic = {
  key: string;
  label: string;
  items: FrontierPaper[];
};

const router = useRouter();
const exploreInput = ref("木星为什么会有这么多卫星？");
const apodData = ref<any>(null);
const newsItems = ref<NewsItem[]>([]);
const scienceCards = ref<ScienceCard[]>([]);
const frontierTopics = ref<FrontierTopic[]>([]);
const landingLoading = ref(false);

// Stats counter
const statsDisplayed = ref({ nodes: 0, bodies: 0, timelines: 0, papers: 0 });
const statsTarget = ref({ nodes: 0, bodies: celestialBodies.length, timelines: 0, papers: 0 });

const frontierPage = ref(1);
const frontierPageSize = 3;
const frontierPageCount = ref(5);

let refreshTimer: number | null = null;
let statsTimer: number | null = null;

const frontierColumns = computed(() =>
  frontierTopics.value.map((topic) => {
    const start = (frontierPage.value - 1) * frontierPageSize;
    const end = start + frontierPageSize;
    return {
      ...topic,
      pageItems: (topic.items || []).slice(start, end),
    };
  })
);

function goExplore() {
  const hasToken = Boolean(localStorage.getItem("astro_access_token") || localStorage.getItem("astro_token"));
  if (hasToken) {
    router.push("/app/qa");
    return;
  }
  router.push({ path: "/login", query: { redirect: "/app/qa" } });
}

function goLogin() {
  router.push({ path: "/login", query: { redirect: "/app/qa" } });
}

function goRegister() {
  router.push({ path: "/register", query: { redirect: "/app/qa" } });
}

function goExploreWithQuestion() {
  const q = exploreInput.value.trim();
  if (!q) {
    goExplore();
    return;
  }
  const target = { path: "/app/qa", query: { q, auto: "1" } };
  const hasToken = Boolean(localStorage.getItem("astro_access_token") || localStorage.getItem("astro_token"));
  if (hasToken) {
    router.push(target);
    return;
  }
  router.push({
    path: "/login",
    query: { redirect: `/app/qa?q=${encodeURIComponent(q)}&auto=1` },
  });
}

function resolveApodImage(item: any): string {
  if (!item || typeof item !== "object") return APOD_FALLBACK_IMAGE;
  const hd = String(item.hdurl || "").trim();
  const url = String(item.url || "").trim();
  const thumb = String(item.thumbnail_url || "").trim();
  if (item.media_type === "image") {
    return hd || url || thumb || APOD_FALLBACK_IMAGE;
  }
  return thumb || hd || url || APOD_FALLBACK_IMAGE;
}

function countUpStats() {
  if (statsTimer) clearInterval(statsTimer);
  const duration = 1800;
  const steps = 60;
  const interval = duration / steps;
  let step = 0;
  statsTimer = window.setInterval(() => {
    step++;
    const progress = Math.min(step / steps, 1);
    const ease = 1 - Math.pow(1 - progress, 3);
    statsDisplayed.value = {
      nodes: Math.round(statsTarget.value.nodes * ease),
      bodies: Math.round(statsTarget.value.bodies * ease),
      timelines: Math.round(statsTarget.value.timelines * ease),
      papers: Math.round(statsTarget.value.papers * ease),
    };
    if (step >= steps) clearInterval(statsTimer!);
  }, interval);
}

async function loadLandingData() {
  landingLoading.value = true;
  try {
    const [apod, newsRes, frontierRes] = await Promise.all([
      getLandingApod().catch((e) => {
        console.warn("APOD load failed", e);
        return null;
      }),
      getLandingNews(6).catch(() => ({ items: [] })),
      getLandingFrontier(18).catch(() => ({ topics: [] })),
    ]);

    apodData.value = apod;
    if (!apodData.value) {
      apodData.value = {
        title: "星空（离线预览）",
        date: new Date().toISOString().split("T")[0],
        explanation: "暂时无法从后端获取 NASA APOD，请确认后端已启动并可访问外网。",
        media_type: "image",
        url: "https://images.unsplash.com/photo-1462331940025-496dfbfc7564?q=80&w=2574&auto=format&fit=crop",
        hdurl: "https://images.unsplash.com/photo-1462331940025-496dfbfc7564?q=80&w=2574&auto=format&fit=crop",
      };
    }

    newsItems.value = Array.isArray(newsRes?.items) ? newsRes.items : [];

    const topics = Array.isArray(frontierRes?.topics) ? frontierRes.topics : [];
    frontierTopics.value = topics.map((t: Record<string, unknown>) => ({
      key: String(t.key ?? ""),
      label: String(t.label ?? ""),
      items: Array.isArray(t.items) ? (t.items as FrontierPaper[]) : [],
    }));

    const lens = frontierTopics.value.map((t) => t.items.length);
    const maxLen = lens.length ? Math.max(...lens) : 0;
    frontierPageCount.value = Math.max(1, Math.ceil(maxLen / frontierPageSize));

    scienceCards.value = celestialBodies.map((body) => ({
      name: body.name,
      type: body.type,
      image_url: body.gridImage,
      desc: body.desc,
      facts: body.basicData,
      url: `/celestial/${body.id}`,
    }));

    try {
      const graphStatus = await getGraphStatus();
      statsTarget.value.nodes = Number(graphStatus?.nodes_count ?? 0);
    } catch {
      statsTarget.value.nodes = 0;
    }
    statsTarget.value.timelines = celestialBodies.reduce((s, b) => s + (b.timeline?.length || 0), 0);
    statsTarget.value.papers = frontierTopics.value.reduce((s, t) => s + t.items.length, 0);
    countUpStats();
  } finally {
    landingLoading.value = false;
  }
}

onMounted(() => {
  loadLandingData();
  refreshTimer = window.setInterval(() => {
    loadLandingData();
  }, 4 * 60 * 1000);

  const observerOptions = { rootMargin: "200px", threshold: 0.01 };
  solarObserver = new IntersectionObserver(([entry]) => {
    if (entry.isIntersecting) {
      solarVisible.value = true;
      solarObserver?.disconnect();
    }
  }, observerOptions);
  aladinObserver = new IntersectionObserver(([entry]) => {
    if (entry.isIntersecting) {
      aladinVisible.value = true;
      aladinObserver?.disconnect();
    }
  }, observerOptions);
  if (solarRef.value) solarObserver.observe(solarRef.value);
  if (aladinRef.value) aladinObserver.observe(aladinRef.value);
});

onUnmounted(() => {
  if (refreshTimer) { window.clearInterval(refreshTimer); refreshTimer = null; }
  if (statsTimer) { window.clearInterval(statsTimer); statsTimer = null; }
  solarObserver?.disconnect();
  aladinObserver?.disconnect();
});
</script>

<template>
  <div
    class="landing-page"
    :style="{
      backgroundImage: `linear-gradient(rgba(4, 9, 18, 0.72), rgba(4, 9, 18, 0.78)), url(${landingBg})`
    }"
  >
    <ThreeUniverse />
    
    <nav class="navbar relative-z">
      <div class="logo">
        <p class="brand-main">ASTRO</p>
        <p class="brand-sub">多模态天文科普探索系统</p>
      </div>
      <div class="nav-cta">
        <el-button text @click="goLogin">登录</el-button>
        <el-button text @click="goRegister">注册</el-button>
        <el-button type="primary" plain @click="goExplore">进入工作台</el-button>
      </div>
    </nav>

    <main class="main-content relative-z">
      <header class="hero">
        <p class="hero-kicker"><span class="kicker-dot"></span> 2026 China Computer Design Contest 路 Information Visualization Track</p>
        <h1>让天文问题，变成一段 <br/><span class="h1-accent">可视化探索旅程</span></h1>
        <p class="hero-desc">
          面向天文科普的多模态智能平台，融合知识图谱、GraphRAG推理、三维星图与实时天文数据，
          连接从「一问」到「深空探索」的完整认知链路。
        </p>
        <div class="hero-search">
          <el-input
            v-model="exploreInput"
            size="large"
            placeholder="输入一个天文问题，直接开始探索"
            @keyup.enter="goExploreWithQuestion"
          />
          <el-button type="primary" size="large" @click="goExploreWithQuestion">立即提问</el-button>
        </div>
      </header>

      <!-- Stats Counter Bar -->
      <div class="stats-bar">
        <div class="stat-item">
          <span class="stat-num">{{ statsDisplayed.nodes.toLocaleString() }}</span>
          <span class="stat-label">知识图谱节点</span>
          <span class="stat-desc">天体关系实体</span>
        </div>
        <div class="stat-divider"></div>
        <div class="stat-item">
          <span class="stat-num">{{ statsDisplayed.bodies }}</span>
          <span class="stat-label">天体科普档案</span>
          <span class="stat-desc">可交互详情页</span>
        </div>
        <div class="stat-divider"></div>
        <div class="stat-item">
          <span class="stat-num">{{ statsDisplayed.timelines }}</span>
          <span class="stat-label">探测历史节点</span>
          <span class="stat-desc">人类深空探索编年</span>
        </div>
        <div class="stat-divider"></div>
        <div class="stat-item">
          <span class="stat-num">{{ statsDisplayed.papers }}</span>
          <span class="stat-label">arXiv 前沿论文</span>
          <span class="stat-desc">实时天文学文献</span>
        </div>
      </div>

      <section class="apod-neows-row">
        <div class="apod-section" v-if="apodData">
          <div class="apod-card surface-card">
            <div class="apod-img-box">
              <img
                :src="resolveApodImage(apodData)"
                :alt="apodData.title"
                class="apod-img"
                loading="lazy"
                referrerpolicy="no-referrer"
              />
            </div>
            <div class="apod-info">
              <div class="apod-tag">NASA 每日星图 <span>(APOD)</span></div>
              <h3 class="apod-title">{{ apodData.title }}</h3>
              <p class="apod-date">{{ apodData.date }}</p>
              <p class="apod-desc">{{ apodData.explanation }}</p>
            </div>
          </div>
        </div>
        <div class="neows-col">
          <NeoWsWidget />
        </div>
      </section>

      <section class="news-section">
        <div class="section-head center">
          <p class="section-title xl">近期时讯</p>
        </div>
        <el-carousel
          v-if="newsItems.length"
          class="news-carousel"
          height="420px"
          indicator-position="outside"
          arrow="always"
          :interval="5000"
          :autoplay="true"
        >
          <el-carousel-item v-for="(news, idx) in newsItems" :key="`${news.url}-${idx}`">
            <a
              class="news-slide"
              :href="news.url"
              target="_blank"
              rel="noopener noreferrer"
              :style="{
                backgroundImage: `linear-gradient(180deg, rgba(3,8,16,0.2) 0%, rgba(3,8,16,0.85) 80%), url(${news.image_url})`
              }"
            >
              <span class="news-date">{{ news.date }}</span>
              <div class="news-content">
                <p class="news-source">{{ news.source }}</p>
                <h3>{{ news.title }}</h3>
                <p class="news-summary">{{ news.summary }}</p>
              </div>
            </a>
          </el-carousel-item>
        </el-carousel>
        <el-skeleton v-else :rows="8" animated />
      </section>

      <section class="science-cards-section">
        <div class="section-head center">
          <span class="section-badge">CELESTIAL ARCHIVE</span>
          <p class="section-title xl">天体科普档案</p>
          <p class="section-subtitle">点击卡片进入详情，探索真实轨道数据与探测历史</p>
        </div>
        <div class="cards-grid">
          <article v-for="card in scienceCards" :key="card.name" class="science-card">
            <div class="card-inner">
              <!-- Front -->
              <div class="card-front">
                <div class="card-image-wrap">
                  <img :src="card.image_url" :alt="card.name" class="card-image" loading="lazy" />
                  <span class="card-type">{{ card.type }}</span>
                </div>
                <div class="card-body">
                  <h4 class="card-title">{{ card.name }}</h4>
                  <p class="card-desc">{{ card.desc }}</p>
                  <div class="card-facts">
                    <div v-for="(value, key) in card.facts" :key="`${card.name}-${key}`" class="fact-item">
                      <span class="fact-key">{{ key }}</span>
                      <span class="fact-value">{{ value }}</span>
                    </div>
                  </div>
                  <router-link :to="card.url" class="card-link">查看详情 →</router-link>
                </div>
              </div>
              <!-- Back -->
              <div class="card-back">
                <p class="back-type">{{ card.type }}</p>
                <h3 class="back-name">{{ card.name }}</h3>
                <div class="back-facts">
                  <div v-for="(value, key) in card.facts" :key="`back-${card.name}-${key}`" class="back-fact-row">
                    <span class="back-key">{{ key }}</span>
                    <span class="back-val">{{ value }}</span>
                  </div>
                </div>
                <router-link :to="card.url" class="back-cta">深入探索</router-link>
              </div>
            </div>
          </article>
        </div>
      </section>

      <!-- Solar System Orbital Visualization -->
      <section ref="solarRef" class="solar-section">
        <div class="section-head center">
          <span class="section-badge">ORBITAL MECHANICS</span>
          <p class="section-title xl">太阳系实时轨道图</p>
          <p class="section-subtitle">基于真实轨道参数 · 对数缩放坐标系 · 点击行星标签聚焦单一轨道</p>
        </div>
        <SolarSystemChart v-if="solarVisible" />
        <div v-else class="lazy-placeholder">滚动到此处加载轨道图</div>
      </section>

      <section class="frontier-section">
        <div class="section-head center">
          <span class="section-badge">arXiv LIVE FEED</span>
          <p class="section-title xl">前沿天文文献</p>
          <p class="section-subtitle">实时拉取 arXiv 最新论文 · 每次加载均为真实更新</p>
        </div>
        <div class="frontier-grid">
          <section
            v-for="topic in frontierColumns"
            :key="topic.key"
            class="frontier-col surface-card"
          >
            <h4 class="frontier-col-title">{{ topic.label }}</h4>
            <div v-if="topic.pageItems.length" class="paper-list">
              <a
                v-for="paper in topic.pageItems"
                :key="paper.url"
                :href="paper.url"
                target="_blank"
                rel="noopener noreferrer"
                class="paper-item"
              >
                <p class="paper-title">{{ paper.title }}</p>
                <p class="paper-meta">
                  <span>{{ paper.date }}</span>
                  <span>{{ paper.source || "arXiv" }}</span>
                </p>
                <p v-if="paper.authors && paper.authors.length" class="paper-authors">{{ paper.authors.join(', ') }}</p>
                <p class="paper-summary">{{ paper.summary }}</p>
              </a>
            </div>
            <div v-else class="paper-empty">当前页暂无数据</div>
          </section>
        </div>

        <div class="frontier-pagination">
          <el-pagination
            background
            layout="prev, pager, next"
            :page-count="frontierPageCount"
            v-model:current-page="frontierPage"
          />
        </div>
      </section>
      <section ref="aladinRef" class="aladin-section">
        <div class="section-head center">
          <span class="section-badge">ALADIN LITE</span>
          <p class="section-title xl">深空天图探索</p>
          <p class="section-subtitle">由 Centre de Données astronomiques de Strasbourg 提供，支持真实天文巡天数据探索</p>
        </div>
        <AladinPlanetarium v-if="aladinVisible" />
        <div v-else class="lazy-placeholder">滚动到此处加载天图</div>
      </section>
    </main>
  </div>
</template>

<style scoped>
.relative-z {
  position: relative;
  z-index: 10;
  pointer-events: auto;
}

.landing-page {
  min-height: 100vh;
  padding: 16px;
  display: flex;
  flex-direction: column;
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
  overflow-y: auto;
  position: relative;
}

.navbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 4px;
}

.brand-main {
  margin: 0;
  font-size: 20px;
  letter-spacing: 1px;
  font-weight: 700;
  color: #fff;
  pointer-events: auto;
}

.brand-sub {
  margin: 4px 0 0;
  color: var(--astro-text-secondary);
  font-size: 12px;
}

.nav-cta {
  display: flex;
  align-items: center;
  gap: 8px;
  pointer-events: auto;
}

.main-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 36px;
  max-width: 1180px;
  margin: 0 auto;
  width: 100%;
  padding-bottom: 64px;
}

.hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  margin-top: 140px; /* adjusted to account for canvas */
  margin-bottom: 60px; /* adjusted */
  pointer-events: auto;
}

.hero-kicker {
  margin: 0 0 12px;
  color: var(--astro-primary);
  font-size: 13px;
  letter-spacing: 1.6px;
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: center;
  font-family: 'Space Mono', monospace;
}

.kicker-dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--astro-primary);
  box-shadow: 0 0 8px var(--astro-primary);
  animation: kicker-pulse 2s infinite;
}

@keyframes kicker-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(1.3); }
}

.h1-accent {
  background: linear-gradient(135deg, var(--astro-primary), #5eb8ff);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

h1 {
  margin: 0 0 16px;
  font-size: 64px;
  line-height: 1.05;
  letter-spacing: 2px;
  pointer-events: auto;
}

.hero-desc {
  color: #c7d2e4;
  line-height: 1.75;
  font-size: 16px;
  max-width: 760px;
  margin-bottom: 28px;
  pointer-events: auto;
}

.hero-actions {
  display: flex;
  gap: 16px;
  justify-content: center;
  flex-wrap: wrap;
  pointer-events: auto;
}

.hero-search {
  width: min(760px, 100%);
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
  margin-bottom: 18px;
  pointer-events: auto;
}

.news-section,
.science-cards-section,
.frontier-section,
.solar-section,
.aladin-section {
  width: 100%;
  pointer-events: auto;
}

.section-head.center {
  text-align: center;
  margin-bottom: 20px;
}

.section-badge {
  display: inline-block;
  font-family: 'Space Mono', monospace;
  font-size: 10px;
  color: var(--astro-primary);
  border: 1px solid rgba(19, 210, 184, 0.3);
  padding: 3px 10px;
  letter-spacing: 1.5px;
  margin-bottom: 10px;
  background: rgba(19, 210, 184, 0.04);
}

.section-subtitle {
  margin: 6px 0 0;
  font-size: 13px;
  color: #566a87;
  font-family: 'Space Mono', monospace;
}

.section-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
}

.section-title.xl {
  font-size: 36px;
  letter-spacing: 1px;
}

/* Stats Bar */
.stats-bar {
  display: flex;
  align-items: stretch;
  gap: 0;
  border: 1px solid rgba(19, 210, 184, 0.2);
  background: rgba(5, 10, 20, 0.7);
  width: 100%;
  pointer-events: auto;
  overflow: hidden;
}

.stat-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px 12px;
  gap: 4px;
  position: relative;
}

.stat-item::before {
  content: '';
  position: absolute;
  bottom: 0;
  left: 20%;
  width: 60%;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--astro-primary), transparent);
  opacity: 0;
  transition: opacity 0.3s;
}

.stat-item:hover::before {
  opacity: 1;
}

.stat-num {
  font-family: 'Space Mono', monospace;
  font-size: 32px;
  font-weight: 700;
  color: var(--astro-primary);
  line-height: 1;
}

.stat-label {
  font-size: 13px;
  color: #e2e8f0;
  font-weight: 600;
}

.stat-desc {
  font-size: 11px;
  color: #4a5e78;
  font-family: 'Space Mono', monospace;
}

.stat-divider {
  width: 1px;
  background: rgba(19, 210, 184, 0.15);
  align-self: stretch;
}

.news-carousel {
  width: 100%;
}

.news-slide {
  position: relative;
  display: block;
  width: 100%;
  height: 420px;
  border: 1px solid var(--astro-border);
  border-radius: 12px;
  overflow: hidden;
  background-size: cover;
  background-position: center;
  text-decoration: none;
}

.news-date {
  position: absolute;
  top: 14px;
  left: 14px;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(8, 16, 30, 0.78);
  border: 1px solid rgba(208, 169, 108, 0.45);
  color: #f7d9a8;
  font-size: 12px;
  z-index: 2;
}

.news-content {
  position: absolute;
  left: 28px;
  right: 28px;
  bottom: 24px;
  z-index: 2;
}

.news-source {
  margin: 0 0 8px;
  color: #f1cd92;
  font-size: 13px;
}

.news-content h3 {
  margin: 0 0 10px;
  color: #f3f6ff;
  font-size: 38px;
  line-height: 1.14;
}

.news-summary {
  margin: 0;
  color: #c7d2e4;
  font-size: 15px;
  line-height: 1.55;
  max-width: 760px;
}

.cards-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}

/* 3D Flip Card */
.science-card {
  perspective: 1000px;
  cursor: pointer;
  pointer-events: auto;
  height: 460px;
}

.card-inner {
  position: relative;
  width: 100%;
  height: 100%;
  transform-style: preserve-3d;
  transition: transform 0.55s cubic-bezier(0.4, 0, 0.2, 1);
}

.science-card:hover .card-inner {
  transform: rotateY(180deg);
}

.card-front,
.card-back {
  position: absolute;
  inset: 0;
  backface-visibility: hidden;
  overflow: hidden;
}

.card-front {
  background: rgba(9, 15, 26, 0.85);
  border: 1px solid var(--astro-border);
  display: flex;
  flex-direction: column;
}

.card-back {
  background: rgba(5, 12, 24, 0.97);
  border: 1px solid rgba(19, 210, 184, 0.4);
  transform: rotateY(180deg);
  display: flex;
  flex-direction: column;
  padding: 20px;
  gap: 10px;
  box-shadow: inset 0 0 40px rgba(19, 210, 184, 0.04);
}

.back-type {
  margin: 0;
  font-family: 'Space Mono', monospace;
  font-size: 10px;
  color: var(--astro-primary);
  letter-spacing: 1px;
  border: 1px solid rgba(19, 210, 184, 0.3);
  padding: 2px 8px;
  display: inline-block;
  width: fit-content;
}

.back-name {
  margin: 0;
  font-size: 26px;
  color: #fff;
  font-weight: 700;
}

.back-facts {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow: hidden;
}

.back-fact-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  border-bottom: 1px solid #131f32;
  padding-bottom: 5px;
  gap: 8px;
}

.back-key {
  font-size: 10px;
  color: #4a5e78;
  font-family: 'Space Mono', monospace;
  white-space: nowrap;
}

.back-val {
  font-size: 12px;
  color: #c8d8ee;
  text-align: right;
  flex-shrink: 0;
}

.back-cta {
  display: block;
  width: 100%;
  text-align: center;
  padding: 10px;
  background: rgba(19, 210, 184, 0.08);
  border: 1px solid rgba(19, 210, 184, 0.35);
  color: var(--astro-primary);
  text-decoration: none;
  font-size: 13px;
  font-weight: 600;
  transition: background 0.2s;
}

.back-cta:hover {
  background: rgba(19, 210, 184, 0.18);
}

.card-image-wrap {
  position: relative;
  display: block;
  height: 180px;
  overflow: hidden;
}

.card-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.card-type {
  position: absolute;
  top: 10px;
  left: 10px;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(5, 12, 22, 0.85);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: #e8eef9;
  font-size: 11px;
}

.card-body {
  padding: 10px;
}

.card-title {
  margin: 0;
  font-size: 24px;
  color: #f0f4ff;
}

.card-desc {
  margin: 6px 0 10px;
  font-size: 13px;
  line-height: 1.55;
  color: #b8c5da;
}

.card-facts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}

.fact-item {
  background: rgba(10, 18, 32, 0.8);
  border: 1px solid #263651;
  border-radius: 8px;
  padding: 7px 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.fact-key {
  font-size: 11px;
  color: #95a6c0;
}

.fact-value {
  font-size: 13px;
  color: #eff4ff;
}

.card-link {
  margin-top: 10px;
  display: inline-flex;
  text-decoration: none;
  font-size: 12px;
  color: #d7e3ff;
  border: 1px solid #2b3d5d;
  border-radius: 999px;
  padding: 6px 11px;
  pointer-events: auto;
}

.card-link:hover {
  border-color: #d0a96c;
  color: #f1d2a3;
}

.frontier-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  width: 100%;
  box-sizing: border-box;
  padding: 0 4px;
}

.frontier-col {
  border: 1px solid var(--astro-border);
  background: rgba(9, 15, 24, 0.62);
  padding: 12px;
  min-height: 360px;
  pointer-events: auto;
}

.frontier-col-title {
  margin: 0 0 12px;
  font-size: 17px;
  color: #eef4ff;
}

.paper-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.paper-item {
  display: block;
  border: 1px solid #2a3a55;
  border-radius: 10px;
  padding: 11px;
  text-decoration: none;
  background: rgba(8, 14, 26, 0.65);
}

.paper-item:hover {
  border-color: #d0a96c;
  background: rgba(181, 138, 76, 0.1);
}

.paper-title {
  margin: 0;
  color: #edf3ff;
  font-size: 14px;
  line-height: 1.45;
}

.paper-meta {
  margin: 6px 0 0;
  display: flex;
  justify-content: space-between;
  color: #9eb0ca;
  font-size: 12px;
}

.paper-authors {
  margin: 4px 0 0;
  font-size: 11px;
  color: #4a6080;
  font-family: 'Space Mono', monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.paper-summary {
  margin: 8px 0 0;
  color: #aab9d0;
  font-size: 12px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.paper-empty {
  color: #8fa2be;
  font-size: 13px;
  padding-top: 12px;
}

.frontier-pagination {
  margin-top: 14px;
  display: flex;
  justify-content: center;
  pointer-events: auto;
}

@media (max-width: 1200px) {
  .cards-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .frontier-grid {
    grid-template-columns: 1fr;
  }

  .frontier-col {
    min-height: auto;
  }
}

@media (max-width: 860px) {
  .hero {
    margin-top: 100px;
  }

  h1 {
    font-size: 38px;
  }

  .hero-actions {
    flex-direction: column;
    width: 100%;
    max-width: 340px;
  }

  .hero-search {
    grid-template-columns: 1fr;
    max-width: 340px;
  }

  .news-slide {
    height: 340px;
  }

  .news-content h3 {
    font-size: 24px;
  }

  .cards-grid {
    grid-template-columns: 1fr;
  }
}

.apod-section {
  width: 100%;
  pointer-events: auto;
}
.apod-card {
  display: flex;
  background: rgba(14, 21, 35, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 16px;
  overflow: hidden;
  min-height: 340px;
  height: 100%;
  align-self: stretch;
}
.apod-img-box {
  flex: 0 0 55%;
  position: relative;
  background: #0a0f18;
  min-height: 280px;
}

.apod-media-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 220px;
  padding: 20px;
  color: #8da4c2;
  font-size: 14px;
  text-align: center;
}

.apod-external-link {
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: 12px;
  display: block;
  text-align: center;
  padding: 10px 14px;
  border-radius: 10px;
  background: rgba(8, 14, 26, 0.88);
  border: 1px solid rgba(208, 169, 108, 0.45);
  color: #f1d2a3;
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
}

.apod-external-link:hover {
  border-color: var(--astro-primary);
  color: var(--astro-primary);
}
.apod-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.apod-info {
  flex: 1;
  padding: 36px 40px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.apod-tag {
  color: #dfbea0;
  font-size: 13px;
  letter-spacing: 1px;
  margin-bottom: 8px;
  font-weight: 600;
}
.apod-title {
  font-size: 32px;
  margin: 0 0 6px;
  color: #f7faff;
  line-height: 1.25;
}
.apod-date {
  font-size: 13px;
  color: #8da4c2;
  margin: 0 0 16px;
}
.apod-desc {
  font-size: 14px;
  line-height: 1.6;
  color: #c7d2e4;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 6;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
@media (max-width: 860px) {
  .apod-card {
    flex-direction: column;
  }
  .apod-img-box {
    height: 300px;
  }
}

.apod-neows-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 340px);
  gap: 20px;
  width: 100%;
  align-items: stretch;
}

.neows-col {
  display: flex;
  min-height: 100%;
}

.neows-col > * {
  flex: 1;
  min-width: 0;
}

.aladin-section {
  width: 100%;
  margin-top: 40px;
}

.lazy-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
  border: 1px dashed rgba(19, 210, 184, 0.15);
  color: #3a4e6a;
  font-size: 13px;
  font-family: 'Space Mono', monospace;
}

@media (max-width: 1100px) {
  .apod-neows-row {
    grid-template-columns: 1fr;
  }
  .neows-col {
    height: 400px;
  }
}

</style>

