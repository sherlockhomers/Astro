<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { getEvaluationReport, getInternalCapabilityReport, runEvaluation } from "../../api";

const internalToken = ref(localStorage.getItem("astro_internal_token") || "");
const loading = ref(false);
const running = ref(false);
const capability = ref<any | null>(null);
const report = ref<any | null>(null);
const error = ref("");
const showAdminPanel = ref(false);

const summaryCards = computed(() => {
  const summary = report.value?.summary || {};
  return [
    { label: "通过率", value: percent(summary.pass_rate) },
    { label: "平均得分", value: percent(summary.avg_score) },
    { label: "平均时延", value: ms(summary.avg_latency_ms) },
    { label: "P95 时延", value: ms(summary.p95_latency_ms) },
    { label: "中文输出率", value: percent(summary.chinese_output_rate) },
    { label: "数值问题合规率", value: percent(summary.numeric_compliance_rate) }
  ];
});

function percent(value?: number) {
  if (typeof value !== "number") return "--";
  return `${(value * 100).toFixed(1)}%`;
}

function ms(value?: number) {
  if (typeof value !== "number") return "--";
  return `${value.toFixed(0)} ms`;
}

function saveToken() {
  localStorage.setItem("astro_internal_token", internalToken.value.trim());
}

async function loadPanel() {
  const token = internalToken.value.trim();
  if (!token) {
    error.value = "请先输入内部评测口令。";
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    saveToken();
    const [capabilityData, reportData] = await Promise.all([
      getInternalCapabilityReport(token),
      getEvaluationReport(token)
    ]);
    capability.value = capabilityData;
    report.value = reportData;
  } catch (err: any) {
    error.value = err?.response?.data?.detail || "加载评测面板失败。请确认口令是否正确。";
  } finally {
    loading.value = false;
  }
}

async function handleRun(sampleSize: number) {
  const token = internalToken.value.trim();
  if (!token) {
    error.value = "请先输入内部评测口令。";
    return;
  }
  running.value = true;
  error.value = "";
  try {
    saveToken();
    report.value = await runEvaluation(token, sampleSize, true);
  } catch (err: any) {
    error.value = err?.response?.data?.detail || "运行评测失败。";
  } finally {
    running.value = false;
  }
}

onMounted(() => {
  if (internalToken.value.trim()) {
    void loadPanel();
  }
});
</script>

