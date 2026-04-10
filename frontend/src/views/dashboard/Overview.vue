<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { getSystemStatus, getGraphStatus, getDataStatus, getModelStatus, getUserOverview } from "../../api";
import {
  Database,
  Network,
  Cpu,
  MessageSquare,
  Image as ImageIcon,
  Orbit,
  Activity,
  ArrowRight,
  CheckCircle,
  AlertCircle,
  Loader
} from "lucide-vue-next";

const router = useRouter();
const loading = ref(true);

const systemData = ref<any>(null);
const graphData = ref<any>(null);
const dataData = ref<any>(null);
const modelData = ref<any>(null);
const userOverview = ref<any>(null);

const recentQuestions = computed(() => userOverview.value?.recent_explorations?.slice(0, 5) || []);
const stats = computed(() => userOverview.value?.stats || {});

async function loadAll() {
  loading.value = true;
  try {
    const [sys, graph, data, model, user] = await Promise.allSettled([
      getSystemStatus(),
      getGraphStatus(),
      getDataStatus(),
      getModelStatus(),
      getUserOverview()
    ]);
    systemData.value = sys.status === "fulfilled" ? sys.value : null;
    graphData.value = graph.status === "fulfilled" ? graph.value : null;
    dataData.value = data.status === "fulfilled" ? data.value : null;
    modelData.value = model.status === "fulfilled" ? model.value : null;
    userOverview.value = user.status === "fulfilled" ? user.value : null;
  } finally {
    loading.value = false;
  }
}

function goTo(path: string) {
  router.push(path);
}

function goQaWith(question: string) {
  router.push({ path: "/app/qa", query: { q: question, auto: "1" } });
}

function statusIcon(ok: boolean) {
  return ok ? CheckCircle : AlertCircle;
}

function statusColor(ok: boolean) {
  return ok ? "#10b981" : "#f59e0b";
}

onMounted(() => {
  loadAll();
});
</script>

