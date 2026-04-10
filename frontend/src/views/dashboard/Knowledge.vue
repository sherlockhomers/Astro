<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  compareEntities,
  findGraphMultiPath,
  getVisualizationGraph,
  getVisualizationSubgraph,
  searchKnowledge
} from "../../api";
import {
  Search,
  Network,
  GitFork,
  BarChart3,
  FileText,
  ChevronRight,
  Info
} from "lucide-vue-next";

const GraphChart = defineAsyncComponent(() => import("../../components/GraphChart.vue"));
const EntityCompareChart = defineAsyncComponent(() => import("../../components/EntityCompareChart.vue"));

type GraphNode = { id: string; name: string; category?: string; value?: number; is_seed?: boolean };
type GraphLink = { source: string; target: string; name?: string };
type KnowledgeItem = { title?: string; score?: number; snippet?: string; source?: string };

const route = useRoute();
const query = ref("木星");
const maxNodes = ref(220);
const maxHops = ref(1);
const includeRelated = ref(false);
const loadingGraph = ref(false);
const graphError = ref("");
const graphData = ref<{ nodes: GraphNode[]; links: GraphLink[]; categories: string[]; rendered_nodes?: number; rendered_links?: number }>({
  nodes: [],
  links: [],
  categories: []
});

const loadingSearch = ref(false);
const searchResults = ref<KnowledgeItem[]>([]);

const nodeDetail = ref<{
  name: string;
  category: string;
  degree: number;
  neighbors: string[];
} | null>(null);

const pathSource = ref("地球");
const pathTarget = ref("火星");
const loadingPath = ref(false);
const pathRows = ref<string[]>([]);

const compareA = ref("木星");
const compareB = ref("火星");
const loadingCompare = ref(false);
const comparePayload = ref<any>(null);

const sideTab = ref<"detail" | "path" | "compare" | "results">("detail");

const quickTags = computed(() => {
  const tags = new Set<string>();
  for (const item of searchResults.value) {
    const title = String(item.title || "").trim();
    if (!title) continue;
    tags.add(title);
    if (tags.size >= 10) break;
  }
  return Array.from(tags);
});

const graphStatsText = computed(() => {
  const n = Number(graphData.value.rendered_nodes || graphData.value.nodes.length || 0);
  const l = Number(graphData.value.rendered_links || graphData.value.links.length || 0);
  return `${n} 节点 · ${l} 关系`;
});

const compareMetrics = computed(() => {
  if (!comparePayload.value?.ok) return [];
  return Array.isArray(comparePayload.value.metrics) ? comparePayload.value.metrics : [];
});

const compareSummary = computed(() => {
  if (!comparePayload.value?.ok) return "";
  return String(comparePayload.value.summary || "");
});

function sanitizeLine(text: string): string {
  const t = String(text || "").trim();
  if (!t) return "";
  if (/^\?+$/.test(t)) return "";
  return t;
}

function buildNodeDetail(name: string) {
  const node = graphData.value.nodes.find((n) => n.name === name || n.id === name);
  const category = String(node?.category || "unknown");
  const neighbors = new Set<string>();
  let degree = 0;
  for (const link of graphData.value.links) {
    if (link.source === name) {
      degree += 1;
      neighbors.add(link.target);
    } else if (link.target === name) {
      degree += 1;
      neighbors.add(link.source);
    }
  }
  nodeDetail.value = {
    name,
    category,
    degree,
    neighbors: Array.from(neighbors).slice(0, 24)
  };
  sideTab.value = "detail";
}

async function runKnowledgeSearch() {
  loadingSearch.value = true;
  try {
    const payload = await searchKnowledge(query.value, 20);
    const items = Array.isArray(payload?.items) ? payload.items : [];
    searchResults.value = items
      .map((x: any) => ({
        title: sanitizeLine(String(x?.title || "")),
        score: Number(x?.score || 0),
        snippet: sanitizeLine(String(x?.snippet || "")),
        source: sanitizeLine(String(x?.source || ""))
      }))
      .filter((x: KnowledgeItem) => x.title || x.snippet);
  } catch {
    searchResults.value = [];
  } finally {
    loadingSearch.value = false;
  }
}

