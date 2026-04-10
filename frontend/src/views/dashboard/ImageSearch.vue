<script setup lang="ts">
import { ElMessage } from "element-plus";
import { onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { getImageIndexStatus, imageSearchByImage, imageSearchByText, saveFavorite, triggerImageIndex } from "../../api";
import { Star } from "lucide-vue-next";

type SearchItem = {
  id: string;
  title: string;
  source: string;
  score: number;
  snippet: string;
  image_url?: string | null;
};

const route = useRoute();
const imageTextQuery = ref("木星");
const imageSearchResults = ref<SearchItem[]>([]);
const imageFile = ref<File | null>(null);
const isSearching = ref(false);
const activeTab = ref("text");
const uploadedPreview = ref("");
const page = ref(1);
const pageSize = ref(12);
const hasNext = ref(false);
const searchMode = ref("");
const searchNote = ref("");
const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
const indexStatus = ref<any>(null);
const indexBusy = ref(false);
const previewVisible = ref(false);
const previewItem = ref<SearchItem | null>(null);
const favoriteBusyId = ref<string>("");
const starredIds = ref<Set<string>>(new Set());
let indexTimer: number | null = null;

async function runImageTextSearch(resetPage = true) {
  if (!imageTextQuery.value.trim()) return;
  if (resetPage) page.value = 1;
  isSearching.value = true;
  try {
    const res = await imageSearchByText(imageTextQuery.value.trim(), page.value, pageSize.value);
    imageSearchResults.value = res.items ?? [];
    hasNext.value = Boolean(res.has_next);
    searchMode.value = res.mode ?? "";
    searchNote.value = res.note ?? "";
  } finally {
    isSearching.value = false;
  }
}

function revokePreview() {
  if (uploadedPreview.value) {
    URL.revokeObjectURL(uploadedPreview.value);
    uploadedPreview.value = "";
  }
}

function onPickFile(event: Event) {
  const input = event.target as HTMLInputElement;
  imageFile.value = input.files?.[0] ?? null;
  revokePreview();
  uploadedPreview.value = imageFile.value ? URL.createObjectURL(imageFile.value) : "";
}

async function runImageSearchByImage(resetPage = true) {
  if (!imageFile.value) return;
  if (resetPage) page.value = 1;
  isSearching.value = true;
  try {
    const res = await imageSearchByImage(imageFile.value, page.value, pageSize.value);
    imageSearchResults.value = res.items ?? [];
    hasNext.value = Boolean(res.has_next);
    searchMode.value = res.mode ?? "";
    searchNote.value = res.note ?? "";
  } finally {
    isSearching.value = false;
  }
}

function nextPage() {
  if (!hasNext.value) return;
  page.value += 1;
  if (activeTab.value === "text") void runImageTextSearch(false);
  else void runImageSearchByImage(false);
}

function prevPage() {
  if (page.value <= 1) return;
  page.value -= 1;
  if (activeTab.value === "text") void runImageTextSearch(false);
  else void runImageSearchByImage(false);
}

function resolveImageUrl(url?: string | null) {
  if (!url) return "";
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  return `${API_BASE}${url}`;
}

function shouldShowNote() {
  return Boolean(searchNote.value) && searchMode.value !== "clip_milvus";
}

async function refreshIndexStatus() {
  try {
    indexStatus.value = await getImageIndexStatus();
  } catch {
    // keep page responsive
  }
}

async function startIndex(force = false) {
  if (indexBusy.value) return;
  indexBusy.value = true;
  try {
    await triggerImageIndex(force);
    await refreshIndexStatus();
  } finally {
    indexBusy.value = false;
  }
}

function readRouteQuery() {
  const q = typeof route.query.q === "string" ? route.query.q.trim() : "";
  if (!q) return;
  imageTextQuery.value = q;
  activeTab.value = "text";
  void runImageTextSearch(true);
}

function openPreview(item: SearchItem) {
  previewItem.value = item;
  previewVisible.value = true;
}

async function copyImage(item?: SearchItem | null) {
  if (!item) return;
  const url = resolveImageUrl(item.image_url);
  if (!url) return;
  try {
    await navigator.clipboard.writeText(url);
    ElMessage.success("图片地址已复制");
  } catch {
    ElMessage.error("复制失败，请手动复制链接");
  }
}

function downloadImage(item?: SearchItem | null) {
  if (!item) return;
  const url = resolveImageUrl(item.image_url);
  if (!url) return;
  const link = document.createElement("a");
  link.href = url;
  link.download = `${item.title || "astro-image"}.png`;
  link.target = "_blank";
  link.rel = "noreferrer";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

async function collectItem(item: SearchItem) {
  if (!item.title || favoriteBusyId.value) return;
  if (starredIds.value.has(item.id)) return;
  favoriteBusyId.value = item.id;
  try {
    const result = await saveFavorite({
      title: item.title,
      category: "图像检索",
      image_url: item.image_url || null,
      source_query: imageTextQuery.value || item.title
    });
    if (result?.ok) {
      starredIds.value = new Set([...starredIds.value, item.id]);
      ElMessage.success("已收藏");
    } else {
      ElMessage.warning(result?.message || "收藏未成功");
    }
  } catch (e) {
    console.error("collectItem error:", e);
    ElMessage.error("收藏失败，请检查登录状态");
  } finally {
    favoriteBusyId.value = "";
  }
}

onMounted(() => {
  void refreshIndexStatus();
  readRouteQuery();
  indexTimer = window.setInterval(() => {
    if (indexBusy.value) return;
    const running = Boolean(indexStatus.value?.running);
    if (running) {
      void refreshIndexStatus();
    }
  }, 3000);
});

onUnmounted(() => {
  revokePreview();
  if (indexTimer !== null) {
    window.clearInterval(indexTimer);
    indexTimer = null;
  }
});

watch(
  () => route.fullPath,
  () => {
    readRouteQuery();
  }
);
</script>

<template>
  <div class="image-search-view">
    <el-card class="surface-card">
      <div class="page-head">
        <p class="panel-title">图像检索与观测样本探索</p>
        <p class="panel-subtitle">支持以文搜图和以图搜图，可从问答页继续追踪相关天体图像。</p>
      </div>

      <div class="index-status" v-if="indexStatus">
        <div class="index-text">
          <strong>向量索引状态：</strong>
          <span>{{ indexStatus.state || "idle" }}</span>
          <span class="sep">|</span>
          <span>已索引 {{ indexStatus.indexed_vectors ?? 0 }}</span>
          <span class="sep">|</span>
          <span>{{ indexStatus.message || "-" }}</span>
        </div>
        <div class="index-actions">
          <el-button size="small" :loading="indexBusy || !!indexStatus.running" @click="startIndex(false)">自动补全索引</el-button>
          <el-button size="small" text :loading="indexBusy" @click="startIndex(true)">强制重建</el-button>
        </div>
      </div>

      <el-tabs v-model="activeTab" @tab-change="() => (page = 1)">
        <el-tab-pane label="以文搜图" name="text">
          <div class="search-panel">
            <el-input v-model="imageTextQuery" placeholder="输入天体名称、类别或观测对象，例如：木星 / black hole / 旋涡星系" />
            <el-button type="primary" :loading="isSearching" @click="runImageTextSearch(true)">开始检索</el-button>
          </div>
        </el-tab-pane>

        <el-tab-pane label="以图搜图" name="image">
          <div class="search-panel vertical">
            <div class="upload-box">
              <input type="file" @change="onPickFile" accept="image/*" />
              <p class="upload-tip">{{ imageFile ? `已选择：${imageFile.name}` : "上传一张天文图片进行内容相似检索" }}</p>
            </div>
            <div class="actions-row">
              <el-button type="primary" :disabled="!imageFile || isSearching" :loading="isSearching" @click="runImageSearchByImage(true)">以图搜图</el-button>
            </div>
            <img v-if="uploadedPreview" :src="uploadedPreview" class="preview-image" alt="已上传图片预览" />
          </div>
        </el-tab-pane>
      </el-tabs>

      <p v-if="shouldShowNote()" class="mode-line">
        <span class="note-text">{{ searchNote }}</span>
      </p>

      <el-divider />

      <div v-if="imageSearchResults.length" class="result-grid">
        <el-card v-for="item in imageSearchResults" :key="item.id" class="result-card" shadow="never">
          <img :src="resolveImageUrl(item.image_url)" :alt="item.title" class="result-image" loading="lazy" decoding="async" @click="openPreview(item)" />
          <div class="item-header">
            <strong>{{ item.title }}</strong>
            <el-tag effect="plain">{{ item.score.toFixed(2) }}</el-tag>
          </div>
          <p class="source">{{ item.source }}</p>
          <p class="snippet">{{ item.snippet || "暂无补充说明" }}</p>
          <div class="card-actions">
            <el-button text @click="openPreview(item)">放大查看</el-button>
            <el-button text @click="downloadImage(item)">保存本地</el-button>
            <el-button text @click="copyImage(item)">复制链接</el-button>
            <span
              :class="['star-icon', { active: starredIds.has(item.id), busy: favoriteBusyId === item.id }]"
              @click.stop="collectItem(item)"
            >
              <Star :size="18" :fill="starredIds.has(item.id) ? 'currentColor' : 'none'" :stroke-width="starredIds.has(item.id) ? 0 : 1.5" />
            </span>
          </div>
        </el-card>
      </div>
      <div v-else class="result-empty">请先执行“以文搜图”或“以图搜图”，结果图片会显示在这里。</div>

      <div v-if="imageSearchResults.length" class="pager-row">
        <el-button :disabled="page <= 1 || isSearching" @click="prevPage">上一页</el-button>
        <span class="page-info">第 {{ page }} 页</span>
        <el-button :disabled="!hasNext || isSearching" @click="nextPage">下一页</el-button>
      </div>
    </el-card>

    <el-dialog v-model="previewVisible" width="860px" class="preview-dialog" :show-close="true">
      <template #header>
        <div class="dialog-head">
          <strong>{{ previewItem?.title || "图片预览" }}</strong>
          <span v-if="previewItem">匹配分数 {{ previewItem.score?.toFixed(2) }}</span>
        </div>
      </template>
      <div v-if="previewItem" class="dialog-body">
        <img :src="resolveImageUrl(previewItem.image_url)" :alt="previewItem.title" class="dialog-image" />
        <div class="dialog-copy">
          <p class="dialog-source">{{ previewItem.source }}</p>
          <p class="dialog-snippet">{{ previewItem.snippet || "暂无补充说明" }}</p>
        </div>
      </div>
      <template #footer>
        <el-button @click="previewVisible = false">关闭</el-button>
        <el-button @click="copyImage(previewItem)">复制链接</el-button>
        <el-button type="primary" @click="downloadImage(previewItem)">保存本地</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.image-search-view {
  width: 100%;
  height: 100%;
  min-height: 0;
  display: flex;
  overflow: hidden;
}

.image-search-view :deep(.el-card) {
  width: 100%;
  height: 100%;
  min-height: 0;
}

.image-search-view :deep(.el-card__body) {
  height: 100%;
  min-height: 0;
  overflow-y: auto;
}

.page-head {
  margin-bottom: 12px;
  border-bottom: 2px solid var(--astro-border);
  padding-bottom: 10px;
}

.panel-title {
  margin: 0;
  font-family: "Space Mono", monospace;
  font-weight: 800;
  font-size: 18px;
  color: var(--astro-primary);
  letter-spacing: 1.5px;
}

.panel-subtitle {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.search-panel {
  display: grid;
  grid-template-columns: 1fr 140px;
  gap: 12px;
  align-items: center;
  margin-top: 4px;
}

.search-panel.vertical {
  grid-template-columns: 1fr;
}

.actions-row,
.index-actions,
.card-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.upload-box {
  border: 1px dashed var(--astro-border);
  border-radius: 10px;
  padding: 14px;
  background: #0d1422;
}

.upload-tip,
.mode-line,
.note-text,
.source,
.snippet,
.dialog-source,
.dialog-snippet,
.result-empty,
.page-info,
.index-text {
  color: var(--text-secondary);
}

.upload-tip,
.mode-line,
.dialog-source,
.dialog-snippet,
.snippet,
.result-empty {
  font-size: 12px;
}

.preview-image {
  width: 220px;
  height: 140px;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid var(--astro-border);
}

.index-status {
  margin-bottom: 14px;
  border: 1px solid var(--astro-border);
  border-top: 2px solid var(--astro-primary);
  padding: 8px 12px;
  background: rgba(16, 25, 42, 0.4);
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
}

.sep {
  margin: 0 6px;
  opacity: 0.55;
}

.result-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

.result-card {
  border: 1px solid var(--astro-border);
  background: rgba(6, 12, 18, 0.7);
  transition: all 0.2s;
}

.result-card:hover {
  border-color: var(--astro-primary);
  background: rgba(19, 210, 184, 0.04);
}

.result-image {
  width: 100%;
  height: 180px;
  object-fit: cover;
  border-radius: 10px;
  border: 1px solid var(--astro-border);
  margin-bottom: 10px;
  cursor: zoom-in;
}

.item-header {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
}

.source {
  margin: 8px 0 6px;
  font-size: 10px;
  font-family: "Space Mono", monospace;
  color: var(--astro-primary);
  opacity: 0.8;
}

.snippet {
  margin: 0 0 10px;
  line-height: 1.6;
  min-height: 58px;
}

.card-actions {
  padding-top: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.star-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  cursor: pointer;
  color: #4a5e78;
  transition: all 0.2s ease;
  margin-left: auto;
  flex-shrink: 0;
}

.star-icon:hover {
  color: #f5b731;
  background: rgba(245, 158, 11, 0.1);
}

.star-icon.active {
  color: #f5b731;
}

.star-icon.active:hover {
  color: #d49a26;
}

.star-icon.busy {
  opacity: 0.4;
  pointer-events: none;
}

.result-empty {
  text-align: center;
  padding: 18px 0 8px;
}

.pager-row {
  margin-top: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
}

.dialog-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.dialog-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 260px;
  gap: 18px;
}

.dialog-image {
  width: 100%;
  max-height: 68vh;
  object-fit: contain;
  border: 1px solid var(--astro-border);
  border-radius: 12px;
  background: rgba(0, 0, 0, 0.25);
}

.dialog-copy {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.dialog-source {
  margin: 0;
  color: var(--astro-primary);
}

.dialog-snippet {
  margin: 0;
  line-height: 1.7;
}

@media (max-width: 980px) {
  .search-panel,
  .dialog-body {
    grid-template-columns: 1fr;
  }
}
</style>
