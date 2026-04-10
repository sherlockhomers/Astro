<script setup lang="ts">
// Main App component now just handles routing
</script>

<template>
  <router-view v-slot="{ Component }">
    <transition name="fade" mode="out-in">
      <component :is="Component" />
    </transition>
  </router-view>
</template>

<style>
/* 
  Enterprise NASA-JPL / Space Terminal Design Language 
  NO "AI-Chat" vibes or generic dashboard colors.
*/

:root {
  /* Core Foundation */
  --bg-color: #05080e;           /* Deepest Space Black */
  --bg-color-secondary: #0a1120; /* Console Panel Base */
  
  /* Text & Data */
  --text-primary: #e2e8f0;       /* High-contrast data readout */
  --text-secondary: #7f92ab;     /* Subdued logs */
  
  /* Borders & Grids */
  --border-color: #1a253a;       /* Sharp panel divider */
  --astro-border: #1a253a;
  
  /* Action & Status Accents */
  --astro-primary: #13d2b8;      /* Radar/Target Cyan */
  --astro-primary-glow: rgba(19, 210, 184, 0.25);
  --accent-color: #1f6feb;       /* Deep Azure action */
  --accent-hover: #388bfd;
  
  /* Utility */
  --success-color: #10b981;
  --warn-color: #f59e0b;         /* Amber warning */
  --error-color: #ef4444;

  /* Element Plus Root Overrides */
  --el-color-primary: var(--astro-primary) !important;
  --el-color-primary-light-3: #43eed7 !important;
  --el-color-primary-light-9: rgba(19, 210, 184, 0.1) !important;
  --el-color-primary-dark-2: #0fa893 !important;
  
  --el-bg-color: var(--bg-color-secondary) !important;
  --el-bg-color-overlay: #0b1321 !important;
  --el-text-color-primary: var(--text-primary) !important;
  --el-text-color-regular: #a0aec0 !important;
  --el-border-color: var(--border-color) !important;
  --el-border-color-light: #243552 !important;
  --el-fill-color-blank: #0a1120 !important;
  
  --el-border-radius-base: 2px !important;    /* Hard sharp edges instead of bubbly corners */
  --el-border-radius-small: 0px !important;
  --el-border-radius-round: 4px !important;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background-color: var(--bg-color);
  color: var(--text-primary);
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}

/* Hardened Custom Scrollbar - Engineering Grade */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

::-webkit-scrollbar-track {
  background: var(--bg-color);
  border-left: 1px solid var(--border-color);
}

::-webkit-scrollbar-thumb {
  background: #364968;
  border-radius: 0;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--astro-primary);
}

/* Typography Reset */
h1, h2, h3, h4, h5, h6 {
  margin-top: 0;
  color: #fff;
  font-weight: 500;
  letter-spacing: 0.5px;
}

/* Page Transition */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: scale(0.995);
}

/* Common UI Glasses / Panels */
.surface-card {
  background: rgba(10, 17, 32, 0.65);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid var(--astro-border);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.02), 0 4px 20px rgba(0, 0, 0, 0.2);
}
</style>
