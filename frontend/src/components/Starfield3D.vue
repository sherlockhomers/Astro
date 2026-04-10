<script setup lang="ts">
import * as THREE from "three";
import { onMounted, onUnmounted, ref, watch } from "vue";

type Point = { x: number; y: number; z: number; category?: string; name?: string };

const props = defineProps<{ points: Point[] }>();
const rootRef = ref<HTMLDivElement | null>(null);

let renderer: THREE.WebGLRenderer | null = null;
let scene: THREE.Scene | null = null;
let camera: THREE.PerspectiveCamera | null = null;
let pointsObj: THREE.Points | null = null;
let rafId = 0;

function initScene() {
  if (!rootRef.value) return;
  disposeScene();

  const width = rootRef.value.clientWidth || 800;
  const height = rootRef.value.clientHeight || 520;

  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x050812);

  camera = new THREE.PerspectiveCamera(65, width / height, 0.1, 2000);
  camera.position.set(0, 0, 240);

  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(width, height);
  rootRef.value.innerHTML = "";
  rootRef.value.appendChild(renderer.domElement);

  const geometry = new THREE.BufferGeometry();
  const coords: number[] = [];
  const colors: number[] = [];
  for (const p of props.points) {
    coords.push(p.x, p.y, p.z);
    const isPlanet = (p.category || "").toLowerCase().includes("planet");
    if (isPlanet) {
      colors.push(0.4, 0.8, 1.0);
    } else {
      colors.push(1.0, 1.0, 1.0);
    }
  }
  if (coords.length === 0) {
    coords.push(0, 0, 0);
    colors.push(0.15, 0.2, 0.3);
  }
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(coords, 3));
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));

  const material = new THREE.PointsMaterial({ size: 1.8, vertexColors: true });
  pointsObj = new THREE.Points(geometry, material);
  scene.add(pointsObj);
  animate();
}

function animate() {
  if (!renderer || !scene || !camera) return;
  rafId = requestAnimationFrame(animate);
  if (pointsObj) {
    pointsObj.rotation.y += 0.0018;
    pointsObj.rotation.x += 0.0007;
  }
  renderer.render(scene, camera);
}

function onResize() {
  if (!rootRef.value || !renderer || !camera) return;
  const width = rootRef.value.clientWidth || 800;
  const height = rootRef.value.clientHeight || 520;
  renderer.setSize(width, height);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}

function disposeScene() {
  cancelAnimationFrame(rafId);
  if (pointsObj) {
    pointsObj.geometry.dispose();
    (pointsObj.material as THREE.Material).dispose();
    pointsObj = null;
  }
  renderer?.dispose();
  renderer = null;
  scene = null;
  camera = null;
}

onMounted(() => {
  initScene();
  window.addEventListener("resize", onResize);
});

onUnmounted(() => {
  window.removeEventListener("resize", onResize);
  disposeScene();
});

watch(
  () => props.points,
  () => initScene(),
  { deep: true }
);
</script>

<template>
  <div ref="rootRef" class="starfield-root"></div>
</template>

<style scoped>
.starfield-root {
  width: 100%;
  height: 100%;
  min-height: 72vh;
  border: 1px solid #2e4179;
  border-radius: 8px;
}
</style>
