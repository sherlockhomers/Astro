<script setup lang="ts">
import { ElMessage } from "element-plus";
import { defineAsyncComponent, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { marked } from "marked";
import { getExploreBundle, saveFavorite, deleteFavorite, streamQuestion, streamQuestionWithImage } from "../../api";
import { Star, Plus, Copy, RefreshCw, Pencil, Check, X, Download } from "lucide-vue-next";

const GraphChart = defineAsyncComponent(() => import("../../components/GraphChart.vue"));

marked.setOptions({ gfm: true, breaks: true });

type ConfidenceLevel = "high" | "medium" | "low";

type ExploreEntry = {
  label: string;
  path: string;
  query: string;
};

type ExploreBundle = {
  query: string;
  intent: string;
  headline?: string;
  note?: string;
  focus_entity?: string;
  focus_card?: {
    name?: string;
    category?: string;
    description?: string;
    lead_image_url?: string | null;
    metrics?: Array<{ label: string; value: string }>;
  };
  related_images?: Array<{
    id: string;
    title: string;
    score: number;
    source: string;
    snippet: string;
    image_url?: string | null;
  }>;
  graph?: {
    focus?: string;
    nodes?: Array<{ id: string; name: string; category?: string; value?: number }>;
    links?: Array<{ source: string; target: string; name?: string }>;
    categories?: string[];
  };
  graph_highlights?: string[];
  compare?: {
    ok?: boolean;
    summary?: string;
    a?: string;
    b?: string;
    metrics?: Array<{ label: string; a: string; b: string }>;
  };
  model3d?: {
    ok?: boolean;
    entity?: { name?: string };
  };
  follow_ups?: string[];
  entry_points?: ExploreEntry[];
};

type ChatMessage = {
  role: "user" | "assistant";
  text: string;
  html: string;
  isTyping?: boolean;
  statusText?: string;
  stageTrail?: string[];
  citations?: string[];
  sourceQuestion?: string;
  topic?: string;
  confidence?: ConfidenceLevel;
  explore?: ExploreBundle | null;
  exploreLoading?: boolean;
  exploreError?: string;
  imagePreview?: string;
  attachmentName?: string;
  starred?: boolean;
  starId?: number | null;
  starBusy?: boolean;
  exploreExpanded?: boolean;
};

type PersistedMessage = {
  role: "user" | "assistant";
  text: string;
  citations?: string[];
  sourceQuestion?: string;
  topic?: string;
  confidence?: ConfidenceLevel;
};

const QA_PERSIST_KEY = "astro_qa_state_v3";

const route = useRoute();
const router = useRouter();
const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

const question = ref("");
const sessionId = ref("");
const asking = ref(false);
const messages = ref<ChatMessage[]>([]);
const imageFile = ref<File | null>(null);
const imagePreview = ref("");
const conversationRef = ref<HTMLElement | null>(null);
const favoriteBusy = ref(false);
const previewUrls: string[] = [];
let persistTimer: number | null = null;

const recommendedQuestions = [
  "木星为什么会有这么多卫星？",
  "如果站在土星环附近，会看到什么？",
  "黑洞为什么连光都逃不出来？",
  "火星上曾经适合生命存在吗？"
];

const knownTopics = ["黑洞", "银河系", "仙女座星系", "木星", "土星", "火星", "地球", "月球", "太阳", "海王星", "天王星", "金星", "水星", "彗星", "星云", "恒星"];

function renderMarkdown(text: string) {
  const raw = String(text || "").trim();
  if (!raw) return "";
  return String(marked.parse(raw));
}

function updateMessageRender(message: ChatMessage) {
  message.html = renderMarkdown(message.text);
}

async function scrollToBottom() {
  await nextTick();
  if (conversationRef.value) {
    conversationRef.value.scrollTop = conversationRef.value.scrollHeight;
  }
}

let _scrollRafId = 0;
function throttledScroll() {
  if (_scrollRafId) return;
  _scrollRafId = requestAnimationFrame(() => {
    _scrollRafId = 0;
    void scrollToBottom();
  });
}

let _renderTimer = 0;
function throttledRender(message: ChatMessage) {
  if (_renderTimer) return;
  _renderTimer = window.setTimeout(() => {
    _renderTimer = 0;
    updateMessageRender(message);
  }, 80);
}

function deriveExploreTopic(prompt: string) {
  const normalized = prompt.trim();
  const known = knownTopics.find((item) => normalized.includes(item));
  if (known) return known;
  const chineseMatch = normalized.match(/[\u4e00-\u9fa5]{1,8}(黑洞|星系|星云|行星|卫星|彗星|太阳|月球|地球|火星|木星|土星|海王星|天王星|金星|水星)/);
  if (chineseMatch?.[0]) return chineseMatch[0];
  return normalized.slice(0, 16);
}

function createUserMessage(text: string, previewUrl?: string, fileName?: string): ChatMessage {
  return {
    role: "user",
    text,
    html: renderMarkdown(text),
    imagePreview: previewUrl,
    attachmentName: fileName
  };
}

function createAssistantPlaceholder(prompt: string): ChatMessage {
  const message: ChatMessage = {
    role: "assistant",
    text: "",
    html: "",
    isTyping: true,
    statusText: "正在理解你的问题。",
    stageTrail: ["正在理解你的问题。"],
    citations: [],
    sourceQuestion: prompt,
    topic: deriveExploreTopic(prompt),
    confidence: "medium",
    explore: null,
    exploreLoading: true,
    exploreError: "",
    starred: false,
    starId: null,
    starBusy: false,
    exploreExpanded: false
  };
  messages.value.push(message);
  return message;
}

function toPersistedMessage(message: ChatMessage): PersistedMessage {
  return {
    role: message.role,
    text: String(message.text || ""),
    citations: Array.isArray(message.citations) ? message.citations.slice(0, 8) : [],
    sourceQuestion: message.sourceQuestion,
    topic: message.topic,
    confidence: message.confidence
  };
}

function saveQaState() {
  try {
    const payload = {
      sessionId: String(sessionId.value || ""),
      messages: messages.value
        .filter((m) => !m.isTyping)
        .slice(-30)
        .map(toPersistedMessage),
      updatedAt: Date.now()
    };
    localStorage.setItem(QA_PERSIST_KEY, JSON.stringify(payload));
  } catch {
    // ignore persistence failures
  }
}

function restoreQaState() {
  try {
    const raw = localStorage.getItem(QA_PERSIST_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw);
    const restoredMessages = Array.isArray(parsed?.messages)
      ? parsed.messages.map((item: PersistedMessage) => ({
          role: item.role === "user" ? "user" : "assistant",
          text: String(item.text || ""),
          html: renderMarkdown(String(item.text || "")),
          isTyping: false,
          citations: Array.isArray(item.citations) ? item.citations : [],
          sourceQuestion: item.sourceQuestion,
          topic: item.topic,
          confidence: item.confidence
        }))
      : [];
    if (restoredMessages.length) {
      messages.value = restoredMessages;
    }
    sessionId.value = String(parsed?.sessionId || "");
  } catch {
    // ignore corrupted cache
  }
}

function schedulePersist() {
  if (persistTimer) {
    window.clearTimeout(persistTimer);
  }
  persistTimer = window.setTimeout(() => {
    persistTimer = null;
    saveQaState();
  }, 220);
}

function confidenceLabel(level?: ConfidenceLevel) {
  if (level === "high") return "回答把握度：高";
  if (level === "low") return "回答把握度：低";
  return "回答把握度：中";
}

function recordStage(message: ChatMessage, text: string) {
  const normalized = String(text || "").trim();
  if (!normalized) return;
  message.statusText = normalized;
  const trail = Array.isArray(message.stageTrail) ? message.stageTrail : [];
  if (trail[trail.length - 1] === normalized) return;
  message.stageTrail = [...trail, normalized].slice(-4);
}

async function hydrateExplore(message: ChatMessage, prompt: string) {
  message.exploreLoading = true;
  message.exploreError = "";
  try {
    const bundle = await getExploreBundle(prompt);
    message.explore = bundle;
  } catch {
    message.explore = null;
    message.exploreError = "延展探索内容暂时没有成功返回。";
  } finally {
    message.exploreLoading = false;
    await scrollToBottom();
  }
}

async function collectFocus(msg: ChatMessage) {
  const name = msg.explore?.focus_card?.name;
  if (!name || favoriteBusy.value) return;
  favoriteBusy.value = true;
  try {
    const result = await saveFavorite({
      title: name,
      category: msg.explore?.focus_card?.category || "天体",
      image_url: msg.explore?.focus_card?.lead_image_url || null,
      source_query: msg.sourceQuestion || name
    });
    if (result?.ok) {
      msg.starred = true;
      msg.starId = result.id ?? null;
      ElMessage.success(result.message || "已加入收藏");
    } else {
      ElMessage.warning(result?.message || "收藏未成功");
    }
  } catch {
    ElMessage.error("收藏失败");
  } finally {
    favoriteBusy.value = false;
  }
}

async function toggleStar(msg: ChatMessage) {
  if (msg.starBusy) return;
  msg.starBusy = true;
  try {
    if (msg.starred && msg.starId) {
      await deleteFavorite(msg.starId);
      msg.starred = false;
      msg.starId = null;
      ElMessage.success("已取消收藏");
    } else {
      const title = msg.explore?.focus_card?.name || msg.topic || msg.sourceQuestion || "天文收藏";
      const result = await saveFavorite({
        title,
        category: msg.explore?.focus_card?.category || "天体",
        image_url: msg.explore?.focus_card?.lead_image_url || null,
        source_query: msg.sourceQuestion || title
      });
      if (result?.ok) {
        msg.starred = true;
        msg.starId = result.id ?? null;
        ElMessage.success("已收藏");
      } else {
        ElMessage.warning(result?.message || "收藏未成功");
      }
    }
  } catch (e) {
    console.error("toggleStar error:", e);
    ElMessage.error("收藏操作失败，请检查登录状态");
  } finally {
    msg.starBusy = false;
  }
}

async function submitQuestion(overrideQuestion?: string) {
  if (asking.value) return;
  const normalizedPrompt = String(overrideQuestion ?? question.value).trim();
  const prompt = normalizedPrompt || (imageFile.value ? "这是什么天体？" : "");
  if (!prompt) return;

  const previewUrl = imageFile.value ? imagePreview.value : "";
  const fileName = imageFile.value?.name || "";
  const userText = imageFile.value ? `[附图] ${prompt}` : prompt;
  messages.value.push(createUserMessage(userText, previewUrl || undefined, fileName || undefined));
  if (!overrideQuestion) {
    question.value = "";
  }
  asking.value = true;
  await scrollToBottom();

  const assistant = createAssistantPlaceholder(prompt);
  void hydrateExplore(assistant, prompt);
  await scrollToBottom();

  try {
    if (imageFile.value) {
      recordStage(assistant, "已收到图片，正在识别主体。");
      const file = imageFile.value;
      await streamQuestionWithImage(prompt, file, sessionId.value || undefined, {
        onStatus(payload) {
          recordStage(assistant, String(payload?.message || "正在分析图片并组织回答。"));
          throttledScroll();
        },
        onDelta(payload) {
          assistant.text += String(payload?.text || "");
          throttledRender(assistant);
          throttledScroll();
        },
        onDone(payload) {
          sessionId.value = payload?.session_id ?? sessionId.value;
          assistant.text = String(payload?.answer || assistant.text || "");
          assistant.citations = Array.isArray(payload?.citations) ? payload.citations : [];
          assistant.confidence = (payload?.confidence || "medium") as ConfidenceLevel;
          assistant.isTyping = false;
          assistant.statusText = "";
          updateMessageRender(assistant);
          void scrollToBottom();
        },
        onError(messageText) {
          assistant.text = messageText || "这次图片问答没有成功返回，请稍后再试。";
          assistant.isTyping = false;
          assistant.statusText = "";
          updateMessageRender(assistant);
          void scrollToBottom();
        }
      });
      imageFile.value = null;
      imagePreview.value = "";
      return;
    }

    await streamQuestion(prompt, sessionId.value || undefined, {
      onStatus(payload) {
        recordStage(assistant, String(payload?.message || "正在整理回答。"));
        throttledScroll();
      },
      onDelta(payload) {
        assistant.text += String(payload?.text || "");
        throttledRender(assistant);
        throttledScroll();
      },
      onDone(payload) {
        sessionId.value = payload?.session_id ?? sessionId.value;
        assistant.text = String(payload?.answer || assistant.text || "");
        assistant.citations = Array.isArray(payload?.citations) ? payload.citations : [];
        assistant.confidence = (payload?.confidence || "medium") as ConfidenceLevel;
        assistant.isTyping = false;
        assistant.statusText = "";
        updateMessageRender(assistant);
        void scrollToBottom();
      },
      onError(messageText) {
        assistant.text = messageText || "这次回答没有成功返回，请稍后再试。";
        assistant.isTyping = false;
        assistant.statusText = "";
        updateMessageRender(assistant);
        void scrollToBottom();
      }
    });
  } catch {
    if (!assistant.text) {
      assistant.text = "这次回答没有成功返回，请稍后再试。";
      updateMessageRender(assistant);
    }
    assistant.isTyping = false;
    assistant.statusText = "";
  } finally {
    asking.value = false;
    schedulePersist();
  }
}

function setRecommendedQuestion(item: string) {
  question.value = item;
}

function askFollowUp(item: string) {
  question.value = item;
  void submitQuestion(item);
}

function loadQuestionFromRoute() {
  const q = typeof route.query.q === "string" ? route.query.q.trim() : "";
  if (!q) return;
  question.value = q;
  if (route.query.auto === "1" && !messages.value.length && !asking.value) {
    void submitQuestion(q);
  }
}

function onPickImage(event: Event) {
  const input = event.target as HTMLInputElement;
  const nextFile = input.files?.[0] ?? null;
  imageFile.value = nextFile;
  if (!nextFile) {
    imagePreview.value = "";
    return;
  }
  const url = URL.createObjectURL(nextFile);
  previewUrls.push(url);
  imagePreview.value = url;
}

function clearImage() {
  imageFile.value = null;
  imagePreview.value = "";
}

function citationLink(citation: string): string | null {
  if (citation.startsWith("http://") || citation.startsWith("https://")) return citation;
  if (citation.startsWith("image:/")) return citation.slice("image:".length);
  return null;
}

function visibleCitations(citations?: string[]) {
  return (citations ?? []).filter((citation) => Boolean(citationLink(citation)));
}

function resolveImageUrl(url?: string | null) {
  if (!url) return "";
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  return `${API_BASE}${url}`;
}

function openRoute(path: string, q: string) {
  router.push({ path, query: { q } });
}

function openImageExplore(msg: ChatMessage) {
  const q = msg.explore?.focus_entity || msg.topic || msg.sourceQuestion || msg.text.slice(0, 18);
  openRoute("/app/image-search", q);
}

function openKnowledgeExplore(msg: ChatMessage) {
  const q = msg.explore?.focus_entity || msg.topic || msg.sourceQuestion || msg.text.slice(0, 18);
  openRoute("/app/knowledge", q);
}

function openStarfieldExplore(msg: ChatMessage) {
  const q = msg.explore?.focus_entity || msg.topic || msg.sourceQuestion || msg.text.slice(0, 18);
  openRoute("/app/starfield", q);
}

function openGraphNode(name: string) {
  openRoute("/app/knowledge", name);
}

function exportConversation() {
  if (!messages.value.length) return;
  const lines: string[] = [
    "# AstroGraph 问答记录",
    `导出时间: ${new Date().toLocaleString()}`,
    `会话 ID: ${sessionId.value || "N/A"}`,
    "",
    "---",
    "",
  ];
  for (const msg of messages.value) {
    if (msg.isTyping) continue;
    if (msg.role === "user") {
      lines.push(`## 提问`);
      lines.push(msg.text);
      lines.push("");
    } else {
      lines.push(`## 回答`);
      lines.push(msg.text);
      if (msg.citations?.length) {
        lines.push("");
        lines.push("**参考来源:**");
        for (const cit of msg.citations) {
          lines.push(`- ${cit}`);
        }
      }
      lines.push("");
      lines.push("---");
      lines.push("");
    }
  }
  const blob = new Blob([lines.join("\n")], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `astro-qa-${sessionId.value || Date.now()}.md`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
  ElMessage.success("对话已导出为 Markdown 文件");
}

function startNewConversation() {
  messages.value = [];
  sessionId.value = "";
  question.value = "";
  imageFile.value = null;
  imagePreview.value = "";
  saveQaState();
}

async function copyMessageText(msg: ChatMessage) {
  try {
    await navigator.clipboard.writeText(msg.text);
    ElMessage.success("已复制到剪贴板");
  } catch {
    ElMessage.error("复制失败");
  }
}

function retryMessage(msg: ChatMessage) {
  const q = msg.role === "user" ? msg.text.replace(/^\[附图\]\s*/, "") : (msg.sourceQuestion || "");
  if (!q) return;
  void submitQuestion(q);
}

const editingIdx = ref<number | null>(null);
const editText = ref("");

function startEdit(idx: number) {
  const msg = messages.value[idx];
  if (!msg || msg.role !== "user") return;
  editingIdx.value = idx;
  editText.value = msg.text.replace(/^\[附图\]\s*/, "");
}

function cancelEdit() {
  editingIdx.value = null;
  editText.value = "";
}

function confirmEdit(idx: number) {
  const newQ = editText.value.trim();
  if (!newQ) { cancelEdit(); return; }
  messages.value = messages.value.slice(0, idx);
  editingIdx.value = null;
  editText.value = "";
  void submitQuestion(newQ);
}

onMounted(() => {
  restoreQaState();
  loadQuestionFromRoute();
  void scrollToBottom();
});

onUnmounted(() => {
  if (persistTimer) {
    window.clearTimeout(persistTimer);
    persistTimer = null;
  }
  if (_scrollRafId) cancelAnimationFrame(_scrollRafId);
  if (_renderTimer) clearTimeout(_renderTimer);
  saveQaState();
  previewUrls.forEach((url) => URL.revokeObjectURL(url));
});

watch(
  () => route.fullPath,
  () => {
    loadQuestionFromRoute();
  }
);

watch(
  () => messages.value.length,
  () => {
    schedulePersist();
  }
);

watch(sessionId, () => {
  schedulePersist();
});
</script>

<template>
  <div class="qa-page">
    <section class="qa-shell surface-card">
      <div v-if="messages.length === 0" class="empty-state">
        <div class="hero-chip">天文智能探索</div>
        <h2 class="hero-title">把一个问题，扩展成一段可视化探索过程</h2>
        <p class="hero-desc">
          你可以直接提问，也可以上传天体图片一起问。系统会先给出科普回答，再自动补上相关图像、关系图谱、3D 模型入口和继续追问建议。
        </p>
        <div class="example-list">
          <el-button v-for="item in recommendedQuestions" :key="item" class="example-chip" text @click="setRecommendedQuestion(item)">
            {{ item }}
          </el-button>
        </div>
      </div>

      <div v-else class="conversation-wrap">
        <div class="conversation-toolbar">
          <button class="toolbar-btn" @click="exportConversation" title="导出对话">
            <Download :size="15" />
            导出
          </button>
          <button class="toolbar-btn primary" @click="startNewConversation">
            <Plus :size="15" />
            新建对话
          </button>
        </div>
        <div ref="conversationRef" class="conversation">
        <div v-for="(msg, idx) in messages" :key="idx" :class="['message-row', msg.role]">
          <div class="avatar">{{ msg.role === 'user' ? '你' : 'ASTRO' }}</div>
          <div class="message-card">
            <div class="message-head">
              <span class="speaker">{{ msg.role === 'user' ? '你的提问' : '科普回答' }}</span>
              <div class="msg-actions">
                <button v-if="msg.role === 'user' && editingIdx !== idx" class="msg-action" title="编辑" @click="startEdit(idx)"><Pencil :size="13" /></button>
                <button class="msg-action" title="复制" @click="copyMessageText(msg)"><Copy :size="13" /></button>
                <button v-if="msg.role === 'user'" class="msg-action" title="重新提问" @click="retryMessage(msg)"><RefreshCw :size="13" /></button>
              </div>
            </div>

            <div v-if="editingIdx === idx" class="edit-area">
              <el-input v-model="editText" type="textarea" :rows="2" />
              <div class="edit-btns">
                <button class="edit-confirm" @click="confirmEdit(idx)"><Check :size="14" /> 确认</button>
                <button class="edit-cancel" @click="cancelEdit"><X :size="14" /> 取消</button>
              </div>
            </div>

            <div v-if="msg.imagePreview" class="message-image-wrap">
              <img :src="msg.imagePreview" :alt="msg.attachmentName || '上传图片'" class="message-image" />
              <span v-if="msg.attachmentName" class="message-file">{{ msg.attachmentName }}</span>
            </div>

            <div class="message-text markdown-body" v-html="msg.html"></div>
            <span v-if="msg.isTyping" class="cursor-blink">|</span>

            <div v-if="msg.role === 'assistant' && !msg.isTyping" class="meta-line">
              <el-tag size="small" effect="plain">{{ confidenceLabel(msg.confidence) }}</el-tag>
              <span
                :class="['star-icon', { active: msg.starred, busy: msg.starBusy }]"
                @click.stop="toggleStar(msg)"
              >
                <Star :size="18" :fill="msg.starred ? 'currentColor' : 'none'" :stroke-width="msg.starred ? 0 : 1.5" />
              </span>
            </div>

            <div v-if="!msg.isTyping && visibleCitations(msg.citations).length" class="citation-wrap">
              <span class="section-label">参考来源</span>
              <template v-for="cit in visibleCitations(msg.citations)" :key="cit">
                <a :href="citationLink(cit) || undefined" target="_blank" rel="noreferrer" class="citation-link">
                  <el-tag size="small" effect="plain">{{ cit }}</el-tag>
                </a>
              </template>
            </div>

            <div v-if="msg.role === 'assistant' && (!msg.isTyping || msg.exploreLoading)" class="explore-panel">
              <button class="explore-toggle" @click="msg.exploreExpanded = !msg.exploreExpanded">
                <span class="explore-kicker">延展探索</span>
                <span class="explore-toggle-hint">{{ msg.exploreExpanded ? '收起' : '展开查看图像、图谱与 3D 入口' }}</span>
                <span :class="['explore-arrow', { open: msg.exploreExpanded }]">▾</span>
              </button>

              <div v-if="msg.exploreLoading && msg.exploreExpanded" class="explore-loading">正在补充延展探索内容...</div>
              <div v-else-if="msg.exploreError && msg.exploreExpanded" class="explore-loading">{{ msg.exploreError }}</div>
              <template v-else-if="msg.explore">
                <div v-if="msg.exploreExpanded" class="explore-body">
                <div v-if="msg.explore.focus_card?.name" class="focus-card">
                  <div class="focus-copy">
                    <div class="focus-meta">
                      <span class="focus-name">{{ msg.explore.focus_card.name }}</span>
                      <el-tag size="small" effect="plain">{{ msg.explore.focus_card.category || '天体' }}</el-tag>
                    </div>
                    <p class="focus-desc">{{ msg.explore.focus_card.description }}</p>
                    <div v-if="msg.explore.focus_card.metrics?.length" class="metric-row">
                      <div v-for="metric in msg.explore.focus_card.metrics" :key="metric.label" class="metric-card">
                        <span class="metric-label">{{ metric.label }}</span>
                        <strong class="metric-value">{{ metric.value }}</strong>
                      </div>
                    </div>
                    <div class="focus-actions">
                      <span
                        :class="['star-icon', { active: msg.starred, busy: msg.starBusy }]"
                        @click.stop="toggleStar(msg)"
                      >
                        <Star :size="20" :fill="msg.starred ? 'currentColor' : 'none'" :stroke-width="msg.starred ? 0 : 1.5" />
                      </span>
                    </div>
                  </div>
                  <img v-if="msg.explore.focus_card.lead_image_url" :src="resolveImageUrl(msg.explore.focus_card.lead_image_url)" :alt="msg.explore.focus_card.name" class="focus-image" />
                </div>

                <div v-if="msg.explore.compare?.ok" class="compare-card">
                  <div class="section-head">
                    <span class="section-title">对比梳理</span>
                    <span class="section-tip">{{ msg.explore.compare.a }} vs {{ msg.explore.compare.b }}</span>
                  </div>
                  <p class="compare-summary">{{ msg.explore.compare.summary }}</p>
                  <div v-if="msg.explore.compare.metrics?.length" class="compare-grid">
                    <div v-for="metric in msg.explore.compare.metrics" :key="metric.label" class="compare-item">
                      <span class="metric-label">{{ metric.label }}</span>
                      <strong>{{ metric.a }}</strong>
                      <span class="compare-sep">对比</span>
                      <strong>{{ metric.b }}</strong>
                    </div>
                  </div>
                </div>

                <div class="explore-grid">
                  <div v-if="msg.explore.related_images?.length" class="explore-block">
                    <div class="section-head">
                      <span class="section-title">相关图像</span>
                      <el-button text @click="openImageExplore(msg)">查看更多</el-button>
                    </div>
                    <div class="image-grid">
                      <button v-for="item in msg.explore.related_images.slice(0, 3)" :key="item.id" class="image-card" type="button" @click="openImageExplore(msg)">
                        <img :src="resolveImageUrl(item.image_url)" :alt="item.title" class="image-thumb" />
                        <div class="image-copy">
                          <strong>{{ item.title }}</strong>
                          <span>{{ item.snippet || item.source }}</span>
                        </div>
                      </button>
                    </div>
                  </div>

                  <div v-if="msg.explore.graph?.nodes?.length" class="explore-block graph-block">
                    <div class="section-head">
                      <span class="section-title">关系子图谱</span>
                      <el-button text @click="openKnowledgeExplore(msg)">进入图谱页</el-button>
                    </div>
                    <div class="graph-preview">
                      <GraphChart
                        :nodes="msg.explore.graph.nodes"
                        :links="msg.explore.graph.links || []"
                        :categories="msg.explore.graph.categories || []"
                        :render-limit-nodes="80"
                        :render-limit-links="120"
                        @node-click="({ name }) => openGraphNode(name)"
                      />
                    </div>
                    <div v-if="msg.explore.graph_highlights?.length" class="highlight-row">
                      <el-tag v-for="item in msg.explore.graph_highlights" :key="item" size="small" effect="plain" class="highlight-tag">{{ item }}</el-tag>
                    </div>
                  </div>
                </div>

                <div class="action-row">
                  <button class="action-card" type="button" @click="openKnowledgeExplore(msg)">
                    <span class="action-title">关系图谱探索</span>
                    <span class="action-desc">围绕焦点实体查看局部关系网络与路径。</span>
                  </button>
                  <button class="action-card" type="button" @click="openStarfieldExplore(msg)">
                    <span class="action-title">3D 天体模型</span>
                    <span class="action-desc">{{ msg.explore.model3d?.ok ? `已准备 ${msg.explore.model3d.entity?.name || msg.explore.focus_entity} 的三维模型。` : '当前没有匹配的 3D 模型。' }}</span>
                  </button>
                </div>

                <div v-if="msg.explore.follow_ups?.length" class="followup-wrap">
                  <span class="section-label">推荐继续追问</span>
                  <div class="followup-row">
                    <el-button v-for="item in msg.explore.follow_ups" :key="item" class="followup-chip" text @click="askFollowUp(item)">
                      {{ item }}
                    </el-button>
                  </div>
                </div>
                </div>
              </template>
            </div>
          </div>
        </div>
      </div>
      </div>

      <div class="composer">
        <div class="upload-row">
          <label class="upload-label">
            <input type="file" accept="image/*" @change="onPickImage" />
            上传图片一起提问
          </label>
          <div v-if="imageFile" class="selected-image">
            <img v-if="imagePreview" :src="imagePreview" :alt="imageFile.name" class="selected-thumb" />
            <span class="file-name">{{ imageFile.name }}</span>
            <el-button text @click="clearImage">移除图片</el-button>
          </div>
        </div>

        <el-input
          v-model="question"
          type="textarea"
          :rows="3"
          placeholder="输入你的天文问题。你可以问概念、机制、观测发现，也可以配合图片一起提问。"
          @keyup.enter.exact.prevent="submitQuestion()"
        />

        <div class="composer-footer">
          <span class="tips">建议把问题问得更具体，例如“木星为什么会有这么多卫星？”</span>
          <el-button type="primary" :loading="asking" @click="submitQuestion()">发送</el-button>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.qa-page {
  width: 100%;
  height: 100%;
  min-height: 0;
  display: flex;
  overflow: hidden;
}

.qa-shell {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 18px;
}

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  gap: 16px;
  padding: 0 28px;
}

.hero-chip,
.example-chip,
.stage-chip,
.highlight-tag,
.followup-chip {
  border: 1px solid var(--astro-border);
  background: rgba(255, 255, 255, 0.03);
}

.hero-chip {
  padding: 6px 14px;
  border-radius: 999px;
  color: var(--astro-primary);
  font-size: 12px;
}

.hero-title {
  margin: 0;
  max-width: 760px;
  font-size: 34px;
  line-height: 1.2;
  font-weight: 800;
  color: var(--text-primary);
}

.hero-desc {
  margin: 0;
  max-width: 760px;
  line-height: 1.9;
  font-size: 14px;
  color: var(--text-secondary);
}

.example-list {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
  max-width: 860px;
}

.conversation-wrap {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.conversation-toolbar {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  padding: 0 0 10px;
  flex-shrink: 0;
}

.toolbar-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 14px;
  border: 1px solid var(--astro-border);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.02);
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.toolbar-btn:hover {
  border-color: rgba(19, 210, 184, 0.35);
  color: var(--astro-primary);
  background: rgba(19, 210, 184, 0.05);
}

.toolbar-btn.primary {
  border-color: rgba(19, 210, 184, 0.25);
  color: var(--astro-primary);
}

.conversation {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding-right: 6px;
}

.message-row {
  display: grid;
  grid-template-columns: 52px minmax(0, 1fr);
  gap: 12px;
}

.message-row.user {
  align-self: flex-end;
  width: min(920px, 100%);
}

.avatar {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  background: rgba(212, 159, 74, 0.14);
  color: var(--astro-primary);
}

.message-card {
  border: 1px solid var(--astro-border);
  border-radius: 18px;
  padding: 16px;
  background: rgba(10, 16, 27, 0.75);
}

.message-head,
.section-head,
.focus-meta,
.citation-wrap,
.upload-row,
.composer-footer,
.meta-line,
.focus-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.message-head,
.section-head,
.composer-footer {
  justify-content: space-between;
}

.speaker,
.explore-kicker,
.section-label,
.section-title,
.focus-name,
.action-title {
  color: var(--text-primary);
  font-weight: 700;
}

.status-line,
.explore-note,
.focus-desc,
.action-desc,
.section-tip,
.metric-label,
.metric-value,
.image-copy span,
.file-name,
.tips,
.message-file,
.compare-summary,
.compare-sep {
  color: var(--text-secondary);
}

.message-image-wrap {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 12px 0;
}

.message-image,
.focus-image,
.image-thumb,
.selected-thumb {
  border: 1px solid var(--astro-border);
  object-fit: cover;
}

.message-image {
  width: 220px;
  height: 150px;
  border-radius: 12px;
}

.message-file {
  font-size: 12px;
}

.message-text {
  line-height: 1.85;
}

.cursor-blink {
  display: inline-block;
  margin-top: 4px;
  animation: blink 1s step-end infinite;
}

.stage-wrap,
.explore-panel,
.focus-card,
.compare-card,
.action-card,
.metric-card {
  border: 1px solid var(--astro-border);
  background: rgba(255, 255, 255, 0.02);
}

.explore-block {
  min-width: 0;
}

.stage-wrap,
.citation-wrap,
.explore-panel {
  margin-top: 14px;
  padding-top: 12px;
}

.stage-list,
.highlight-row,
.followup-row,
.metric-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.focus-card {
  display: grid;
  grid-template-columns: 1fr 240px;
  gap: 14px;
  padding: 14px;
  border-radius: 16px;
}

.focus-image {
  width: 100%;
  height: 200px;
  border-radius: 14px;
}

.metric-row,
.compare-grid,
.explore-grid,
.action-row {
  margin-top: 14px;
}

.metric-row,
.compare-grid,
.explore-grid,
.action-row {
  display: grid;
  gap: 10px;
}

.metric-row { grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); }
.compare-grid { grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }
.explore-grid { grid-template-columns: 1fr; }
.action-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }

