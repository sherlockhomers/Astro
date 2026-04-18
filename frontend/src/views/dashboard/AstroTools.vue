<script setup lang="ts">
import { ref } from "vue";
import { ElMessage } from "element-plus";
import { Calculator, Moon, Telescope, Compass, MapPin, Loader2 } from "lucide-vue-next";
import {
  callCoordConvert,
  callMoonPhase,
  callPlanetVisibility
} from "../../api";

type ActiveTool = "moon" | "planet" | "coord";

const activeTool = ref<ActiveTool>("planet");
const busy = ref(false);

// 月相
const moonDate = ref<string>("");
const moonResult = ref<Record<string, unknown> | null>(null);

// 行星可见性
const planetName = ref("木星");
const planetCity = ref("北京");
const planetDateTime = ref<string>("");
const planetResult = ref<Record<string, unknown> | null>(null);

const planetOptions = ["水星", "金星", "火星", "木星", "土星", "天王星", "海王星"];
const cityOptions = ["北京", "上海", "广州", "深圳", "成都", "杭州", "西安", "武汉", "重庆", "香港", "台北"];

// 坐标转换
const coordRa = ref<number>(83.633);
const coordDec = ref<number>(22.014);
const coordFrom = ref<"equatorial" | "ecliptic">("equatorial");
const coordTo = ref<"equatorial" | "ecliptic">("ecliptic");
const coordResult = ref<Record<string, unknown> | null>(null);

async function runMoon() {
  busy.value = true;
  try {
    moonResult.value = await callMoonPhase(moonDate.value || undefined);
  } catch {
    ElMessage.error("月相接口请求失败，稍后再试");
  } finally {
    busy.value = false;
  }
}

async function runPlanet() {
  busy.value = true;
  try {
    planetResult.value = await callPlanetVisibility({
      planet: planetName.value,
      city: planetCity.value || undefined,
      datetime_iso: planetDateTime.value || undefined
    });
  } catch (err: any) {
    const detail = err?.response?.data?.detail || "行星可见性接口请求失败";
    ElMessage.error(detail);
  } finally {
    busy.value = false;
  }
}

async function runCoord() {
  if (coordFrom.value === coordTo.value) {
    ElMessage.warning("源坐标和目标坐标要不一样");
    return;
  }
  busy.value = true;
  try {
    coordResult.value = await callCoordConvert({
      ra: Number(coordRa.value),
      dec: Number(coordDec.value),
      from_frame: coordFrom.value,
      to_frame: coordTo.value
    });
  } catch {
    ElMessage.error("坐标转换接口请求失败");
  } finally {
    busy.value = false;
  }
}

function switchTool(t: ActiveTool) {
  activeTool.value = t;
}
</script>

