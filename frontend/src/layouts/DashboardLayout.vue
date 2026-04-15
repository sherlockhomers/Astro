<script setup lang="ts">
import { onMounted, onUnmounted, onErrorCaptured, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { logout } from "../api";
import {
  MessageSquare,
  Image as ImageIcon,
  Network,
  Globe2,
  User,
  Home,
  Satellite,
  LogOut,
  WifiOff,
  RefreshCw
} from "lucide-vue-next";

const router = useRouter();
const route = useRoute();
let prefetchHandle: number | null = null;
const renderError = ref(false);
const renderErrorMessage = ref("");

onErrorCaptured((err) => {
  const msg = err instanceof Error ? err.message : String(err);
  if (msg.includes("Network Error") || msg.includes("ERR_CONNECTION") || msg.includes("fetch")) {
    renderError.value = true;
    renderErrorMessage.value = "后端服务暂时不可用，请检查后端是否已启动。";
  } else {
    renderError.value = true;
    renderErrorMessage.value = msg || "页面渲染出现异常，请刷新重试。";
  }
  return false;
});

function retryConnection() {
  renderError.value = false;
  renderErrorMessage.value = "";
  router.go(0);
}

const navItems = [
  { name: "智能问答", desc: "围绕天文问题进行自然对话与科普讲解", path: "/app/qa", icon: MessageSquare },
  { name: "图像检索", desc: "支持以文搜图和以图搜图", path: "/app/image-search", icon: ImageIcon },
  { name: "知识探索", desc: "查看实体关系、路径发现与图谱子图", path: "/app/knowledge", icon: Network },
  { name: "3D 可视化星图", desc: "查询并观察常见天体的三维模型", path: "/app/starfield", icon: Globe2 },
  { name: "个人中心", desc: "查看账号信息、收藏和探索记录", path: "/app/profile", icon: User }
];

function goHome() {
  router.push("/");
}

async function signOut() {
  try {
    await logout();
  } finally {
    router.push("/login");
  }
}

function prefetchDashboardChunks() {
  void Promise.allSettled([
    import("../views/dashboard/ImageSearch.vue"),
    import("../views/dashboard/Knowledge.vue"),
    import("../views/dashboard/Starfield.vue"),
    import("../views/dashboard/Profile.vue"),
    import("../components/GraphChart.vue"),
    import("../components/EntityCompareChart.vue"),
    import("../components/CelestialModel3D.vue")
  ]);
}

onMounted(() => {
  const idleCallback = (window as typeof window & {
    requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number;
  }).requestIdleCallback;

  if (typeof idleCallback === "function") {
    prefetchHandle = idleCallback(() => {
      prefetchDashboardChunks();
    }, { timeout: 1500 });
    return;
  }

  prefetchHandle = window.setTimeout(() => {
    prefetchDashboardChunks();
  }, 900);
});

onUnmounted(() => {
  if (prefetchHandle === null) return;
  const cancelIdleCallback = (window as typeof window & {
    cancelIdleCallback?: (id: number) => void;
  }).cancelIdleCallback;
  if (typeof cancelIdleCallback === "function") {
    cancelIdleCallback(prefetchHandle);
  } else {
    window.clearTimeout(prefetchHandle);
  }
  prefetchHandle = null;
});
</script>

<template>
  <div class="dashboard-layout">
    <aside class="sidebar surface-card">
      <div class="brand">
        <Satellite class="brand-icon" />
        <div class="brand-text">
          <p class="brand-title">ASTRO</p>
          <p class="brand-subtitle">天文科普智能探索系统</p>
        </div>
      </div>

      <nav class="nav-menu">
        <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: route.path.startsWith(item.path) }"
        >
          <component :is="item.icon" class="icon" />
          <div>
            <p class="nav-name">{{ item.name }}</p>
            <p class="nav-desc">{{ item.desc }}</p>
          </div>
        </router-link>
      </nav>

      <div class="sidebar-footer">
        <button class="footer-btn primary" @click="goHome">
          <Home class="footer-icon" />
          返回首页
        </button>
        <button class="footer-btn secondary" @click="signOut">
          <LogOut class="footer-icon" />
          退出登录
        </button>
      </div>
    </aside>

    <main class="main-content">
      <section class="content-wrapper">
        <div v-if="renderError" class="error-overlay">
          <WifiOff :size="48" class="error-icon" />
          <h2 class="error-title">服务暂时不可用</h2>
          <p class="error-desc">{{ renderErrorMessage }}</p>
          <button class="error-retry" @click="retryConnection">
            <RefreshCw :size="15" />
            重新连接
          </button>
        </div>
        <router-view v-else v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <keep-alive :max="5">
              <component :is="Component" :key="route.path" />
            </keep-alive>
          </transition>
        </router-view>
      </section>
    </main>
  </div>