.metric-card,
.compare-item,
.action-card {
  padding: 12px;
  border-radius: 14px;
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  align-items: start;
}

.image-card {
  border: 1px solid var(--astro-border);
  border-radius: 10px;
  padding: 0;
  background: rgba(6, 12, 22, 0.5);
  text-align: left;
  cursor: pointer;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: border-color 0.15s;
}

.image-card:hover {
  border-color: rgba(19, 210, 184, 0.3);
}

.image-thumb {
  width: 100%;
  height: 140px;
  border-radius: 0;
  display: block;
}

.image-copy {
  padding: 8px 10px;
}

.image-copy strong {
  display: block;
  font-size: 13px;
  color: var(--text-primary);
}

.image-copy span {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-size: 12px;
  margin-top: 4px;
  line-height: 1.5;
}

.graph-preview {
  height: 260px;
  overflow: hidden;
  border-radius: 10px;
  border: 1px solid var(--astro-border);
}

.action-card {
  text-align: left;
  cursor: pointer;
}

.composer {
  margin-top: 16px;
  border-top: 1px solid var(--astro-border);
  padding-top: 14px;
}

.upload-row {
  margin-bottom: 12px;
  justify-content: flex-start;
}

.upload-label {
  border: 1px dashed var(--astro-border);
  border-radius: 12px;
  padding: 10px 14px;
  cursor: pointer;
  color: var(--astro-primary);
}

