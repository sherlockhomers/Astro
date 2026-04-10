import { defineStore } from "pinia";
import { ref, watch } from "vue";

const SETTINGS_KEY = "astro_settings";

type AppSettings = {
  theme: "dark" | "light";
  showExplorePanel: boolean;
  graphMaxNodes: number;
  qaAutoScroll: boolean;
};

const DEFAULT_SETTINGS: AppSettings = {
  theme: "dark",
  showExplorePanel: true,
  graphMaxNodes: 220,
  qaAutoScroll: true,
};

function loadFromStorage(): AppSettings {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (raw) {
      return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
    }
  } catch {
    // ignore
  }
  return { ...DEFAULT_SETTINGS };
}

export const useSettingsStore = defineStore("settings", () => {
  const saved = loadFromStorage();
  const theme = ref<"dark" | "light">(saved.theme);
  const showExplorePanel = ref(saved.showExplorePanel);
  const graphMaxNodes = ref(saved.graphMaxNodes);
  const qaAutoScroll = ref(saved.qaAutoScroll);

  function persist() {
    const payload: AppSettings = {
      theme: theme.value,
      showExplorePanel: showExplorePanel.value,
      graphMaxNodes: graphMaxNodes.value,
      qaAutoScroll: qaAutoScroll.value,
    };
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(payload));
  }

  watch([theme, showExplorePanel, graphMaxNodes, qaAutoScroll], persist, { deep: true });

  function reset() {
    theme.value = DEFAULT_SETTINGS.theme;
    showExplorePanel.value = DEFAULT_SETTINGS.showExplorePanel;
    graphMaxNodes.value = DEFAULT_SETTINGS.graphMaxNodes;
    qaAutoScroll.value = DEFAULT_SETTINGS.qaAutoScroll;
    persist();
  }

  return {
    theme,
    showExplorePanel,
    graphMaxNodes,
    qaAutoScroll,
    reset,
  };
});