<template>
  <div class="overview-page">
    <div class="overview-scroll">
      <header class="ov-header">
        <div>
          <h1 class="ov-title">系统驾驶舱</h1>
          <p class="ov-subtitle">AstroGraph 多模态天文科普探索系统 · 实时运行状态总览</p>
        </div>
        <button class="refresh-btn" :disabled="loading" @click="loadAll">
          <Loader :size="15" :class="{ spinning: loading }" />
          {{ loading ? '加载中' : '刷新' }}
        </button>
      </header>

      <!-- Status Cards -->
      <section class="status-grid">
        <div class="status-card">
          <div class="sc-icon-wrap green">
            <Database :size="22" />
          </div>
          <div class="sc-body">
            <span class="sc-label">知识实体</span>
            <span class="sc-value">{{ dataData?.entity_count?.toLocaleString() || '0' }}</span>
          </div>
          <component :is="statusIcon(dataData?.loaded)" :size="16" :style="{ color: statusColor(dataData?.loaded) }" class="sc-status" />
        </div>

        <div class="status-card">
          <div class="sc-icon-wrap blue">
            <Network :size="22" />
          </div>
          <div class="sc-body">
            <span class="sc-label">图谱节点</span>
            <span class="sc-value">{{ graphData?.nodes_count?.toLocaleString() || '0' }}</span>
          </div>
          <component :is="statusIcon(graphData?.graph_ready)" :size="16" :style="{ color: statusColor(graphData?.graph_ready) }" class="sc-status" />
        </div>

        <div class="status-card">
          <div class="sc-icon-wrap purple">
            <Orbit :size="22" />
          </div>
          <div class="sc-body">
            <span class="sc-label">图谱关系</span>
            <span class="sc-value">{{ graphData?.relations_count?.toLocaleString() || '0' }}</span>
          </div>
        </div>

        <div class="status-card">
          <div class="sc-icon-wrap cyan">
            <Cpu :size="22" />
          </div>
          <div class="sc-body">
            <span class="sc-label">AI 模型</span>
            <span class="sc-value">{{ modelData?.loaded ? '已就绪' : '未加载' }}</span>
          </div>
          <component :is="statusIcon(modelData?.loaded)" :size="16" :style="{ color: statusColor(modelData?.loaded) }" class="sc-status" />
        </div>

        <div class="status-card">
          <div class="sc-icon-wrap amber">
            <ImageIcon :size="22" />
          </div>
          <div class="sc-body">
            <span class="sc-label">图像数据</span>
            <span class="sc-value">{{ dataData?.image_count?.toLocaleString() || '0' }}</span>
          </div>
        </div>

        <div class="status-card">
          <div class="sc-icon-wrap pink">
            <MessageSquare :size="22" />
          </div>
          <div class="sc-body">
            <span class="sc-label">我的问答</span>
            <span class="sc-value">{{ stats.history_count || 0 }}</span>
          </div>
        </div>
      </section>

      <!-- System Message -->
      <div v-if="systemData?.message" class="system-message">
        <Activity :size="15" class="sm-icon" />
        <span>{{ systemData.message }}</span>
      </div>

      <!-- Quick Navigation + Recent Activity -->
      <div class="content-row">
        <section class="quick-nav">
          <h3>快速导航</h3>
          <div class="nav-cards">
            <button class="nav-card" @click="goTo('/app/qa')">
              <MessageSquare :size="20" class="nc-icon cyan-text" />
              <div class="nc-body">
                <strong>智能问答</strong>
                <span>提出天文问题，获取科普回答</span>
              </div>
              <ArrowRight :size="16" class="nc-arrow" />
            </button>
            <button class="nav-card" @click="goTo('/app/image-search')">
              <ImageIcon :size="20" class="nc-icon amber-text" />
              <div class="nc-body">
                <strong>图像检索</strong>
                <span>以文搜图、以图搜图</span>
              </div>
              <ArrowRight :size="16" class="nc-arrow" />
            </button>
            <button class="nav-card" @click="goTo('/app/knowledge')">
              <Network :size="20" class="nc-icon blue-text" />
              <div class="nc-body">
                <strong>知识图谱</strong>
                <span>实体关系探索与路径发现</span>
              </div>
              <ArrowRight :size="16" class="nc-arrow" />
            </button>
            <button class="nav-card" @click="goTo('/app/starfield')">
              <Orbit :size="20" class="nc-icon purple-text" />
              <div class="nc-body">
                <strong>3D 天体</strong>
                <span>交互式三维模型查看</span>
              </div>
              <ArrowRight :size="16" class="nc-arrow" />
            </button>
          </div>
        </section>

        <section class="recent-section">
          <h3>最近探索</h3>
          <div v-if="recentQuestions.length" class="recent-list">
            <button
              v-for="item in recentQuestions"
              :key="item.id"
              class="recent-item"
              @click="goQaWith(item.question || item.topic)"
            >
              <span class="ri-topic">{{ item.topic }}</span>
              <span class="ri-question">{{ item.question }}</span>
              <span class="ri-time">{{ item.created_at }}</span>
            </button>
          </div>
          <div v-else class="recent-empty">
            <p>还没有探索记录</p>
            <button class="go-qa-btn" @click="goTo('/app/qa')">开始第一次提问</button>
          </div>
        </section>
      </div>

      <!-- Capabilities -->
      <section class="capabilities">
        <h3>系统能力矩阵</h3>
        <div class="cap-grid">
          <div class="cap-item" v-for="cap in [
            { name: '自适应 RAG Agent', ok: true },
            { name: '知识图谱推理', ok: graphData?.graph_ready },
            { name: 'GraphRAG 追踪', ok: true },
            { name: '多模态问答', ok: modelData?.supports_image_qa || modelData?.supports_image_predict },
            { name: '流式 SSE 回答', ok: true },
            { name: '图像向量检索', ok: dataData?.image_count > 0 },
            { name: '多轮会话记忆', ok: true },
            { name: '实时天文数据', ok: true },
          ]" :key="cap.name">
            <component :is="statusIcon(cap.ok)" :size="15" :style="{ color: statusColor(cap.ok) }" />
            <span>{{ cap.name }}</span>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.overview-page {
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.overview-scroll {
  height: 100%;
  overflow-y: auto;
  padding: 0 0 40px;
}

.ov-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 24px 24px 20px;
  border: 1px solid var(--astro-border);
  background: rgba(10, 17, 32, 0.8);
}

.ov-title {
  margin: 0;
  font-size: 24px;
  font-weight: 800;
  color: #fff;
}

.ov-subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.refresh-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: 1px solid var(--astro-border);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.02);
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.refresh-btn:hover {
  border-color: rgba(19, 210, 184, 0.35);
  color: var(--astro-primary);
}

.spinning { animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0); } to { transform: rotate(360deg); } }

.status-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 1px;
  background: var(--astro-border);
  border: 1px solid var(--astro-border);
  border-top: none;
}