<template>
  <div class="tools-view">
    <div class="tools-tabs">
      <button
        class="tab-btn"
        :class="{ active: activeTool === 'planet' }"
        @click="switchTool('planet')"
      >
        <Telescope :size="16" />
        <span>今晚看什么</span>
      </button>
      <button
        class="tab-btn"
        :class="{ active: activeTool === 'moon' }"
        @click="switchTool('moon')"
      >
        <Moon :size="16" />
        <span>月相查询</span>
      </button>
      <button
        class="tab-btn"
        :class="{ active: activeTool === 'coord' }"
        @click="switchTool('coord')"
      >
        <Compass :size="16" />
        <span>坐标转换</span>
      </button>
    </div>

    <!-- 行星可见性 -->
    <section v-if="activeTool === 'planet'" class="tool-panel surface-card">
      <header class="panel-head">
        <Telescope :size="18" class="panel-icon" />
        <div>
          <h2 class="panel-title">今晚能看到哪颗行星？</h2>
          <p class="panel-desc">选定行星和你的城市，我们算出它此刻在天空中的位置和观测建议。</p>
        </div>
      </header>

      <div class="panel-form">
        <div class="form-row">
          <label class="form-label">行星</label>
          <el-select v-model="planetName" class="form-input">
            <el-option v-for="p in planetOptions" :key="p" :label="p" :value="p" />
          </el-select>
        </div>
        <div class="form-row">
          <label class="form-label">城市</label>
          <el-select v-model="planetCity" filterable allow-create class="form-input">
            <el-option v-for="c in cityOptions" :key="c" :label="c" :value="c" />
          </el-select>
        </div>
        <div class="form-row">
          <label class="form-label">观测时间</label>
          <el-date-picker
            v-model="planetDateTime"
            type="datetime"
            placeholder="留空表示现在"
            class="form-input"
            value-format="YYYY-MM-DDTHH:mm:ss"
          />
        </div>
        <button class="run-btn" :disabled="busy" @click="runPlanet">
          <Loader2 v-if="busy" :size="14" class="spin" />
          {{ busy ? '计算中...' : '开始计算' }}
        </button>
      </div>

      <div v-if="planetResult" class="result-card" :class="{ dim: !planetResult.visible_now }">
        <div class="result-head">
          <span class="planet-badge">{{ planetResult.planet_zh }} · {{ planetResult.planet_en }}</span>
          <span class="visible-tag" :class="{ ok: planetResult.visible_now }">
            {{ planetResult.visible_now ? '✓ 此刻可见' : '地平以下 / 过低' }}
          </span>
        </div>
        <p class="result-summary">{{ planetResult.summary }}</p>
        <div class="stat-grid">
          <div class="stat">
            <span class="stat-k">方向</span>
            <span class="stat-v">{{ planetResult.azimuth_label }} ({{ planetResult.azimuth_deg }}°)</span>
          </div>
          <div class="stat">
            <span class="stat-k">高度角</span>
            <span class="stat-v">{{ planetResult.altitude_deg }}°</span>
          </div>
          <div class="stat">
            <span class="stat-k">距离地球</span>
            <span class="stat-v">{{ planetResult.distance_au }} AU</span>
          </div>
          <div class="stat">
            <span class="stat-k">位置</span>
            <span class="stat-v">
              <MapPin :size="11" class="inline-ico" />{{ planetResult.location }}
            </span>
          </div>
        </div>
      </div>
    </section>

    <!-- 月相 -->
    <section v-if="activeTool === 'moon'" class="tool-panel surface-card">
      <header class="panel-head">
        <Moon :size="18" class="panel-icon" />
        <div>
          <h2 class="panel-title">月相查询</h2>
          <p class="panel-desc">拿一个日期，我们告诉你那天的月亮长什么样、亮多少、月龄几天。</p>
        </div>
      </header>
      <div class="panel-form">
        <div class="form-row">
          <label class="form-label">日期</label>
          <el-date-picker
            v-model="moonDate"
            type="date"
            placeholder="留空表示今天"
            class="form-input"
            value-format="YYYY-MM-DD"
          />
        </div>
        <button class="run-btn" :disabled="busy" @click="runMoon">
          <Loader2 v-if="busy" :size="14" class="spin" />
          {{ busy ? '计算中...' : '查月相' }}
        </button>
      </div>

      <div v-if="moonResult" class="result-card">
        <div class="result-head">
          <span class="planet-badge">{{ moonResult.phase_name }}</span>
          <span class="visible-tag ok">月龄 {{ moonResult.age_days }} 天</span>
        </div>
        <p class="result-summary">{{ moonResult.summary }}</p>
        <div class="moon-bar">
          <div class="moon-bar-fill" :style="{ width: `${Number(moonResult.illumination) * 100}%` }"></div>
          <span class="moon-bar-label">亮度 {{ Math.round(Number(moonResult.illumination) * 100) }}%</span>
        </div>
      </div>
    </section>

    <!-- 坐标转换 -->
    <section v-if="activeTool === 'coord'" class="tool-panel surface-card">
      <header class="panel-head">
        <Compass :size="18" class="panel-icon" />
        <div>
          <h2 class="panel-title">坐标系转换</h2>
          <p class="panel-desc">赤道坐标 ⇄ 黄道坐标 快速换算。默认是蟹状星云 (M1) 的赤道坐标。</p>
        </div>
      </header>
      <div class="panel-form two-col">
        <div class="form-row">
          <label class="form-label">RA / 黄经 (°)</label>
          <el-input v-model.number="coordRa" class="form-input" type="number" />
        </div>
        <div class="form-row">
          <label class="form-label">Dec / 黄纬 (°)</label>
          <el-input v-model.number="coordDec" class="form-input" type="number" />
        </div>
        <div class="form-row">
          <label class="form-label">源坐标系</label>
          <el-select v-model="coordFrom" class="form-input">
            <el-option label="赤道坐标 equatorial" value="equatorial" />
            <el-option label="黄道坐标 ecliptic" value="ecliptic" />
          </el-select>
        </div>
        <div class="form-row">
          <label class="form-label">目标坐标系</label>
          <el-select v-model="coordTo" class="form-input">
            <el-option label="黄道坐标 ecliptic" value="ecliptic" />
            <el-option label="赤道坐标 equatorial" value="equatorial" />
          </el-select>
        </div>
        <button class="run-btn full-span" :disabled="busy" @click="runCoord">
          <Loader2 v-if="busy" :size="14" class="spin" />
          {{ busy ? '计算中...' : '转换' }}
        </button>
      </div>

      <div v-if="coordResult" class="result-card">
        <div class="result-head">
          <span class="planet-badge">{{ coordResult.input?.frame }} → {{ coordResult.output?.frame }}</span>
        </div>
        <p class="result-summary">{{ coordResult.summary }}</p>
      </div>
    </section>

    <div class="tool-hint">
      <Calculator :size="12" />
      这些结果都是用公式实时算出来的，不是查表。精度在科普展示够用，专业观测请对比 SIMBAD / NASA HORIZONS。
    </div>
  </div>