<template>
  <div class="evaluation-page">
    <section class="surface-card panel-shell">
      <div class="hero">
        <div>
          <p class="eyebrow">系统质量评估</p>
          <h2>问答链路评测与能力指标</h2>
          <p class="hero-desc">
            基于标准天文科普题集，对系统问答质量进行自动化回归测试。展示准确率、响应速度和各主题覆盖表现。
          </p>
        </div>

        <div class="token-box">
          <button class="toggle-admin" @click="showAdminPanel = !showAdminPanel">
            {{ showAdminPanel ? '收起管理面板' : '管理员操作' }}
          </button>
          <div v-if="showAdminPanel" class="admin-panel">
            <el-input
              v-model="internalToken"
              placeholder="输入管理口令"
              show-password
              @keyup.enter="loadPanel"
            />
            <div class="token-actions">
              <el-button :loading="loading" @click="loadPanel">加载数据</el-button>
              <el-button type="primary" plain :loading="running" @click="handleRun(12)">快速评测</el-button>
              <el-button type="primary" :loading="running" @click="handleRun(24)">完整评测</el-button>
            </div>
          </div>
        </div>
      </div>

      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

      <div v-if="capability" class="summary-grid">
        <div class="summary-card">
          <span class="summary-label">本地实体总量</span>
          <strong>{{ capability.summary?.entity_total?.toLocaleString?.() || capability.summary?.entity_total || "--" }}</strong>
        </div>
        <div class="summary-card">
          <span class="summary-label">图谱关系总量</span>
          <strong>{{ capability.summary?.relation_total?.toLocaleString?.() || capability.summary?.relation_total || "--" }}</strong>
        </div>
        <div class="summary-card">
          <span class="summary-label">图像向量数量</span>
          <strong>{{ capability.summary?.indexed_vectors?.toLocaleString?.() || capability.summary?.indexed_vectors || "--" }}</strong>
        </div>
        <div class="summary-card">
          <span class="summary-label">当前问答模式</span>
          <strong>{{ capability.summary?.qa_mode || "--" }}</strong>
        </div>
      </div>

      <div v-if="report" class="metrics-section">
        <div class="section-title">
          <h3>核心指标</h3>
          <p>基于固定题集对当前问答链路进行回归测试。</p>
        </div>

        <div class="summary-grid">
          <div v-for="card in summaryCards" :key="card.label" class="summary-card">
            <span class="summary-label">{{ card.label }}</span>
            <strong>{{ card.value }}</strong>
          </div>
        </div>

        <div class="judge-card">
          <span class="summary-label">评委视角结论</span>
          <p>{{ report.summary?.judge_comment || "暂时还没有评测结论。" }}</p>
        </div>

        <div class="section-title">
          <h3>分类表现</h3>
          <p>按主题查看通过率、平均得分和平均时延。</p>
        </div>

        <div class="table-wrap">
          <table class="metrics-table">
            <thead>
              <tr>
                <th>类别</th>
                <th>样本数</th>
                <th>通过率</th>
                <th>平均得分</th>
                <th>平均时延</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in report.category_breakdown || []" :key="item.category">
                <td>{{ item.category }}</td>
                <td>{{ item.count }}</td>
                <td>{{ percent(item.pass_rate) }}</td>
                <td>{{ percent(item.avg_score) }}</td>
                <td>{{ ms(item.avg_latency_ms) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="section-title">
          <h3>低分样例</h3>
          <p>优先修这些问题，最能提升比赛演示时的稳定性和说服力。</p>
        </div>

        <div class="case-list">
          <article
            v-for="item in (report.cases || []).slice(0, 8)"
            :key="item.id"
            class="case-card"
            :class="{ failed: !item.passed }"
          >
            <div class="case-head">
              <span class="case-category">{{ item.category }}</span>
              <span class="case-score">{{ percent(item.score) }}</span>
            </div>
            <h4>{{ item.question }}</h4>
            <p class="case-answer">{{ item.answer_preview }}</p>
            <div class="case-meta">
              <span>缺失关键词：{{ (item.missing_required || []).join(" / ") || "无" }}</span>
              <span>时延：{{ ms(item.latency_ms) }}</span>
            </div>
          </article>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.evaluation-page {
  width: 100%;
  height: 100%;
  overflow: auto;
}

.panel-shell {
  min-height: 100%;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.hero {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 18px;
  align-items: start;
}

.eyebrow {
  margin: 0 0 8px;
  color: var(--astro-primary);
  font-size: 12px;
  letter-spacing: 0.5px;
}

.hero h2 {
  margin: 0;
  font-size: 30px;
  color: var(--text-primary);
}

.hero-desc {
  margin: 10px 0 0;
  color: var(--text-secondary);
  line-height: 1.8;
}

.toggle-admin {
  padding: 6px 14px;
  border: 1px solid var(--astro-border);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.02);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.12s;
  align-self: flex-end;
}

.toggle-admin:hover {
  border-color: rgba(19, 210, 184, 0.3);
  color: var(--astro-primary);
}

.admin-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  border: 1px solid var(--astro-border);
  border-radius: 8px;
  background: rgba(6, 12, 22, 0.5);
}

.token-box {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.token-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.metrics-section,
.table-wrap,
.case-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.section-title h3 {
  margin: 0;
  font-size: 20px;
}

.section-title p {
  margin: 6px 0 0;
  color: var(--text-secondary);
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.summary-card,
.judge-card,
.case-card {
  padding: 16px;
  border-radius: 16px;
  border: 1px solid var(--astro-border);
  background: rgba(255, 255, 255, 0.02);
}

.summary-label {
  display: block;
  color: var(--text-secondary);
  font-size: 12px;
  margin-bottom: 8px;
}

.summary-card strong {
  font-size: 24px;
  color: var(--text-primary);
}

.judge-card p {
  margin: 0;
  line-height: 1.85;
  color: var(--text-primary);
}

.metrics-table {
  width: 100%;
  border-collapse: collapse;
  overflow: hidden;
  border-radius: 14px;
}

.metrics-table th,
.metrics-table td {
  padding: 12px 14px;
  border-bottom: 1px solid var(--astro-border);
  text-align: left;
}

.metrics-table thead {
  background: rgba(255, 255, 255, 0.03);
}

.case-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.case-card.failed {
  border-color: rgba(255, 120, 120, 0.25);
}

.case-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.case-category,
.case-score {
  font-size: 12px;
  color: var(--astro-primary);
}

.case-card h4 {
  margin: 0 0 10px;
  font-size: 16px;
  line-height: 1.5;
}

.case-answer {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.75;
}

.case-meta {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}

@media (max-width: 1180px) {
  .hero,
  .summary-grid,
  .case-list {
    grid-template-columns: 1fr;
  }
}
</style>