async function runSubgraph() {
  loadingGraph.value = true;
  graphError.value = "";
  try {
    const payload = await getVisualizationSubgraph(
      query.value,
      maxNodes.value,
      1200,
      maxHops.value,
      includeRelated.value
    );
    const nodes = Array.isArray(payload?.nodes) ? payload.nodes : [];
    const links = Array.isArray(payload?.links) ? payload.links : [];
    const categories = Array.isArray(payload?.categories) ? payload.categories : [];
    graphData.value = {
      nodes,
      links,
      categories,
      rendered_nodes: Number(payload?.rendered_nodes || nodes.length),
      rendered_links: Number(payload?.rendered_links || links.length)
    };

    const seed = nodes.find((n: GraphNode) => Boolean(n.is_seed));
    if (seed?.name) {
      buildNodeDetail(seed.name);
    } else if (nodes[0]?.name) {
      buildNodeDetail(nodes[0].name);
    } else {
      nodeDetail.value = null;
    }
  } catch {
    graphData.value = { nodes: [], links: [], categories: [] };
    nodeDetail.value = null;
    graphError.value = "图谱加载失败，请稍后重试。";
  } finally {
    loadingGraph.value = false;
  }
}

async function runGraph() {
  await Promise.all([runSubgraph(), runKnowledgeSearch()]);
}

async function loadGlobalGraph() {
  loadingGraph.value = true;
  graphError.value = "";
  try {
    const payload = await getVisualizationGraph(maxNodes.value, 2400);
    const nodes = Array.isArray(payload?.nodes) ? payload.nodes : [];
    const links = Array.isArray(payload?.links) ? payload.links : [];
    const categories = Array.isArray(payload?.categories) ? payload.categories : [];
    graphData.value = {
      nodes,
      links,
      categories,
      rendered_nodes: Number(payload?.rendered_nodes || nodes.length),
      rendered_links: Number(payload?.rendered_links || links.length)
    };
    if (nodes[0]?.name) buildNodeDetail(nodes[0].name);
  } catch {
    graphError.value = "全局图谱加载失败。";
  } finally {
    loadingGraph.value = false;
  }
}

function handleNodeClick(node: { name: string }) {
  if (!node?.name) return;
  buildNodeDetail(node.name);
}

async function runPath() {
  loadingPath.value = true;
  pathRows.value = [];
  try {
    const payload = await findGraphMultiPath(pathSource.value, pathTarget.value, 4, 6);
    const paths = Array.isArray(payload?.paths) ? payload.paths : [];
    const rows: string[] = [];
    for (const p of paths) {
      if (!Array.isArray(p) || !p.length) continue;
      const segs = p.map((s: any) => `${s.from} →[${s.rel}]→ ${s.to}`);
      rows.push(segs.join("  "));
    }
    pathRows.value = rows;
  } catch {
    pathRows.value = [];
  } finally {
    loadingPath.value = false;
  }
}

async function runCompare() {
  loadingCompare.value = true;
  comparePayload.value = null;
  try {
    comparePayload.value = await compareEntities(compareA.value, compareB.value);
  } catch {
    comparePayload.value = null;
  } finally {
    loadingCompare.value = false;
  }
}

function pickTag(tag: string) {
  query.value = tag;
  runGraph();
}

function applyRoute() {
  const q = typeof route.query.q === "string" ? route.query.q.trim() : "";
  if (q) {
    query.value = q;
    runGraph();
  }
}

onMounted(() => {
  applyRoute();
  if (!route.query.q) runGraph();
});
</script>

