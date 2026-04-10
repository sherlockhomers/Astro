<template>
  <div ref="container" class="three-universe-container"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, onActivated, onDeactivated } from 'vue';
import * as THREE from 'three';
// @ts-ignore
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls';

const container = ref<HTMLElement | null>(null);

let scene: THREE.Scene;
let camera: THREE.PerspectiveCamera;
let renderer: THREE.WebGLRenderer;
let controls: OrbitControls;
let animationFrameId: number;
let particlesMesh: THREE.Points;
let planetMesh: THREE.Mesh;
let ringMesh: THREE.Mesh;
let glowMesh: THREE.Mesh;
let mouseX = 0;
let mouseY = 0;
let isActive = true;

const initThree = () => {
  if (!container.value) return;

  const w = window.innerWidth;
  // Make height depend on the hero section or window
  const h = window.innerHeight * 0.8;

  // 1. Scene
  scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x040912, 0.001);

  // 2. Camera
  camera = new THREE.PerspectiveCamera(60, w / h, 0.1, 2000);
  camera.position.set(0, 5, 25);

  // 3. Renderer
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setSize(w, h);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  container.value.appendChild(renderer.domElement);

  // 4. Controls
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.05;
  controls.enableZoom = false; // Disable zoom to not mess with page scroll
  controls.enablePan = false;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 0.5;

  // 5. Lighting
  const ambientLight = new THREE.AmbientLight(0xffffff, 0.3);
  scene.add(ambientLight);

  const pointLight = new THREE.PointLight(0x58a6ff, 2.5, 100);
  pointLight.position.set(15, 10, 15);
  scene.add(pointLight);
  
  const backLight = new THREE.PointLight(0xffa500, 1.5, 100);
  backLight.position.set(-15, -10, -15);
  scene.add(backLight);

  // 6. Starfield (Particles)
  const particlesGeometry = new THREE.BufferGeometry();
  const particlesCount = 2000;
  const posArray = new Float32Array(particlesCount * 3);

  for(let i=0; i < particlesCount * 3; i++) {
    posArray[i] = (Math.random() - 0.5) * 100;
  }
  particlesGeometry.setAttribute('position', new THREE.BufferAttribute(posArray, 3));
  
  const particleMaterial = new THREE.PointsMaterial({
    size: 0.05,
    color: 0xc7d2e4,
    transparent: true,
    opacity: 0.8,
    blending: THREE.AdditiveBlending
  });
  
  particlesMesh = new THREE.Points(particlesGeometry, particleMaterial);
  scene.add(particlesMesh);

  // 7. Planet (Wireframe/Neon styled)
  const planetGeo = new THREE.IcosahedronGeometry(6, 12);
  const planetMat = new THREE.MeshStandardMaterial({
    color: 0x0a192f,
    wireframe: true,
    emissive: 0x1f6feb,
    emissiveIntensity: 0.2
  });
  planetMesh = new THREE.Mesh(planetGeo, planetMat);
  scene.add(planetMesh);

  // Solid Inner Core
  const coreGeo = new THREE.IcosahedronGeometry(5.8, 12);
  const coreMat = new THREE.MeshStandardMaterial({
    color: 0x040912,
    roughness: 0.8,
  });
  const coreMesh = new THREE.Mesh(coreGeo, coreMat);
  planetMesh.add(coreMesh);

  // Rings
  const ringGeo = new THREE.TorusGeometry(10, 0.05, 16, 100);
  const ringMat = new THREE.MeshStandardMaterial({
    color: 0xd0a96c,
    emissive: 0xd0a96c,
    emissiveIntensity: 0.5,
    wireframe: true
  });
  ringMesh = new THREE.Mesh(ringGeo, ringMat);
  ringMesh.rotation.x = Math.PI / 2.5;
  ringMesh.rotation.y = Math.PI / 8;
  scene.add(ringMesh);
  
  const ringGeo2 = new THREE.TorusGeometry(10.5, 0.02, 16, 100);
  const ringMat2 = new THREE.MeshBasicMaterial({ color: 0x58a6ff, transparent: true, opacity: 0.5 });
  const ringMesh2 = new THREE.Mesh(ringGeo2, ringMat2);
  ringMesh2.rotation.copy(ringMesh.rotation);
  scene.add(ringMesh2);

  // 8. Event Listeners
  window.addEventListener('resize', onWindowResize);
  document.addEventListener('mousemove', onMouseMove);

  // Start Animation
  animate();
};

const onWindowResize = () => {
  if (!camera || !renderer) return;
  const w = window.innerWidth;
  const h = window.innerHeight * 0.8;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
};

const onMouseMove = (event: MouseEvent) => {
  mouseX = (event.clientX / window.innerWidth) * 2 - 1;
  mouseY = -(event.clientY / window.innerHeight) * 2 + 1;
};

const animate = () => {
  if (!isActive) return;
  animationFrameId = requestAnimationFrame(animate);

  // Rotations
  if (planetMesh) planetMesh.rotation.y += 0.002;
  if (ringMesh) ringMesh.rotation.z -= 0.001;
  if (particlesMesh) particlesMesh.rotation.y += 0.0005;

  // Parallax Effect
  if (camera) {
    camera.position.x += (mouseX * 2 - camera.position.x) * 0.05;
    camera.position.y += (mouseY * 2 + 5 - camera.position.y) * 0.05;
    camera.lookAt(0, 0, 0);
  }

  controls.update();
  renderer.render(scene, camera);
};

onMounted(() => {
  initThree();
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', onWindowResize);
  document.removeEventListener('mousemove', onMouseMove);
  if (animationFrameId) cancelAnimationFrame(animationFrameId);
  if (renderer) renderer.dispose();
});

onActivated(() => {
  if (!isActive) {
    isActive = true;
    animate();
  }
});

onDeactivated(() => {
  isActive = false;
  if (animationFrameId) cancelAnimationFrame(animationFrameId);
});
</script>

<style scoped>
.three-universe-container {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 80vh; /* Match JS script */
  z-index: 0; /* Behind the hero content */
  pointer-events: auto; /* Allow dragging if needed, but text should be overlaid with pointer-events: none on container or higher z-index on text */
  overflow: hidden;
  mask-image: linear-gradient(to bottom, black 50%, transparent 100%);
  -webkit-mask-image: linear-gradient(to bottom, black 50%, transparent 100%);
}

.three-universe-container canvas {
  outline: none;
}
</style>