</template>

<style scoped>
.tools-view {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 4px;
  height: 100%;
  overflow-y: auto;
}

.tools-tabs {
  display: flex;
  gap: 8px;
  padding-bottom: 2px;
  border-bottom: 1px solid var(--astro-border);
}

.tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  border-radius: 2px;
  transition: all 0.15s;
}

.tab-btn:hover {
  color: var(--text-primary);
  background: rgba(19, 210, 184, 0.06);
}

.tab-btn.active {
  color: var(--astro-primary);
  border-color: var(--astro-primary);
  background: rgba(19, 210, 184, 0.08);
  box-shadow: 0 0 0 1px rgba(19, 210, 184, 0.15) inset;
}

.tool-panel {
  padding: 22px 24px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.panel-head {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}

.panel-icon {
  color: var(--astro-primary);
  padding: 8px;
  border: 1px solid var(--astro-border);
  border-radius: 4px;
  background: rgba(19, 210, 184, 0.05);
  box-sizing: content-box;
  flex-shrink: 0;
}

.panel-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 0.3px;
}

.panel-desc {
  margin: 4px 0 0;
  font-size: 12.5px;
  color: var(--text-secondary);
  line-height: 1.55;
}

.panel-form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 12px;
  align-items: end;
}

.panel-form.two-col {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.form-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-label {
  font-size: 11px;
  color: var(--text-secondary);
  letter-spacing: 0.6px;
  text-transform: uppercase;
}

.form-input {
  width: 100%;
}

.run-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 20px;
  border: 1px solid var(--astro-primary);
  background: rgba(19, 210, 184, 0.08);
  color: var(--astro-primary);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  border-radius: 2px;
  transition: background 0.15s;
}

.run-btn:hover:not(:disabled) {
  background: rgba(19, 210, 184, 0.18);
}

.run-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.run-btn.full-span {
  grid-column: 1 / -1;
}

.spin {
  animation: tools-spin 1s linear infinite;
}

@keyframes tools-spin {
  to { transform: rotate(360deg); }
}

.result-card {
  border: 1px solid var(--astro-border);
  background: rgba(8, 14, 26, 0.65);
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  border-radius: 2px;
  transition: opacity 0.2s;
}

.result-card.dim {
  opacity: 0.72;
}

.result-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.planet-badge {
  font-size: 12px;
  letter-spacing: 0.6px;
  color: var(--astro-primary);
  padding: 3px 10px;
  border: 1px solid rgba(19, 210, 184, 0.35);
  border-radius: 2px;
  font-weight: 600;
}

.visible-tag {
  font-size: 11.5px;
  color: var(--text-secondary);
  letter-spacing: 0.4px;
}

.visible-tag.ok {
  color: var(--success-color);
}

.result-summary {
  margin: 0;
  color: var(--text-primary);
  font-size: 13.5px;
  line-height: 1.65;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
  padding-top: 6px;
  border-top: 1px dashed var(--astro-border);
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stat-k {
  font-size: 11px;
  color: var(--text-secondary);
  letter-spacing: 0.5px;
}

.stat-v {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.inline-ico {
  color: var(--astro-primary);
}

.moon-bar {
  position: relative;
  height: 18px;
  background: rgba(6, 12, 22, 0.7);
  border: 1px solid var(--astro-border);
  border-radius: 2px;
  overflow: hidden;
}

.moon-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, rgba(19, 210, 184, 0.3), rgba(19, 210, 184, 0.8));
  transition: width 0.4s ease;
}

.moon-bar-label {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: var(--text-primary);
  letter-spacing: 0.6px;
  font-variant-numeric: tabular-nums;
}

.tool-hint {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: rgba(6, 12, 22, 0.4);
  border: 1px dashed var(--astro-border);
  color: var(--text-secondary);
  font-size: 11.5px;
  line-height: 1.5;
  border-radius: 2px;
}
</style>