<template>
  <div class="knowledge-page">
    <!-- Search Bar -->
    <div class="search-strip">
      <div class="search-left">
        <div class="search-input-wrap">
          <Search :size="15" class="si-icon" />
          <input
            v-model="query"
            class="search-input"
            placeholder="输入实体或问题检索图谱，如：木星、黑洞、太阳系"
            @keyup.enter="runGraph"
          />
        </div>
        <button class="search-btn" :disabled="loadingGraph" @click="runGraph">检索</button>
        <button class="search-btn secondary" :disabled="loadingGraph" @click="loadGlobalGraph">全局图谱</button>
      </div>
      <div class="search-options">
        <span class="opt-label">深度</span>
        <el-segmented v-model="maxHops" :options="[1, 2]" size="small" />
        <el-switch v-model="includeRelated" size="small" />
        <span class="opt-label">{{ includeRelated ? '弱关系' : '强关系' }}</span>
      </div>
    </div>

    <!-- Tags -->
    <div v-if="quickTags.length" class="tags-strip">
      <button v-for="tag in quickTags" :key="tag" class="tag-chip" @click="pickTag(tag)">{{ tag }}</button>
      <span class="graph-stats">{{ graphStatsText }}</span>
    </div>

    <!-- Main Body -->
    <div class="main-body">
      <!-- Graph Area -->
      <div class="graph-area">
        <p v-if="graphError" class="graph-error">{{ graphError }}</p>
        <GraphChart
          :nodes="graphData.nodes"
          :links="graphData.links"
          :categories="graphData.categories"
          :render-limit-nodes="maxNodes"
          :render-limit-links="2400"
          @node-click="handleNodeClick"
        />
      </div>

      <!-- Right Sidebar -->
      <div class="sidebar">
        <div class="side-tabs">
          <button
            v-for="tab in [
              { key: 'detail', label: '节点', icon: Info },
              { key: 'path', label: '路径', icon: GitFork },
              { key: 'compare', label: '对比', icon: BarChart3 },
              { key: 'results', label: '检索', icon: FileText }
            ]"
            :key="tab.key"
            :class="['side-tab', { active: sideTab === tab.key }]"
            @click="sideTab = tab.key as any"
          >
            <component :is="tab.icon" :size="14" />
            {{ tab.label }}
          </button>
        </div>

        <div class="side-content">
          <!-- Node Detail -->
          <div v-if="sideTab === 'detail'" class="side-panel">
            <template v-if="nodeDetail">
              <div class="detail-header">
                <h3>{{ nodeDetail.name }}</h3>
                <span class="detail-cat">{{ nodeDetail.category }}</span>
              </div>
              <div class="detail-stat-row">
                <div class="detail-stat">
                  <span class="ds-val">{{ nodeDetail.degree }}</span>
                  <span class="ds-label">连接度</span>
                </div>
                <div class="detail-stat">
                  <span class="ds-val">{{ nodeDetail.neighbors.length }}</span>
                  <span class="ds-label">邻居数</span>
                </div>
              </div>
              <div class="neighbor-section">
                <span class="ns-label">相邻节点</span>
                <div class="neighbor-wrap">
                  <button
                    v-for="n in nodeDetail.neighbors"
                    :key="n"
                    class="neighbor-chip"
                    @click="query = n; runGraph()"
                  >{{ n }}</button>
                  <span v-if="!nodeDetail.neighbors.length" class="muted">暂无</span>
                </div>
              </div>
            </template>
            <div v-else class="empty-side">
              <Network :size="32" class="empty-side-icon" />
              <p>点击图谱节点查看详情</p>
            </div>
          </div>

          <!-- Path Finding -->
          <div v-if="sideTab === 'path'" class="side-panel">
            <div class="side-form">
              <input v-model="pathSource" class="side-input" placeholder="起点实体" />
              <input v-model="pathTarget" class="side-input" placeholder="终点实体" />
              <button class="side-btn" :disabled="loadingPath" @click="runPath">
                {{ loadingPath ? '查找中...' : '查找路径' }}
              </button>
            </div>
            <div class="path-results">
              <div v-for="(item, idx) in pathRows" :key="`${idx}-${item}`" class="path-row">
                <span class="path-idx">{{ idx + 1 }}</span>
                <span class="path-text">{{ item }}</span>
              </div>
              <div v-if="!pathRows.length" class="muted center">输入两个实体名称查找关系路径</div>
            </div>
          </div>

          <!-- Entity Compare -->
          <div v-if="sideTab === 'compare'" class="side-panel">
            <div class="side-form">
              <input v-model="compareA" class="side-input" placeholder="实体 A" />
              <input v-model="compareB" class="side-input" placeholder="实体 B" />
              <button class="side-btn" :disabled="loadingCompare" @click="runCompare">
                {{ loadingCompare ? '对比中...' : '开始对比' }}
              </button>
            </div>
            <div v-if="compareSummary" class="compare-summary">{{ compareSummary }}</div>
            <EntityCompareChart
              v-if="compareMetrics.length"
              :left-name="compareA"
              :right-name="compareB"
              :metrics="compareMetrics"
            />
            <div v-if="!comparePayload && !loadingCompare" class="muted center">输入两个实体名称进行属性对比</div>
          </div>

          <!-- Search Results -->
          <div v-if="sideTab === 'results'" class="side-panel">
            <div v-if="searchResults.length" class="result-list">
              <div v-for="(item, idx) in searchResults" :key="`${idx}-${item.title}`" class="result-card">
                <strong>{{ item.title || "未命名" }}</strong>
                <p>{{ item.snippet || "无摘要" }}</p>
              </div>
            </div>
            <div v-else class="muted center">{{ loadingSearch ? '检索中...' : '暂无检索结果' }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.knowledge-page {
  width: 100%;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 0;
  overflow: hidden;
}

/* ===== Search Strip ===== */
.search-strip {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border: 1px solid var(--astro-border);
  background: rgba(10, 17, 32, 0.8);
  flex-shrink: 0;
}

.search-left {
  display: flex;
  gap: 6px;
  flex: 1;
  min-width: 0;
}

.search-input-wrap {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  border: 1px solid var(--astro-border);
  border-radius: 6px;
  background: rgba(6, 12, 22, 0.6);
  min-width: 0;
  transition: border-color 0.15s;
}

.search-input-wrap:focus-within {
  border-color: rgba(19, 210, 184, 0.4);
}

.si-icon {
  color: #4a5e78;
  flex-shrink: 0;
}

.search-input {
  flex: 1;
  border: none;
  background: transparent;
  color: var(--text-primary);
  font-size: 13px;
  padding: 8px 0;
  outline: none;
  min-width: 0;
}

.search-input::placeholder {
  color: #3a4e6a;
}

.search-btn {
  padding: 8px 16px;
  border: 1px solid var(--astro-primary);
  border-radius: 6px;
  background: rgba(19, 210, 184, 0.08);
  color: var(--astro-primary);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
  transition: all 0.12s;
}

.search-btn:hover {
  background: rgba(19, 210, 184, 0.18);
}

.search-btn.secondary {
  border-color: var(--astro-border);
  color: var(--text-secondary);
  background: rgba(255, 255, 255, 0.02);
}

.search-btn.secondary:hover {
  border-color: rgba(19, 210, 184, 0.3);
  color: var(--astro-primary);
}

.search-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.search-options {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.opt-label {
  font-size: 12px;
  color: var(--text-secondary);
}

/* ===== Tags Strip ===== */
.tags-strip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: 1px solid var(--astro-border);
  border-top: none;
  background: rgba(8, 14, 26, 0.6);
  flex-shrink: 0;
  flex-wrap: wrap;
}

.tag-chip {
  padding: 3px 10px;
  border: 1px solid var(--astro-border);
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.02);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.12s;
}