</template>

<style scoped>
.dashboard-layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  height: 100vh;
  gap: 16px;
  padding: 16px;
}

.sidebar {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.brand {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 22px 18px 18px;
  border-bottom: 1px solid var(--astro-border);
  background: linear-gradient(180deg, rgba(16, 25, 42, 0.38), transparent);
}

.brand-icon {
  color: var(--astro-primary);
  width: 28px;
  height: 28px;
}

.brand-title {
  margin: 0;
  font-size: 28px;
  font-weight: 800;
  letter-spacing: 1px;
  color: var(--text-primary);
}

.brand-subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.nav-menu {
  flex: 1;
  padding: 16px 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
}

.nav-item {
  display: flex;
  gap: 12px;
  padding: 14px;
  border-radius: 14px;
  border: 1px solid transparent;
  color: inherit;
  text-decoration: none;
  transition: all 0.2s ease;
}

.nav-item:hover {
  border-color: rgba(212, 159, 74, 0.22);
  background: rgba(255, 255, 255, 0.02);
}

.nav-item.active {
  border-color: rgba(212, 159, 74, 0.35);
  background: rgba(212, 159, 74, 0.06);
}

.icon {
  width: 20px;
  height: 20px;
  margin-top: 2px;
  color: var(--astro-primary);
  flex-shrink: 0;
}

.nav-name {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

.nav-desc {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.55;
  color: var(--text-secondary);
}

.sidebar-footer {
  padding: 16px;
  border-top: 1px solid var(--astro-border);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.footer-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 38px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.footer-btn.primary {
  border: 1px solid rgba(19, 210, 184, 0.35);
  background: rgba(19, 210, 184, 0.08);
  color: var(--astro-primary);
}

.footer-btn.primary:hover {
  background: rgba(19, 210, 184, 0.15);
  border-color: rgba(19, 210, 184, 0.5);
}

.footer-btn.secondary {
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.02);
  color: var(--text-secondary);
}

.footer-btn.secondary:hover {
  border-color: rgba(239, 68, 68, 0.3);
  color: var(--error-color);
  background: rgba(239, 68, 68, 0.05);
}

.footer-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.main-content {
  min-width: 0;
  min-height: 0;
}

.content-wrapper {
  height: 100%;
  min-height: 0;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(6px);
}

@media (max-width: 1180px) {
  .dashboard-layout {
    grid-template-columns: 280px 1fr;
  }
}

.error-overlay {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  gap: 12px;
  padding: 40px;
}

.error-icon {
  color: #ef4444;
  opacity: 0.7;
}

.error-title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
}

.error-desc {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary);
  max-width: 400px;
  line-height: 1.6;
}

.error-retry {
  margin-top: 8px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 24px;
  border: 1px solid var(--astro-primary);
  border-radius: 8px;
  background: rgba(19, 210, 184, 0.08);
  color: var(--astro-primary);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.error-retry:hover {
  background: rgba(19, 210, 184, 0.18);
}

@media (max-width: 980px) {
  .dashboard-layout {
    grid-template-columns: 1fr;
    height: auto;
    min-height: 100vh;
  }
}
</style>
