<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { deleteFavorite, deleteHistoryItem, getRecommendPath, getUserOverview, logout } from "../../api";
import {
  User,
  Clock,
  Star,
  MessageSquare,
  Sparkles,
  ArrowRight,
  Trash2,
  RefreshCw,
  LogOut,
  Calendar,
  Hash,
  Telescope,
  Orbit,
  ChevronRight,
  X,
  Rocket,
  Search
} from "lucide-vue-next";

type Overview = {
  ok: boolean;
  user_id: number;
  username: string;
  created_at?: string | null;
  stats?: Record<string, number>;
  recent_explorations?: Array<{ id: number; session_id: string; question: string; topic: string; created_at: string }>;
  favorites?: Array<{ id: number; title: string; category?: string | null; image_url?: string | null; source_query?: string | null; created_at: string }>;
  history_preview?: Array<{ id: number; session_id: string; question: string; answer: string; citations?: string[]; created_at: string }>;
  recommended_continue?: Array<{ title: string; query: string; reason: string; path: string }>;
};

type PathCard = {
  name: string;
  seed: string;
  relation: string;
  score: number;
  query: string;
  reason: string;
  path: string;
};

const router = useRouter();
const loading = ref(false);
const busyId = ref<number | null>(null);
const overview = ref<Overview | null>(null);
const drawerType = ref<"" | "recent" | "favorites" | "recommended">("");

// 「你的下一站」—— 图谱游走算出的推荐；跟上面那个模板式推荐不一样
const pathCards = ref<PathCard[]>([]);
const pathSeeds = ref<string[]>([]);
const pathLoading = ref(false);

const stats = computed(() => overview.value?.stats || {});
const recentItems = computed(() => overview.value?.recent_explorations || []);
const favoriteItems = computed(() => overview.value?.favorites || []);
const historyItems = computed(() => overview.value?.history_preview || []);
const recommendedItems = computed(() => overview.value?.recommended_continue || []);

const memberDays = computed(() => {
  if (!overview.value?.created_at) return 0;
  const created = new Date(overview.value.created_at);
  const now = new Date();
  return Math.max(1, Math.floor((now.getTime() - created.getTime()) / (1000 * 60 * 60 * 24)));
});

