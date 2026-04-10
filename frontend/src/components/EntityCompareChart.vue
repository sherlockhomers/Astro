<script setup lang="ts">
import * as echarts from "echarts";
import { computed, onMounted, onUnmounted, ref, watch } from "vue";

type MetricItem = {
  key: string;
  label: string;
  unit: string;
  a: number | null;
  b: number | null;
};

const props = defineProps<{
  leftName: string;
  rightName: string;
  metrics: MetricItem[];
}>();

const chartRef = ref<HTMLDivElement | null>(null);
let chart: echarts.ECharts | null = null;

const rows = computed(() => {
  const out: Array<{ label: string; unit: string; a: number; b: number; aPct: number; bPct: number }> = [];
  for (const m of props.metrics || []) {
    if (typeof m?.a !== "number" || typeof m?.b !== "number") continue;
    const maxVal = Math.max(Math.abs(m.a), Math.abs(m.b), 1);
    out.push({
      label: m.label,
      unit: m.unit,
      a: m.a,
      b: m.b,
      aPct: Number(((Math.abs(m.a) / maxVal) * 100).toFixed(2)),
      bPct: Number(((Math.abs(m.b) / maxVal) * 100).toFixed(2))
    });
  }
  return out;
});

function human(v: number): string {
  const n = Math.abs(v);
  if (n >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(2)}B`;
  if (n >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(v / 1_000).toFixed(2)}K`;
  return `${Number(v.toFixed(2))}`;
}

function render() {
  if (!chartRef.value) return;
  if (!chart) {
    chart = echarts.init(chartRef.value, undefined, { renderer: "canvas" });
  }

  const data = rows.value;
  if (!data.length) {
    chart.clear();
    return;
  }

  const categories = data.map((x) => x.label);
  const leftPct = data.map((x) => x.aPct);
  const rightPct = data.map((x) => x.bPct);

  chart.setOption(
    {
      animation: false,
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        formatter(params: any) {
          const arr = Array.isArray(params) ? params : [params];
          if (!arr.length) return "";
          const idx = Number(arr[0].dataIndex || 0);
          const row = data[idx];
          if (!row) return "";
          return [
            `<b>${row.label}</b>（归一化对比）`,
            `${props.leftName}: ${human(row.a)} ${row.unit}`,
            `${props.rightName}: ${human(row.b)} ${row.unit}`
          ].join("<br/>");
        }
      },
      legend: {
        textStyle: { color: "#c8d6f0" },
        data: [props.leftName, props.rightName]
      },
      grid: { left: 65, right: 20, top: 35, bottom: 25 },
      xAxis: {
        type: "value",
        min: 0,
        max: 100,
        axisLabel: { color: "#8fa3c7", formatter: "{value}%" },
        splitLine: { lineStyle: { color: "rgba(143,163,199,0.18)" } }
      },
      yAxis: {
        type: "category",
        data: categories,
        axisLabel: { color: "#8fa3c7" },
        axisLine: { lineStyle: { color: "#33466a" } }
      },
      series: [
        {
          name: props.leftName,
          type: "bar",
          data: leftPct,
          barMaxWidth: 18,
          itemStyle: { color: "#5f9cff" }
        },
        {
          name: props.rightName,
          type: "bar",
          data: rightPct,
          barMaxWidth: 18,
          itemStyle: { color: "#f6b85f" }
        }
      ]
    },
    { notMerge: true, lazyUpdate: true }
  );
}

function resize() {
  chart?.resize();
}

onMounted(() => {
  render();
  window.addEventListener("resize", resize);
});

onUnmounted(() => {
  window.removeEventListener("resize", resize);
  chart?.dispose();
  chart = null;
});

watch(
  () => [props.leftName, props.rightName, props.metrics],
  () => render(),
  { deep: true }
);
</script>

<template>
  <div ref="chartRef" style="width: 100%; height: 220px"></div>
</template>
