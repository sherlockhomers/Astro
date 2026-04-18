import { defineStore } from "pinia";
import {
  getGraphStatus,
  getLandingAlerts,
  getLandingApod,
  getLandingFrontier,
  getLandingNews
} from "../api";

// Landing 每次进来都要拉 3~4 个接口，在知识卡片和首页之间反复横跳会明显卡。
// 存一份上次的结果，回来的时候先渲染老数据，够新就不刷、旧了才悄悄刷。

const THREE_MIN = 3 * 60 * 1000;
const REFRESH_MIN = 4 * 60 * 1000;

type NewsItem = {
  title: string;
  url: string;
  image_url: string;
  source: string;
  summary: string;
  date: string;
};

type FrontierPaper = {
  title: string;
  url: string;
  date: string;
  summary: string;
  journal_ref?: string;
  category?: string;
  source?: string;
  authors?: string[];
};

type FrontierTopic = {
  key: string;
  label: string;
  items: FrontierPaper[];
};

type SpaceAlert = {
  id: string;
  title: string;
  summary: string;
  source: string;
  severity: "alert" | "notable" | "info";
  happens_at: string;
  url?: string | null;
  extra?: Record<string, unknown>;
};

type LandingState = {
  apod: any | null;
  news: NewsItem[];
  frontierTopics: FrontierTopic[];
  alerts: SpaceAlert[];
  graphNodes: number;
  fetchedAt: number;
  refreshing: boolean;
  inflight: Promise<void> | null;
};

export const useLandingStore = defineStore("landing", {
  state: (): LandingState => ({
    apod: null,
    news: [],
    frontierTopics: [],
    alerts: [],
    graphNodes: 0,
    fetchedAt: 0,
    refreshing: false,
    inflight: null
  }),
  getters: {
    hasData(state): boolean {
      return Boolean(state.apod) || state.news.length > 0 || state.frontierTopics.length > 0;
    },
    isStale(state): boolean {
      return Date.now() - state.fetchedAt > THREE_MIN;
    }
  },
  actions: {
    // 进入页面时调用：第一次是真要等接口的；之后能直接用缓存就不会 await 阻塞
    async ensureFresh(force = false): Promise<void> {
      if (this.inflight) {
        return this.inflight;
      }
      if (this.hasData && !force && !this.isStale) {
        return;
      }
      this.inflight = this._doFetch();
      try {
        await this.inflight;
      } finally {
        this.inflight = null;
      }
    },

    // 不 await 的版本，用于定时器和 stale 数据的后台更新
    refreshInBackground(): void {
      if (this.inflight || this.refreshing) return;
      this.refreshing = true;
      this._doFetch()
        .catch(() => {
          // 拉失败就不动旧数据
        })
        .finally(() => {
          this.refreshing = false;
        });
    },

    async _doFetch(): Promise<void> {
      const [apod, newsRes, frontierRes, alertRes] = await Promise.all([
        getLandingApod().catch(() => null),
        getLandingNews(6).catch(() => ({ items: [] })),
        getLandingFrontier(36).catch(() => ({ topics: [] })),
        getLandingAlerts(6).catch(() => ({ events: [] }))
      ]);

      // apod 这一项：新的拿到了就换；新的挂了、老的还在，就别把老的洗掉
      if (apod) {
        this.apod = apod;
      } else if (!this.apod) {
        this.apod = null;
      }

      const nextNews = Array.isArray(newsRes?.items) ? (newsRes.items as NewsItem[]) : [];
      if (nextNews.length || !this.news.length) {
        this.news = nextNews;
      }

      const topics = Array.isArray(frontierRes?.topics) ? frontierRes.topics : [];
      const normalized = topics.map((t: Record<string, unknown>) => ({
        key: String(t.key ?? ""),
        label: String(t.label ?? ""),
        items: Array.isArray(t.items) ? (t.items as FrontierPaper[]) : []
      }));
      if (normalized.length || !this.frontierTopics.length) {
        this.frontierTopics = normalized;
      }

      const incomingAlerts = Array.isArray(alertRes?.events) ? (alertRes.events as SpaceAlert[]) : [];
      if (incomingAlerts.length || !this.alerts.length) {
        this.alerts = incomingAlerts;
      }

      // 图谱状态是另一个接口，挂了上面三样数据该展示还是展示
      try {
        const g = await getGraphStatus();
        this.graphNodes = Number(g?.nodes_count ?? 0);
      } catch {
        // 保留上次的值
      }

      this.fetchedAt = Date.now();
    }
  }
});

export const LANDING_REFRESH_INTERVAL_MS = REFRESH_MIN;