.tag-chip:hover {
  border-color: rgba(19, 210, 184, 0.35);
  color: var(--astro-primary);
  background: rgba(19, 210, 184, 0.05);
}

.graph-stats {
  margin-left: auto;
  font-size: 11px;
  color: #3a4e6a;
  font-family: 'Space Mono', monospace;
}

/* ===== Main Body ===== */
.main-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 1fr 320px;
  border: 1px solid var(--astro-border);
  border-top: none;
  overflow: hidden;
}

/* ===== Graph Area ===== */
.graph-area {
  position: relative;
  min-height: 0;
  overflow: hidden;
  background: rgba(5, 8, 14, 0.7);
}

.graph-error {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 5;
  margin: 0;
  padding: 6px 12px;
  border-radius: 6px;
  background: rgba(239, 68, 68, 0.12);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: #ff8f8f;
  font-size: 12px;
}

/* ===== Sidebar ===== */
.sidebar {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-left: 1px solid var(--astro-border);
  background: rgba(10, 17, 32, 0.7);
}

.side-tabs {
  display: flex;
  border-bottom: 1px solid var(--astro-border);
  flex-shrink: 0;
}

.side-tab {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 10px 6px;
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.12s;
}

.side-tab:hover {
  color: var(--text-primary);
  background: rgba(255, 255, 255, 0.02);
}