const formattedDate = computed(() => {
  if (!overview.value?.created_at) return "--";
  try {
    const d = new Date(overview.value.created_at);
    return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`;
  } catch {
    return overview.value.created_at;
  }
});

function formatTime(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return "刚刚";
    if (diffMin < 60) return `${diffMin} 分钟前`;
    const diffHour = Math.floor(diffMin / 60);
    if (diffHour < 24) return `${diffHour} 小时前`;
    const diffDay = Math.floor(diffHour / 24);
    if (diffDay < 7) return `${diffDay} 天前`;
    return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  } catch {
    return dateStr;
  }
}

async function loadOverview() {
  loading.value = true;
  try {
    overview.value = await getUserOverview();
  } finally {
    loading.value = false;
  }
}

async function loadPathCards() {
  pathLoading.value = true;
  try {
    const payload = await getRecommendPath();
    pathCards.value = Array.isArray(payload?.cards) ? payload.cards : [];
    pathSeeds.value = Array.isArray(payload?.seeds) ? payload.seeds : [];
  } catch {
    pathCards.value = [];
    pathSeeds.value = [];
  } finally {
    pathLoading.value = false;
  }
}

function openPathCard(card: PathCard) {
  router.push({ path: card.path || "/app/qa", query: { q: card.query, auto: "1" } });
}

function openRoute(path: string, query: string, auto = true) {
  router.push({ path, query: auto ? { q: query, auto: "1" } : { q: query } });
}

function openRecent(item: { topic: string; question: string }) {
  openRoute("/app/qa", item.question || item.topic, true);
}

function openFavorite(item: { title: string; source_query?: string | null }) {
  openRoute("/app/qa", item.source_query || item.title, true);
}

function openHistory(item: { question: string }) {
  openRoute("/app/qa", item.question, true);
}

function openRecommendation(item: { path: string; query: string }) {
  openRoute(item.path || "/app/qa", item.query, true);
}

async function removeFavorite(id: number) {
  if (busyId.value !== null) return;
  busyId.value = id;
  try {
    await deleteFavorite(id);
    await loadOverview();
  } finally {
    busyId.value = null;
  }
}

async function removeHistory(id: number) {
  if (busyId.value !== null) return;
  busyId.value = id;
  try {
    await deleteHistoryItem(id);
    await loadOverview();
  } finally {
    busyId.value = null;
  }
}

function openDrawer(type: "recent" | "favorites" | "recommended") {
  drawerType.value = type;
}

function closeDrawer() {
  drawerType.value = "";
}

async function signOut() {
  try {
    await logout();
  } finally {
    router.push("/login");
  }
}

onMounted(() => {
  void loadOverview();
  void loadPathCards();
});
</script>

<template>
  <div class="profile-page">
    <div class="profile-scroll">
      <!-- Compact Profile Header -->
      <header class="profile-header">
        <div class="header-bg"></div>
        <div class="header-content">
          <div class="header-left">
            <div class="avatar-ring">
              <div class="avatar-inner" v-if="overview">{{ overview.username.charAt(0).toUpperCase() }}</div>
              <div class="avatar-inner" v-else>?</div>
            </div>
            <div class="header-info" v-if="overview">
              <div class="name-row">
                <h1>{{ overview.username }}</h1>
                <span class="badge-explorer">
                  <Telescope :size="12" />
                  天文探索者
                </span>
              </div>
              <div class="header-meta">
                <span class="meta-item"><Hash :size="11" /> ID {{ overview.user_id }}</span>
                <span class="meta-sep">·</span>
                <span class="meta-item"><Calendar :size="11" /> {{ formattedDate }} 加入</span>
                <span class="meta-sep">·</span>
                <span class="meta-item"><Orbit :size="11" /> 第 {{ memberDays }} 天</span>
              </div>
            </div>
            <el-skeleton v-else animated :rows="1" style="width: 240px" />
          </div>
          <div class="header-actions">
            <button class="btn-icon" @click="loadOverview" :disabled="loading" title="刷新">
              <RefreshCw :size="16" :class="{ spinning: loading }" />
            </button>
            <button class="btn-icon danger" @click="signOut" title="退出登录">
              <LogOut :size="16" />
            </button>
          </div>
        </div>
      </header>

      <!-- Quick Access Cards -->
      <section class="quick-access" v-if="overview">
        <button class="access-card" @click="openDrawer('recent')">
          <div class="access-icon blue"><Clock :size="18" /></div>
          <div class="access-body">
            <strong>{{ stats.recent_count || 0 }}</strong>
            <span>最近探索</span>
          </div>
          <ChevronRight :size="16" class="access-arrow" />
        </button>
        <button class="access-card" @click="openDrawer('favorites')">
          <div class="access-icon amber"><Star :size="18" /></div>
          <div class="access-body">
            <strong>{{ stats.favorites_count || 0 }}</strong>
            <span>收藏天体</span>
          </div>
          <ChevronRight :size="16" class="access-arrow" />
        </button>
        <button class="access-card" @click="openDrawer('recommended')">
          <div class="access-icon purple"><Sparkles :size="18" /></div>
          <div class="access-body">
            <strong>{{ recommendedItems.length }}</strong>
            <span>推荐探索</span>
          </div>
          <ChevronRight :size="16" class="access-arrow" />
        </button>
        <div class="access-stat">
          <div class="access-icon cyan"><MessageSquare :size="18" /></div>
          <div class="access-body">
            <strong>{{ stats.history_count || 0 }}</strong>
            <span>问答记录</span>
          </div>
        </div>
      </section>

      <!-- 你的下一站 —— 图谱游走推荐 -->
      <section class="path-section">
        <div class="section-header">
          <div class="section-title-group">
            <Sparkles :size="18" class="section-icon" />
            <h2>你的下一站</h2>
          </div>
          <span class="section-hint">
            <template v-if="pathSeeds.length">
              基于「{{ pathSeeds.slice(0, 3).join('、') }}」在知识图谱上找出来的相关话题
            </template>
            <template v-else>
              先问几个问题或收藏几个天体，这里会推荐关联话题
            </template>
          </span>
        </div>

        <div v-if="pathLoading" class="path-loading">正在沿着知识图谱走一遍...</div>
        <div v-else-if="pathCards.length" class="path-grid">
          <button
            v-for="(card, idx) in pathCards.slice(0, 6)"
            :key="card.name + idx"
            class="path-card"
            @click="openPathCard(card)"
          >
            <div class="path-card-top">
              <span class="path-hop">{{ String(idx + 1).padStart(2, '0') }}</span>
              <span class="path-name">{{ card.name }}</span>
            </div>
            <p class="path-reason">{{ card.reason }}</p>
            <div class="path-card-bottom">
              <span class="path-query">"{{ card.query }}"</span>
              <ArrowRight :size="13" class="path-arrow" />
            </div>
          </button>
        </div>
        <div v-else class="path-empty">
          <Sparkles :size="28" class="de-icon" />
          <p>再问几个问题或收藏几个天体，我们就能画出你的下一站</p>
        </div>
      </section>

      <!-- Main History Feed -->
      <section class="history-section">
        <div class="section-header">
          <div class="section-title-group">
            <MessageSquare :size="18" class="section-icon" />
            <h2>问答历史</h2>
          </div>
          <span class="section-hint">点击任意记录可直接继续对话</span>
        </div>

        <div v-if="historyItems.length" class="history-feed">
          <div
            v-for="(item, idx) in historyItems"
            :key="item.id"
            class="feed-card"
          >
            <div class="feed-index">
              <span class="feed-num">{{ String(idx + 1).padStart(2, "0") }}</span>
            </div>
            <div class="feed-content">
              <div class="feed-question" @click="openHistory(item)">
                <div class="q-badge">Q</div>
                <div class="q-text">{{ item.question }}</div>
              </div>
              <div class="feed-answer">
                <div class="a-badge">A</div>
                <p class="a-text">{{ item.answer }}</p>
              </div>
                <div class="feed-footer">
                <span class="feed-time">{{ formatTime(item.created_at) }}</span>
                <div class="feed-actions">
                  <button class="feed-btn-continue" @click="openHistory(item)">
                    继续追问
                    <ArrowRight :size="12" />
                  </button>
                  <button
                    class="feed-btn-delete"
                    :disabled="busyId === item.id"
                    @click.stop="removeHistory(item.id)"
                  >
                    <Trash2 :size="12" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-else class="empty-history">
          <div class="empty-visual">
            <Search :size="48" class="empty-main-icon" />
          </div>
          <h3>还没有问答记录</h3>
          <p>你对宇宙的每一个提问，都会在这里留下足迹</p>
          <button class="btn-cta" @click="openRoute('/app/qa', '', false)">
            <Rocket :size="15" />
            开始你的第一次探索
          </button>
        </div>
      </section>
    </div>

    <!-- Slide-over Drawer -->
    <Teleport to="body">
      <Transition name="drawer">
        <div v-if="drawerType" class="drawer-overlay" @click.self="closeDrawer">
          <div class="drawer-panel">
            <div class="drawer-header">
              <h3>
                <template v-if="drawerType === 'recent'">
                  <Clock :size="18" /> 最近探索
                </template>
                <template v-else-if="drawerType === 'favorites'">
                  <Star :size="18" /> 收藏天体
                </template>
                <template v-else>
                  <Sparkles :size="18" /> 推荐探索
                </template>
              </h3>
              <button class="btn-close" @click="closeDrawer">
                <X :size="18" />
              </button>
            </div>

            <div class="drawer-body">
              <!-- Recent -->
              <template v-if="drawerType === 'recent'">
                <div v-if="recentItems.length" class="drawer-list">
                  <button
                    v-for="item in recentItems"
                    :key="item.id"
                    class="drawer-item"
                    @click="openRecent(item); closeDrawer()"
                  >
                    <div class="di-dot"></div>
                    <div class="di-body">
                      <strong>{{ item.topic }}</strong>
                      <span>{{ item.question }}</span>
                      <small>{{ formatTime(item.created_at) }}</small>
                    </div>
                    <ArrowRight :size="14" class="di-arrow" />
                  </button>
                </div>
                <div v-else class="drawer-empty">
                  <Clock :size="32" class="de-icon" />
                  <p>暂无最近探索记录</p>
                </div>
              </template>

              <!-- Favorites -->
              <template v-if="drawerType === 'favorites'">
                <div v-if="favoriteItems.length" class="drawer-list">
                  <div
                    v-for="item in favoriteItems"
                    :key="item.id"
                    class="drawer-item with-action"
                  >
                    <div class="di-star-icon">
                      <Star :size="14" />
                    </div>
                    <button
                      class="di-body clickable"
                      @click="openFavorite(item); closeDrawer()"
                    >
                      <strong>{{ item.title }}</strong>
                      <span>{{ item.category || "天体" }}</span>
                      <small>{{ formatTime(item.created_at) }}</small>
                    </button>
                    <button
                      class="di-delete"
                      :disabled="busyId === item.id"
                      @click.stop="removeFavorite(item.id)"
                    >
                      <Trash2 :size="13" />
                    </button>
                  </div>
                </div>
                <div v-else class="drawer-empty">
                  <Star :size="32" class="de-icon" />
                  <p>暂无收藏天体</p>
                  <span>在问答中点击"收藏天体"即可添加</span>
                </div>
              </template>

              <!-- Recommended -->
              <template v-if="drawerType === 'recommended'">
                <div v-if="recommendedItems.length" class="drawer-list">
                  <button
                    v-for="item in recommendedItems"
                    :key="item.title"
                    class="drawer-item rec"
                    @click="openRecommendation(item); closeDrawer()"
                  >
                    <div class="di-spark-icon">
                      <Sparkles :size="14" />
                    </div>
                    <div class="di-body">
                      <strong>{{ item.title }}</strong>
                      <span>{{ item.reason }}</span>
                    </div>
                    <ArrowRight :size="14" class="di-arrow" />
                  </button>
                </div>
                <div v-else class="drawer-empty">
                  <Sparkles :size="32" class="de-icon" />
                  <p>暂无推荐内容</p>
                  <span>多使用问答和收藏，系统会自动生成推荐</span>
                </div>
              </template>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.profile-page {
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.profile-scroll {
  height: 100%;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 0;
}

/* ===== Profile Header ===== */
.profile-header {
  position: relative;
  padding: 24px 28px;
  border: 1px solid var(--astro-border);
  background: rgba(10, 17, 32, 0.85);
  overflow: hidden;
}

.header-bg {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse at 90% 0%, rgba(19, 210, 184, 0.07) 0%, transparent 55%),
    radial-gradient(ellipse at 10% 100%, rgba(94, 184, 255, 0.04) 0%, transparent 50%);
  pointer-events: none;
}

.header-content {
  position: relative;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
  min-width: 0;
}

.avatar-ring {
  flex-shrink: 0;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  padding: 2px;
  background: conic-gradient(from 180deg, var(--astro-primary), #5eb8ff, var(--astro-primary));
}

.avatar-inner {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  background: #0a1120;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  font-weight: 800;
  color: var(--astro-primary);
}

.header-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.name-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.name-row h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 800;
  color: #fff;
}

.badge-explorer {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 10px;
  border-radius: 999px;
  border: 1px solid rgba(19, 210, 184, 0.25);
  background: rgba(19, 210, 184, 0.06);
  color: var(--astro-primary);
  font-size: 11px;
  font-weight: 600;
}

.header-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  color: #566a87;
  font-family: 'Space Mono', monospace;
}

.meta-sep {
  color: #2a3d5a;
  font-size: 12px;
}

.header-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.btn-icon {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  border: 1px solid var(--astro-border);
  background: rgba(255, 255, 255, 0.03);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-icon:hover {
  border-color: rgba(19, 210, 184, 0.4);
  color: var(--astro-primary);
}

.btn-icon.danger:hover {
  border-color: rgba(239, 68, 68, 0.4);
  color: var(--error-color);
}

.btn-icon:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* ===== Quick Access ===== */
.quick-access {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1px;
  background: var(--astro-border);
  border: 1px solid var(--astro-border);
  border-top: none;
}

.access-card,
.access-stat {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 18px;
  background: rgba(10, 17, 32, 0.75);
  border: none;
  cursor: pointer;
  transition: background 0.15s;
  text-align: left;
}

.access-stat {
  cursor: default;
}

.access-card:hover {
  background: rgba(16, 25, 42, 0.95);
}

.access-icon {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.access-icon.blue { background: rgba(31, 111, 235, 0.12); color: #5b9cf5; }
.access-icon.amber { background: rgba(245, 158, 11, 0.12); color: #f5b731; }
.access-icon.purple { background: rgba(139, 92, 246, 0.12); color: #a78bfa; }
.access-icon.cyan { background: rgba(19, 210, 184, 0.12); color: var(--astro-primary); }

.access-body {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.access-body strong {
  font-size: 20px;
  font-weight: 800;
  font-family: 'Space Mono', monospace;
  color: #fff;
  line-height: 1.1;
}

.access-body span {
  font-size: 12px;
  color: var(--text-secondary);
}

.access-arrow {
  color: #2a3d5a;
  margin-left: auto;
  flex-shrink: 0;
  transition: color 0.15s;
}

.access-card:hover .access-arrow {
  color: var(--text-secondary);
}

/* ===== History Section ===== */
.history-section {
  border: 1px solid var(--astro-border);
  border-top: none;
  background: rgba(8, 14, 26, 0.6);
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 300px;
}

.path-section {
  border: 1px solid var(--astro-border);
  border-top: none;
  background: rgba(8, 14, 26, 0.6);
  display: flex;
  flex-direction: column;
}

.path-loading,
.path-empty {
  padding: 28px 24px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.path-empty .de-icon {
  color: #263a5a;
}

.path-grid {
  padding: 14px 20px 16px;
  display: grid;
  /* 固定 6 列，只显示一行卡片，后面的剪掉不展示，让"问答历史"能往上顶 */
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
}

@media (max-width: 1180px) {
  .path-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .path-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.path-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 14px 12px;
  border: 1px solid var(--astro-border);
  background: rgba(6, 12, 22, 0.55);
  color: inherit;
  text-align: left;
  cursor: pointer;
  border-radius: 2px;
  transition: border-color 0.15s, background 0.15s, transform 0.15s;
}

.path-card:hover {
  border-color: var(--astro-primary);
  background: rgba(19, 210, 184, 0.06);
  transform: translateY(-1px);
}

.path-card-top {
  display: flex;
  align-items: center;
  gap: 10px;
}

.path-hop {
  font-size: 11px;
  color: var(--astro-primary);
  letter-spacing: 0.6px;
  padding: 2px 6px;
  border: 1px solid rgba(19, 210, 184, 0.3);
  border-radius: 2px;
  font-variant-numeric: tabular-nums;
}

.path-name {
  font-size: 14px;
  color: var(--text-primary);
  font-weight: 600;
  letter-spacing: 0.3px;
}

.path-reason {
  margin: 0;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.55;
  min-height: 34px;
}

.path-card-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-top: 6px;
  border-top: 1px dashed var(--astro-border);
}

.path-query {
  font-size: 11.5px;
  color: var(--text-secondary);
  font-style: italic;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.path-arrow {
  color: var(--astro-primary);
  flex-shrink: 0;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 18px 24px;
  border-bottom: 1px solid var(--astro-border);
}

.section-title-group {
  display: flex;
  align-items: center;
  gap: 10px;
}

.section-icon {
  color: var(--astro-primary);
}

.section-title-group h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

.section-hint {
  font-size: 12px;
  color: #4a5e78;
}

/* ===== History Feed ===== */
.history-feed {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}

.feed-card {
  display: flex;
  gap: 0;
  border-bottom: 1px solid rgba(26, 37, 58, 0.6);
  transition: background 0.12s;
}

.feed-card:last-child {
  border-bottom: none;
}

.feed-card:hover {
  background: rgba(19, 210, 184, 0.015);
}

.feed-index {
  width: 56px;
  flex-shrink: 0;
  display: flex;
  justify-content: center;
  padding-top: 20px;
}

.feed-num {
  font-family: 'Space Mono', monospace;
  font-size: 13px;
  color: #2a3d5a;
  font-weight: 600;
}

.feed-content {
  flex: 1;
  padding: 16px 20px 16px 0;
  min-width: 0;
}

.feed-question {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  cursor: pointer;
  margin-bottom: 10px;
}

.q-badge,
.a-badge {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 800;
  margin-top: 1px;
}

.q-badge {
  background: rgba(31, 111, 235, 0.15);
  color: #5b9cf5;
}

.a-badge {
  background: rgba(19, 210, 184, 0.12);
  color: var(--astro-primary);
}

.q-text {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.5;
}

.feed-answer {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  margin-left: 0;
}

.a-text {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.7;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.feed-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
  margin-left: 34px;
}

.feed-time {
  font-size: 11px;
  color: #3a4e6a;
  font-family: 'Space Mono', monospace;
}

.feed-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  opacity: 0;
  transition: opacity 0.15s;
}

.feed-card:hover .feed-actions {
  opacity: 1;
}

.feed-btn-continue,
.feed-btn-delete {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 30px;
  border-radius: 6px;
  border: 1px solid transparent;
  background: transparent;
  cursor: pointer;
  transition: all 0.12s;
  vertical-align: middle;
}

.feed-btn-continue {
  gap: 4px;
  padding: 0 12px;
  font-size: 12px;
  font-weight: 500;
  color: var(--astro-primary);
  border-color: rgba(19, 210, 184, 0.25);
}

.feed-btn-continue:hover {
  background: rgba(19, 210, 184, 0.08);
  border-color: rgba(19, 210, 184, 0.4);
}

.feed-btn-delete {
  width: 30px;
  color: #566a87;
}

.feed-btn-delete:hover {
  color: var(--error-color);
  background: rgba(239, 68, 68, 0.08);
  border-color: rgba(239, 68, 68, 0.3);
}

.feed-btn-delete:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

/* ===== Empty History ===== */
.empty-history {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 60px 24px;
  gap: 8px;
}

.empty-visual {
  width: 88px;
  height: 88px;
  border-radius: 50%;
  background: rgba(19, 210, 184, 0.05);
  border: 1px solid rgba(19, 210, 184, 0.12);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 12px;
}

.empty-main-icon {
  color: #1e3a54;
}

.empty-history h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
}

.empty-history p {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary);
  max-width: 340px;
}

.btn-cta {
  margin-top: 16px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 22px;
  border: 1px solid var(--astro-primary);
  border-radius: 8px;
  background: rgba(19, 210, 184, 0.08);
  color: var(--astro-primary);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-cta:hover {
  background: rgba(19, 210, 184, 0.18);
}

/* ===== Drawer ===== */
.drawer-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  z-index: 2000;
  display: flex;
  justify-content: flex-end;
}

.drawer-panel {
  width: min(420px, 90vw);
  height: 100%;
  background: #0b1321;
  border-left: 1px solid var(--astro-border);
  display: flex;
  flex-direction: column;
  box-shadow: -8px 0 30px rgba(0, 0, 0, 0.4);
}

.drawer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid var(--astro-border);
}

.drawer-header h3 {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

.btn-close {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  border: 1px solid var(--astro-border);
  background: transparent;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.12s;
}

.btn-close:hover {
  border-color: rgba(239, 68, 68, 0.4);
  color: var(--error-color);
}

.drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px 0;
}

.drawer-list {
  display: flex;
  flex-direction: column;
}

.drawer-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 24px;
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition: background 0.12s;
  border-bottom: 1px solid rgba(26, 37, 58, 0.5);
}

.drawer-item:last-child {
  border-bottom: none;
}

.drawer-item:hover {
  background: rgba(255, 255, 255, 0.02);
}

.drawer-item.with-action {
  cursor: default;
}

.di-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--astro-primary);
  flex-shrink: 0;
  opacity: 0.5;
}

.di-star-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: rgba(245, 158, 11, 0.1);
  color: #f5b731;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.di-spark-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: rgba(139, 92, 246, 0.1);
  color: #a78bfa;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.di-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.di-body.clickable {
  cursor: pointer;
  background: transparent;
  border: none;
  padding: 0;
  text-align: left;
}

.di-body strong {
  font-size: 14px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.di-body span {
  font-size: 12px;
  color: var(--text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.di-body small {
  font-size: 11px;
  color: #3a4e6a;
  font-family: 'Space Mono', monospace;
}

.di-arrow {
  color: #2a3d5a;
  flex-shrink: 0;
  transition: color 0.12s;
}

.drawer-item:hover .di-arrow {
  color: var(--astro-primary);
}

.di-delete {
  width: 30px;
  height: 30px;
  border-radius: 6px;
  border: 1px solid transparent;
  background: transparent;
  color: #566a87;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.12s;
}

.di-delete:hover {
  border-color: rgba(239, 68, 68, 0.3);
  color: var(--error-color);
  background: rgba(239, 68, 68, 0.06);
}

.di-delete:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.drawer-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 24px;
  gap: 8px;
  text-align: center;
}

.de-icon {
  color: #1e3a54;
  margin-bottom: 8px;
}

.drawer-empty p {
  margin: 0;
  font-size: 14px;
  color: var(--text-primary);
  font-weight: 600;
}

.drawer-empty span {
  font-size: 12px;
  color: var(--text-secondary);
}

/* ===== Drawer Transition ===== */
.drawer-enter-active,
.drawer-leave-active {
  transition: opacity 0.2s ease;
}

.drawer-enter-active .drawer-panel,
.drawer-leave-active .drawer-panel {
  transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}

.drawer-enter-from,
.drawer-leave-to {
  opacity: 0;
}

.drawer-enter-from .drawer-panel,
.drawer-leave-to .drawer-panel {
  transform: translateX(100%);
}

/* ===== Responsive ===== */
@media (max-width: 900px) {
  .quick-access {
    grid-template-columns: repeat(2, 1fr);
  }

  .header-content {
    flex-wrap: wrap;
  }
}

@media (max-width: 600px) {
  .quick-access {
    grid-template-columns: 1fr;
  }

  .header-left {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .feed-index {
    width: 40px;
  }
}
</style>
