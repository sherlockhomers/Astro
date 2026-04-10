<template>
  <div class="aladin-container surface-card">
    <div class="aladin-header">
      <div class="title-wrap">
        <h3 class="aladin-title">虚拟星空馆 (Aladin Interactive)</h3>
        <p class="aladin-subtitle">基于海量星表真实摄影数据的全景深空视野</p>
      </div>
      <div class="aladin-controls">
        <el-input
          v-model="searchQuery"
          placeholder="搜索星系/星云 (例如: M31, Orion)"
          class="search-input"
          size="small"
          @keyup.enter="handleSearch"
        >
          <template #append>
            <el-button @click="handleSearch">搜索</el-button>
          </template>
        </el-input>
      </div>
    </div>

    <div id="aladin-lite-div" class="aladin-view"></div>
    
    <div class="aladin-footer">
      <div class="coord-display">
        <span>RA: {{ coords.ra }}</span>
        <span>Dec: {{ coords.dec }}</span>
      </div>
      <div class="survey-info">
        Survey: DSS Colored / SIMBAD
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue';

declare const A: any;

const searchQuery = ref('');
const coords = ref({ ra: '00:00:00', dec: '+00:00:00' });
let aladinInstance: any = null;

const initAladin = () => {
  if (typeof A === 'undefined') {
    console.error('Aladin Lite is not loaded');
    return;
  }

  A.init.then(() => {
    aladinInstance = A.aladin('#aladin-lite-div', {
      survey: 'P/DSS2/color',
      fov: 60,
      target: 'Orion',
      showReticle: true,
      showZoomControl: true,
      showLayersControl: true,
      showGotoControl: false // Using custom search
    });

    aladinInstance.on('mouseMove', (event: any) => {
      if (event.ra !== undefined && event.dec !== undefined) {
        coords.value = {
          ra: event.ra.toFixed(4),
          dec: event.dec.toFixed(4)
        };
      }
    });
  });
};

const handleSearch = () => {
  if (aladinInstance && searchQuery.value) {
    aladinInstance.gotoObject(searchQuery.value);
  }
};

onMounted(() => {
  setTimeout(initAladin, 500);
});

onBeforeUnmount(() => {
  // Let Vue handle DOM removal. Forcibly clearing innerHTML here crashes the WebGL thread during Vue Router navigation.
});
</script>

<style scoped>
.aladin-container {
  background: rgba(14, 21, 35, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 16px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  height: 600px;
}

.aladin-header {
  padding: 16px 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.title-wrap {
  display: flex;
  flex-direction: column;
}

.aladin-title {
  margin: 0;
  font-size: 18px;
  color: #fff;
}

.aladin-subtitle {
  margin: 4px 0 0;
  font-size: 12px;
  color: #8da4c2;
}

.aladin-view {
  flex: 1;
  background: #000;
  width: 100% !important;
  height: 100% !important;
}

.aladin-footer {
  padding: 8px 16px;
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #6e7681;
  background: rgba(4, 9, 18, 0.8);
}

.coord-display {
  display: flex;
  gap: 16px;
}

.search-input {
  width: 280px;
}

:deep(.aladin-container) {
  /* Override any default Aladin styles if needed */
}
</style>