.side-tab.active {
  color: var(--astro-primary);
  border-bottom-color: var(--astro-primary);
}

.side-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.side-panel {
  height: 100%;
  overflow-y: auto;
  padding: 14px;
}

/* ===== Node Detail ===== */
.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
}

.detail-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 800;
  color: #fff;
}

.detail-cat {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid var(--astro-border);
  color: var(--text-secondary);
  white-space: nowrap;
}

.detail-stat-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 14px;
}

.detail-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 10px;
  border: 1px solid var(--astro-border);
  border-radius: 8px;
  background: rgba(6, 12, 22, 0.5);
}

.ds-val {
  font-size: 22px;
  font-weight: 800;
  font-family: 'Space Mono', monospace;
  color: var(--astro-primary);
}

.ds-label {
  font-size: 11px;
  color: var(--text-secondary);
}

.neighbor-section {
  margin-top: 4px;
}

.ns-label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.neighbor-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.neighbor-chip {
  padding: 3px 10px;
  border: 1px solid var(--astro-border);
  border-radius: 4px;
  background: rgba(6, 12, 22, 0.5);
  color: var(--text-primary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.12s;
}

.neighbor-chip:hover {
  border-color: rgba(19, 210, 184, 0.35);
  color: var(--astro-primary);
}

/* ===== Side Form ===== */
.side-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 14px;
}

.side-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--astro-border);
  border-radius: 6px;
  background: rgba(6, 12, 22, 0.6);
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  transition: border-color 0.12s;
}

.side-input:focus {
  border-color: rgba(19, 210, 184, 0.4);
}

.side-input::placeholder {
  color: #3a4e6a;
}

.side-btn {
  padding: 8px 14px;
  border: 1px solid var(--astro-primary);
  border-radius: 6px;
  background: rgba(19, 210, 184, 0.08);
  color: var(--astro-primary);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.12s;
}

.side-btn:hover {
  background: rgba(19, 210, 184, 0.18);
}

.side-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ===== Path Results ===== */
.path-results {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.path-row {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 8px 10px;
  border: 1px solid var(--astro-border);
  border-radius: 6px;
  background: rgba(6, 12, 22, 0.4);
}

.path-idx {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  background: rgba(19, 210, 184, 0.12);
  color: var(--astro-primary);
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.path-text {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  word-break: break-all;
}

/* ===== Compare ===== */
.compare-summary {
  margin-bottom: 12px;
  padding: 10px;
  border: 1px solid var(--astro-border);
  border-radius: 6px;
  background: rgba(6, 12, 22, 0.4);
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}

/* ===== Results ===== */
.result-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.result-card {
  padding: 10px;
  border: 1px solid var(--astro-border);
  border-radius: 6px;
  background: rgba(6, 12, 22, 0.4);
}

.result-card strong {
  font-size: 13px;
  color: var(--text-primary);
}

.result-card p {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ===== Empty / Muted ===== */
.empty-side {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 40px 16px;
  gap: 10px;
}

.empty-side-icon {
  color: #1e3a54;
}

.empty-side p {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.muted {
  font-size: 12px;
  color: var(--text-secondary);
}

.muted.center {
  text-align: center;
  padding: 30px 12px;
}

/* ===== Responsive ===== */
@media (max-width: 900px) {
  .main-body {
    grid-template-columns: 1fr;
    grid-template-rows: 1fr 300px;
  }

  .sidebar {
    border-left: none;
    border-top: 1px solid var(--astro-border);
  }

  .search-strip {
    flex-direction: column;
    align-items: stretch;
  }

  .search-options {
    justify-content: flex-start;
  }
}
</style>
