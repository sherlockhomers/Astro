<script setup lang="ts">
import { defineAsyncComponent, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { getModel3D } from "../../api";
import { Search, Globe2 } from "lucide-vue-next";

const CelestialModel3D = defineAsyncComponent(() => import("../../components/CelestialModel3D.vue"));
const route = useRoute();

const modelQuery = ref("地球");
const modelLoading = ref(false);
const modelError = ref("");
const modelResult = ref<any>(null);

async function searchModel() {
  const q = modelQuery.value.trim();
  if (!q) return;
  modelLoading.value = true;
  modelError.value = "";
  try {
    const res = await getModel3D(q);
    if (!res?.ok) {
      modelResult.value = null;
      modelError.value = res?.message || "未找到匹配天体";
      return;
    }
    modelResult.value = res;
  } catch {
    modelError.value = "3D 模型检索失败，请检查后端服务";
    modelResult.value = null;
  } finally {
    modelLoading.value = false;
  }
}

function applyRouteContext() {
  const q = typeof route.query.q === "string" ? route.query.q.trim() : "";
  if (!q) return;
  modelQuery.value = q;
  searchModel();
}

onMounted(() => {
  applyRouteContext();
  if (!route.query.q) searchModel();
});

watch(
  () => route.fullPath,
  () => {
    applyRouteContext();
  }
);
</script>

<template>
  <div class="starfield-view">
    <div class="search-bar">
      <div class="search-input-wrap">
        <Search :size="16" class="search-icon" />
        <input
          v-model="modelQuery"
          class="search-input"
          placeholder="输入天体名称搜索 3D 模型，例如：地球、木星、黑洞"
          @keyup.enter="searchModel"
        />
      </div>
      <button class="search-btn" :disabled="modelLoading" @click="searchModel">
        {{ modelLoading ? '检索中...' : '搜索' }}
      </button>
    </div>

    <el-alert v-if="modelError" type="warning" :closable="false" show-icon class="error-alert">{{ modelError }}</el-alert>

    <div class="viewer-area">
      <CelestialModel3D
        v-if="modelResult?.model"
        :model="modelResult.model"
        :title="`3D 天体：${modelResult.entity?.name || modelQuery}`"
      />
      <div v-else class="model-empty">
        <Globe2 :size="56" class="empty-globe" />
        <p class="empty-title">搜索天体查看 3D 模型</p>
        <p class="empty-desc">输入任意天体名称，系统会返回对应的交互式三维模型。支持鼠标拖拽旋转、滚轮缩放。</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.starfield-view {
  width: 100%;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 0;
  overflow: hidden;
}

.search-bar {
  display: flex;
  gap: 8px;
  padding: 14px 18px;
  border: 1px solid var(--astro-border);
  background: rgba(10, 17, 32, 0.8);
  flex-shrink: 0;
}

.search-input-wrap {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 14px;
  border: 1px solid var(--astro-border);
  border-radius: 8px;
  background: rgba(6, 12, 22, 0.6);
  transition: border-color 0.15s;
}

.search-input-wrap:focus-within {
  border-color: rgba(19, 210, 184, 0.4);
}

.search-icon {
  color: #4a5e78;
  flex-shrink: 0;
}

.search-input {
  flex: 1;
  border: none;
  background: transparent;
  color: var(--text-primary);
  font-size: 14px;
  padding: 10px 0;
  outline: none;
}

.search-input::placeholder {
  color: #3a4e6a;
}

.search-btn {
  padding: 10px 22px;
  border: 1px solid var(--astro-primary);
  border-radius: 8px;
  background: rgba(19, 210, 184, 0.1);
  color: var(--astro-primary);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
  flex-shrink: 0;
}

.search-btn:hover {
  background: rgba(19, 210, 184, 0.2);
}

.search-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error-alert {
  flex-shrink: 0;
}

.viewer-area {
  flex: 1;
  min-height: 0;
  border: 1px solid var(--astro-border);
  border-top: none;
  background: rgba(5, 8, 14, 0.9);
  overflow: hidden;
  position: relative;
}

.viewer-area :deep(canvas) {
  width: 100% !important;
  height: 100% !important;
}

.model-empty {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  text-align: center;
  padding: 40px;
}

.empty-globe {
  color: #1a2a42;
  margin-bottom: 8px;
}

.empty-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
}

.empty-desc {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
  max-width: 400px;
  line-height: 1.6;
}

@media (max-width: 600px) {
  .search-bar {
    flex-direction: column;
  }
}
</style>