.upload-label input {
  display: none;
}

.selected-image {
  display: flex;
  align-items: center;
  gap: 10px;
}

.selected-thumb {
  width: 64px;
  height: 64px;
  border-radius: 10px;
}

@keyframes blink {
  50% { opacity: 0; }
}

/* Message Actions */
.msg-actions {
  display: flex;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.15s;
  margin-left: auto;
}

.message-card:hover .msg-actions {
  opacity: 1;
}

.msg-action {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: #4a5e78;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.12s;
}

.msg-action:hover {
  color: var(--astro-primary);
  background: rgba(19, 210, 184, 0.08);
}

.edit-area {
  margin: 10px 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.edit-btns {
  display: flex;
  gap: 8px;
}

.edit-confirm,
.edit-cancel {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 12px;
  border-radius: 6px;
  border: 1px solid var(--astro-border);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.12s;
}

.edit-confirm {
  background: rgba(19, 210, 184, 0.08);
  color: var(--astro-primary);
  border-color: rgba(19, 210, 184, 0.25);
}

.edit-confirm:hover {
  background: rgba(19, 210, 184, 0.15);
}

.edit-cancel {
  background: transparent;
  color: var(--text-secondary);
}

.edit-cancel:hover {
  color: var(--error-color);
  border-color: rgba(239, 68, 68, 0.3);
}

/* Explore Toggle */
.explore-toggle {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 12px 0;
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
}

.explore-toggle-hint {
  flex: 1;
  font-size: 12px;
  color: var(--text-secondary);
}

.explore-arrow {
  font-size: 14px;
  color: var(--text-secondary);
  transition: transform 0.2s;
}

.explore-arrow.open {
  transform: rotate(180deg);
}

.explore-body {
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Star Icon */
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

@media (max-width: 1080px) {
  .focus-card,
  .explore-grid,
  .action-row,
  .image-grid {
    grid-template-columns: 1fr;
  }
}
</style>