.status-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px 16px;
  background: rgba(10, 17, 32, 0.75);
  position: relative;
}

.sc-icon-wrap {
  width: 42px;
  height: 42px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.sc-icon-wrap.green { background: rgba(16, 185, 129, 0.12); color: #10b981; }
.sc-icon-wrap.blue { background: rgba(31, 111, 235, 0.12); color: #5b9cf5; }
.sc-icon-wrap.purple { background: rgba(139, 92, 246, 0.12); color: #a78bfa; }
.sc-icon-wrap.cyan { background: rgba(19, 210, 184, 0.12); color: var(--astro-primary); }
.sc-icon-wrap.amber { background: rgba(245, 158, 11, 0.12); color: #f5b731; }
.sc-icon-wrap.pink { background: rgba(236, 72, 153, 0.12); color: #ec4899; }

.sc-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.sc-label {
  font-size: 11px;
  color: var(--text-secondary);
}

.sc-value {
  font-size: 20px;
  font-weight: 800;
  font-family: 'Space Mono', monospace;
  color: #fff;
  line-height: 1.1;
}

.sc-status {
  position: absolute;
  top: 10px;
  right: 10px;
}

.system-message {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 24px;
  border: 1px solid var(--astro-border);
  border-top: none;
  background: rgba(19, 210, 184, 0.03);
  font-size: 13px;
  color: var(--text-secondary);
}

.sm-icon { color: var(--astro-primary); flex-shrink: 0; }

.content-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1px;
  background: var(--astro-border);
  border: 1px solid var(--astro-border);
  border-top: none;
}

.quick-nav,
.recent-section {
  background: rgba(10, 17, 32, 0.7);
  padding: 20px 24px;
}

.quick-nav h3,
.recent-section h3,
.capabilities h3 {
  margin: 0 0 14px;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
}

.nav-cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.nav-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--astro-border);
  border-radius: 8px;
  background: rgba(6, 12, 22, 0.5);
  cursor: pointer;
  text-align: left;
  transition: all 0.12s;
}

.nav-card:hover {
  border-color: rgba(19, 210, 184, 0.3);
  background: rgba(19, 210, 184, 0.03);
}

.nc-icon { flex-shrink: 0; }
.cyan-text { color: var(--astro-primary); }
.amber-text { color: #f5b731; }
.blue-text { color: #5b9cf5; }
.purple-text { color: #a78bfa; }

.nc-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.nc-body strong { font-size: 14px; color: var(--text-primary); }
.nc-body span { font-size: 12px; color: var(--text-secondary); }

.nc-arrow { color: #2a3d5a; flex-shrink: 0; }
.nav-card:hover .nc-arrow { color: var(--astro-primary); }

.recent-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.recent-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 10px 12px;
  border: 1px solid var(--astro-border);
  border-radius: 8px;
  background: rgba(6, 12, 22, 0.5);
  text-align: left;
  cursor: pointer;
  transition: all 0.12s;
}

.recent-item:hover {
  border-color: rgba(19, 210, 184, 0.25);
}

.ri-topic { font-size: 13px; font-weight: 600; color: var(--astro-primary); }
.ri-question { font-size: 12px; color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ri-time { font-size: 11px; color: #3a4e6a; font-family: 'Space Mono', monospace; }

.recent-empty {
  text-align: center;
  padding: 30px 0;
}

.recent-empty p { margin: 0 0 12px; color: var(--text-secondary); font-size: 13px; }

.go-qa-btn {
  padding: 8px 18px;
  border: 1px solid var(--astro-primary);
  border-radius: 8px;
  background: rgba(19, 210, 184, 0.08);
  color: var(--astro-primary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.12s;
}

.go-qa-btn:hover { background: rgba(19, 210, 184, 0.18); }

.capabilities {
  padding: 20px 24px;
  border: 1px solid var(--astro-border);
  border-top: none;
  background: rgba(10, 17, 32, 0.7);
}

.cap-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}

.cap-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--astro-border);
  border-radius: 6px;
  background: rgba(6, 12, 22, 0.4);
  font-size: 13px;
  color: var(--text-secondary);
}

@media (max-width: 1100px) {
  .status-grid { grid-template-columns: repeat(3, 1fr); }
  .content-row { grid-template-columns: 1fr; }
  .cap-grid { grid-template-columns: repeat(2, 1fr); }
}

@media (max-width: 700px) {
  .status-grid { grid-template-columns: repeat(2, 1fr); }
  .cap-grid { grid-template-columns: 1fr; }
}
</style>
