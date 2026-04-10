<script setup lang="ts">
import * as echarts from "echarts";
import { onMounted, onUnmounted, ref, watch } from "vue";

type GraphNode = { id: string; name: string; category?: string; value?: number };
type GraphLink = { source: string; target: string; name?: string };

const props = defineProps<{
  nodes: GraphNode[];
  links: GraphLink[];
  categories: string[];
  renderLimitNodes?: number;
  renderLimitLinks?: number;
}>();
const emit = defineEmits<{
  (e: "node-click", payload: { id: string; name: string; category?: string; value?: number }): void;
  (e: "edge-click", payload: { source: string; target: string; name?: string }): void;
}>();

const chartRef = ref<HTMLDivElement | null>(null);
let chart: echarts.ECharts | null = null;
let renderFrame: number | null = null;

function reduceGraphData(
  nodes: GraphNode[],
  links: GraphLink[],
  maxNodes = 120,
  maxLinks = 320
): { nodes: GraphNode[]; links: GraphLink[] } {
  const normalized = normalizeGraphData(nodes, links);
  if (normalized.nodes.length <= maxNodes && normalized.links.length <= maxLinks) {
    return normalized;
  }

  const degree = new Map<string, number>();
  for (const n of normalized.nodes) {
    degree.set(n.name, 0);
  }
  for (const l of normalized.links) {
    degree.set(l.source, (degree.get(l.source) || 0) + 1);
    degree.set(l.target, (degree.get(l.target) || 0) + 1);
  }

  const sortedNodes = [...normalized.nodes].sort((a, b) => {
    const da = degree.get(a.name) || 0;
    const db = degree.get(b.name) || 0;
    if (db !== da) return db - da;
    return (b.value || 1) - (a.value || 1);
  });
  const keepNodes = sortedNodes.slice(0, maxNodes);
  const keepNames = new Set(keepNodes.map((x) => x.name));

  const keepLinks = normalized.links
    .filter((x) => keepNames.has(x.source) && keepNames.has(x.target))
    .slice(0, maxLinks);

  return { nodes: keepNodes, links: keepLinks };
}

function normalizeGraphData(
  nodes: GraphNode[],
  links: GraphLink[]
): { nodes: GraphNode[]; links: GraphLink[] } {
  const nodeByName = new Map<string, GraphNode>();
  for (const node of nodes || []) {
    const name = (node?.name || node?.id || "").trim();
    if (!name) continue;
    if (!nodeByName.has(name)) {
      nodeByName.set(name, { ...node, id: name, name });
    }
  }

  const validNames = new Set(nodeByName.keys());
  const dedupLinks = new Map<string, GraphLink>();
  for (const link of links || []) {
    const source = String(link?.source || "").trim();
    const target = String(link?.target || "").trim();
    if (!source || !target || source === target) continue;
    if (!validNames.has(source) || !validNames.has(target)) continue;
    const rel = String(link?.name || "").trim();
    const key = `${source}|${target}|${rel}`;
    if (!dedupLinks.has(key)) {
      dedupLinks.set(key, { source, target, name: rel });
    }
  }
  return {
    nodes: [...nodeByName.values()],
    links: [...dedupLinks.values()]
  };
}

function renderChart() {
  if (!chartRef.value) return;
  if (!chart) {
    chart = echarts.init(chartRef.value, undefined, { renderer: "canvas" });
  }

  const maxNodes = Math.max(120, Math.min(props.renderLimitNodes || 800, 2200));
  const maxLinks = Math.max(320, Math.min(props.renderLimitLinks || 5000, 15000));
  const reduced = reduceGraphData(props.nodes || [], props.links || [], maxNodes, maxLinks);
  if (!reduced.nodes.length) {
    chart.clear();
    return;
  }
  const denseGraph = reduced.nodes.length > 650 || reduced.links.length > 2600;
  const superDense = reduced.nodes.length > 1500 || reduced.links.length > 8200;
  const layoutMode = denseGraph ? "none" : "force";
  const radius = 220;
  const nodesData = reduced.nodes.map((n, idx) => {
    const angle = (Math.PI * 2 * idx) / Math.max(1, reduced.nodes.length);
    const isSeed = Boolean((n as any).is_seed) || Number(n.value || 0) >= 2;
    return {
      ...n,
      category: Math.max(0, (props.categories || []).indexOf(n.category || "unknown")),
      symbolSize: (superDense ? 3 : denseGraph ? 5 : 9) + (isSeed ? 5 : 0),
      itemStyle: isSeed
        ? {
            borderColor: "#f7c97b",
            borderWidth: 2,
            shadowBlur: 8,
            shadowColor: "rgba(247, 201, 123, 0.45)"
          }
        : undefined,
      x: denseGraph ? Math.cos(angle) * (radius + (idx % 7) * 18) : undefined,
      y: denseGraph ? Math.sin(angle) * (radius + (idx % 7) * 18) : undefined
    };
  });

  const option: echarts.EChartsOption = {
    animation: false,
    animationDurationUpdate: 0,
    tooltip: {},
    legend: denseGraph ? [] : [{ data: (props.categories || []).slice(0, 12) }],
    series: [
      {
        type: "graph",
        layout: layoutMode,
        roam: true,
        draggable: !denseGraph,
        force:
          layoutMode === "force"
            ? {
                repulsion: 130,
                edgeLength: [45, 120],
                gravity: 0.08
              }
            : undefined,
        data: nodesData,
        links: reduced.links,
        categories: (props.categories || []).map((c) => ({ name: c })),
        progressive: 1400,
        progressiveThreshold: 2200,
        label: {
          show: !denseGraph,
          position: "right",
          fontSize: 10
        },
        edgeLabel: { show: false },
        lineStyle: {
          color: "source",
          curveness: 0.06,
          width: superDense ? 0.45 : denseGraph ? 0.7 : 1.0,
          opacity: superDense ? 0.22 : denseGraph ? 0.38 : 0.55
        }
      }
    ]
  };

  chart.off("click");
  chart.on("click", (params: any) => {
    if (params?.dataType === "node" && params?.data) {
      emit("node-click", {
        id: String(params.data.id || params.data.name || ""),
        name: String(params.data.name || params.data.id || ""),
        category: params.data.category,
        value: Number(params.data.value || 1)
      });
      return;
    }
    if (params?.dataType === "edge" && params?.data) {
      emit("edge-click", {
        source: String(params.data.source || ""),
        target: String(params.data.target || ""),
        name: String(params.data.name || "")
      });
    }
  });

  chart.setOption(option, { notMerge: true, lazyUpdate: true, silent: false });
}

function scheduleRender() {
  if (renderFrame !== null) {
    window.cancelAnimationFrame(renderFrame);
  }
  renderFrame = window.requestAnimationFrame(() => {
    renderFrame = null;
    renderChart();
  });
}

function resize() {
  chart?.resize();
}

onMounted(() => {
  renderChart();
  window.addEventListener("resize", resize);
});

onUnmounted(() => {
  if (renderFrame !== null) {
    window.cancelAnimationFrame(renderFrame);
    renderFrame = null;
  }
  window.removeEventListener("resize", resize);
  chart?.dispose();
  chart = null;
});

watch(
  () => [props.nodes, props.links, props.categories, props.renderLimitNodes, props.renderLimitLinks],
  () => {
    scheduleRender();
  }
);
</script>

<template>
  <div ref="chartRef" style="width: 100%; height: 100%"></div>
</template>
