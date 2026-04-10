<script setup lang="ts">
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { onMounted, onUnmounted, ref, watch } from "vue";

type ModelPayload = {
  kind: string;
  preset?: string;
  color: string;
  emissive?: string;
  ring?: boolean;
  size?: number;
  note?: string;
};

const props = defineProps<{
  model: ModelPayload | null;
  title?: string;
}>();

const rootRef = ref<HTMLDivElement | null>(null);

let renderer: THREE.WebGLRenderer | null = null;
let scene: THREE.Scene | null = null;
let camera: THREE.PerspectiveCamera | null = null;
let controls: OrbitControls | null = null;
let clock: THREE.Clock | null = null;
let rafId = 0;

let rootGroup: THREE.Group | null = null;
let starPoints: THREE.Points | null = null;
let blackholeDiskUniforms: { uTime: { value: number } } | null = null;

const textureLoader = new THREE.TextureLoader();
const textureCache = new Map<string, THREE.Texture>();

function loadTexture(path: string, color = true): THREE.Texture {
  const key = `${path}|${color ? "srgb" : "linear"}`;
  const cached = textureCache.get(key);
  if (cached) return cached;
  const tex = textureLoader.load(path);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  if (color) tex.colorSpace = THREE.SRGBColorSpace;
  textureCache.set(key, tex);
  return tex;
}

function createFallbackStripedTexture(): THREE.Texture {
  const canvas = document.createElement("canvas");
  canvas.width = 1024;
  canvas.height = 512;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    return new THREE.Texture();
  }
  const grad = ctx.createLinearGradient(0, 0, 0, canvas.height);
  grad.addColorStop(0, "#f3d1ad");
  grad.addColorStop(0.22, "#d19d72");
  grad.addColorStop(0.45, "#f1c490");
  grad.addColorStop(0.67, "#c37c56");
  grad.addColorStop(1, "#edcba1");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  for (let i = 0; i < 120; i += 1) {
    const y = Math.random() * canvas.height;
    const h = 3 + Math.random() * 14;
    ctx.globalAlpha = 0.08 + Math.random() * 0.18;
    ctx.fillStyle = i % 2 === 0 ? "#ffffff" : "#5f371e";
    ctx.fillRect(0, y, canvas.width, h);
  }
  ctx.globalAlpha = 1;
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.needsUpdate = true;
  return tex;
}

function createStarfield() {
  if (!scene) return;
  const geometry = new THREE.BufferGeometry();
  const count = 2400;
  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  for (let i = 0; i < count; i += 1) {
    const r = 700 + Math.random() * 1200;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    positions[i * 3 + 0] = r * Math.sin(phi) * Math.cos(theta);
    positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
    positions[i * 3 + 2] = r * Math.cos(phi);
    const c = 0.78 + Math.random() * 0.22;
    colors[i * 3 + 0] = c;
    colors[i * 3 + 1] = c;
    colors[i * 3 + 2] = c + Math.random() * 0.04;
  }
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  const material = new THREE.PointsMaterial({
    size: 2.3,
    vertexColors: true,
    transparent: true,
    opacity: 0.9,
    sizeAttenuation: true
  });
  starPoints = new THREE.Points(geometry, material);
  scene.add(starPoints);
}

function createPlanetSphere(radius: number, material: THREE.Material): THREE.Mesh {
  const geo = new THREE.SphereGeometry(radius, 160, 160);
  return new THREE.Mesh(geo, material);
}

function addAtmosphere(radius: number) {
  if (!rootGroup) return;
  const geo = new THREE.SphereGeometry(radius * 1.03, 96, 96);
  const mat = new THREE.ShaderMaterial({
    uniforms: {
      c: { value: 0.45 },
      p: { value: 4.0 },
      glowColor: { value: new THREE.Color("#5fa8ff") },
      viewVector: { value: camera?.position || new THREE.Vector3(0, 0, 120) }
    },
    vertexShader: `
      uniform vec3 viewVector;
      uniform float c;
      uniform float p;
      varying float intensity;
      void main() {
        vec3 vNormal = normalize(normalMatrix * normal);
        vec3 vNormel = normalize(normalMatrix * viewVector);
        intensity = pow(c - dot(vNormal, vNormel), p);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform vec3 glowColor;
      varying float intensity;
      void main() {
        vec3 glow = glowColor * intensity;
        gl_FragColor = vec4(glow, clamp(intensity, 0.0, 0.55));
      }
    `,
    side: THREE.BackSide,
    blending: THREE.AdditiveBlending,
    transparent: true
  });
  const atmosphere = new THREE.Mesh(geo, mat);
  rootGroup.add(atmosphere);
}

function createBlackhole(size = 1) {
  if (!rootGroup || !scene) return;
  const core = new THREE.Mesh(
    new THREE.SphereGeometry(16 * size, 96, 96),
    new THREE.MeshPhysicalMaterial({
      color: "#050507",
      roughness: 0.25,
      metalness: 0.95
    })
  );
  rootGroup.add(core);

  blackholeDiskUniforms = {
    uTime: { value: 0 }
  };
  const disk = new THREE.Mesh(
    new THREE.RingGeometry(24 * size, 48 * size, 240, 1),
    new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      uniforms: blackholeDiskUniforms,
      vertexShader: `
        varying vec2 vUv;
        void main() {
          vUv = uv;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform float uTime;
        varying vec2 vUv;
        float noise(vec2 p){
          return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
        }
        void main() {
          vec2 uv = vUv - 0.5;
          float r = length(uv) * 2.0;
          float a = atan(uv.y, uv.x);
          float swirl = sin(18.0 * r - 6.0 * a - uTime * 2.2) * 0.5 + 0.5;
          float grain = noise(uv * 36.0 + uTime * 0.1) * 0.25;
          float edge = smoothstep(0.95, 0.25, r) * smoothstep(0.0, 0.15, r);
          vec3 col = mix(vec3(1.0, 0.62, 0.18), vec3(1.0, 0.9, 0.55), swirl);
          col *= (0.45 + swirl * 0.8 + grain);
          float alpha = edge * (0.75 + swirl * 0.2);
          gl_FragColor = vec4(col, alpha);
        }
      `
    })
  );
  disk.rotation.x = Math.PI * 0.5;
  rootGroup.add(disk);

  const glow = new THREE.PointLight("#f3a55e", 6.5, 360, 1.5);
  glow.position.set(0, 0, 0);
  scene.add(glow);
}

function createModel(payload: ModelPayload) {
  if (!scene) return;
  rootGroup = new THREE.Group();
  scene.add(rootGroup);

  const size = payload.size ?? 1;
  const radius = 16 * size;
  const preset = String(payload.preset || payload.kind || "generic").toLowerCase();

  if (payload.kind === "blackhole" || preset === "blackhole") {
    createBlackhole(size);
    return;
  }

  let mesh: THREE.Mesh | null = null;

  if (preset === "earth") {
    const day = loadTexture("/textures/earth_atmos_2048.jpg");
    const normal = loadTexture("/textures/earth_normal_2048.jpg", false);
    const spec = loadTexture("/textures/earth_specular_2048.jpg", false);
    const mat = new THREE.MeshPhongMaterial({
      map: day,
      normalMap: normal,
      normalScale: new THREE.Vector2(1.05, 1.05),
      specularMap: spec,
      specular: new THREE.Color("#7f9ec2"),
      shininess: 18
    });
    mesh = createPlanetSphere(radius, mat);
    const cloud = loadTexture("/textures/earth_clouds_1024.png");
    const cloudMesh = createPlanetSphere(radius * 1.012, new THREE.MeshLambertMaterial({ map: cloud, transparent: true, opacity: 0.72 }));
    rootGroup.add(cloudMesh);
    addAtmosphere(radius);
  } else if (preset === "mars") {
    const map = loadTexture("/textures/2k_mars.jpg");
    mesh = createPlanetSphere(
      radius,
      new THREE.MeshStandardMaterial({
        map,
        roughness: 0.96,
        metalness: 0.02,
        bumpMap: map,
        bumpScale: 0.42
      })
    );
  } else if (preset === "jupiter") {
    let map: THREE.Texture;
    try {
      map = loadTexture("/textures/solarsystemscope_texture_2k_jupiter.jpg");
    } catch {
      map = createFallbackStripedTexture();
    }
    map.repeat.set(1.0, 1.0);
    mesh = createPlanetSphere(
      radius,
      new THREE.MeshStandardMaterial({
        map,
        roughness: 0.9,
        metalness: 0.05
      })
    );
  } else if (preset === "saturn") {
    const map = loadTexture("/textures/2k_saturn.jpg");
    mesh = createPlanetSphere(
      radius,
      new THREE.MeshStandardMaterial({
        map,
        roughness: 0.9,
        metalness: 0.05
      })
    );
    const ringAlpha = loadTexture("/textures/8k_saturn_ring_alpha.png", false);
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(radius * 1.28, radius * 2.25, 240),
      new THREE.MeshStandardMaterial({
        color: "#d7c29c",
        map: ringAlpha,
        alphaMap: ringAlpha,
        transparent: true,
        side: THREE.DoubleSide,
        opacity: 0.92
      })
    );
    ring.rotation.x = Math.PI * 0.5;
    rootGroup.add(ring);
  } else if (preset === "sun") {
    const map = loadTexture("/textures/2k_sun.jpg");
    mesh = createPlanetSphere(
      radius,
      new THREE.MeshBasicMaterial({
        map,
        color: "#ffd980"
      })
    );
    const sunLight = new THREE.PointLight("#ffd486", 7.5, 900, 1.35);
    sunLight.position.set(0, 0, 0);
    scene.add(sunLight);
  } else if (preset === "moon") {
    const map = loadTexture("/textures/2k_moon.jpg");
    mesh = createPlanetSphere(
      radius,
      new THREE.MeshStandardMaterial({
        map,
        roughness: 0.99,
        metalness: 0.0,
        bumpMap: map,
        bumpScale: 0.2
      })
    );
  } else if (preset === "neptune") {
    const map = loadTexture("/textures/2k_neptune.jpg");
    mesh = createPlanetSphere(
      radius,
      new THREE.MeshStandardMaterial({
        map,
        roughness: 0.82,
        metalness: 0.04
      })
    );
  } else if (preset === "uranus") {
    mesh = createPlanetSphere(
      radius,
      new THREE.MeshStandardMaterial({
        color: "#87dbe2",
        roughness: 0.78,
        metalness: 0.06
      })
    );
  } else if (preset === "venus") {
    const map = loadTexture("/textures/2k_venus_surface.jpg");
    mesh = createPlanetSphere(
      radius,
      new THREE.MeshStandardMaterial({
        map,
        roughness: 0.9,
        metalness: 0.04
      })
    );
  } else if (preset === "mercury") {
    const map = loadTexture("/textures/2k_mercury.jpg");
    mesh = createPlanetSphere(
      radius,
      new THREE.MeshStandardMaterial({
        map,
        roughness: 0.95,
        metalness: 0.01
      })
    );
  } else if (preset === "pluto") {
    const map = loadTexture("/textures/2k_eris_fictional.jpg");
    mesh = createPlanetSphere(
      radius * 0.88,
      new THREE.MeshStandardMaterial({
        map,
        roughness: 0.98,
        metalness: 0.0,
        bumpMap: map,
        bumpScale: 0.12
      })
    );
  } else if (preset === "asteroid") {
    const map = loadTexture("/textures/2k_ceres_fictional.jpg");
    const geo = new THREE.IcosahedronGeometry(radius * 0.72, 2);
    mesh = new THREE.Mesh(
      geo,
      new THREE.MeshStandardMaterial({
        map,
        roughness: 0.98,
        metalness: 0.01,
        bumpMap: map,
        bumpScale: 0.14
      })
    );
  } else if (preset === "comet") {
    const map = loadTexture("/textures/2k_ceres_fictional.jpg");
    const geo = new THREE.IcosahedronGeometry(radius * 0.64, 2);
    mesh = new THREE.Mesh(
      geo,
      new THREE.MeshStandardMaterial({
        map,
        roughness: 0.98,
        metalness: 0.0,
        bumpMap: map,
        bumpScale: 0.2
      })
    );
    const tail = new THREE.Mesh(
      new THREE.ConeGeometry(radius * 0.32, radius * 4.5, 48, 1, true),
      new THREE.MeshBasicMaterial({
        color: "#9fd3ff",
        transparent: true,
        opacity: 0.22,
        depthWrite: false
      })
    );
    tail.rotation.z = Math.PI * 0.5;
    tail.position.set(-radius * 1.8, 0, 0);
    rootGroup.add(tail);
    const tail2 = new THREE.Mesh(
      new THREE.ConeGeometry(radius * 0.16, radius * 6.3, 48, 1, true),
      new THREE.MeshBasicMaterial({
        color: "#d8f0ff",
        transparent: true,
        opacity: 0.16,
        depthWrite: false
      })
    );
    tail2.rotation.z = Math.PI * 0.5;
    tail2.position.set(-radius * 2.5, 0, 0);
    rootGroup.add(tail2);
  } else if (preset === "nebula" || preset === "galaxy") {
    const nebulaGeo = new THREE.IcosahedronGeometry(radius * 1.05, 3);
    mesh = new THREE.Mesh(
      nebulaGeo,
      new THREE.MeshStandardMaterial({
        color: preset === "nebula" ? "#8455ff" : "#8fd3ff",
        emissive: preset === "nebula" ? "#1f0f3f" : "#10324a",
        roughness: 0.45,
        metalness: 0.2,
        wireframe: true
      })
    );
  } else {
    mesh = createPlanetSphere(
      radius,
      new THREE.MeshStandardMaterial({
        color: payload.color || "#77b7ff",
        emissive: payload.emissive || "#000000",
        roughness: 0.84,
        metalness: 0.12
      })
    );
  }

  if (mesh) rootGroup.add(mesh);
}

function initScene() {
  if (!rootRef.value) return;
  disposeScene();

  const width = Math.max(320, rootRef.value.clientWidth || 960);
  const height = Math.max(320, rootRef.value.clientHeight || 680);

  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x020614);

  camera = new THREE.PerspectiveCamera(48, width / height, 0.1, 5000);
  camera.position.set(0, 12, 120);

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(width, height);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.02;
  rootRef.value.innerHTML = "";
  rootRef.value.appendChild(renderer.domElement);

  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.05;
  controls.enablePan = false;
  controls.autoRotate = false;
  controls.minDistance = 40;
  controls.maxDistance = 260;
  controls.target.set(0, 0, 0);
  controls.update();

  clock = new THREE.Clock();

  const hemi = new THREE.HemisphereLight("#8ab9ff", "#13213c", 0.8);
  const key = new THREE.DirectionalLight("#fef6dc", 2.1);
  key.position.set(88, 44, 72);
  const rim = new THREE.DirectionalLight("#4d88ff", 0.75);
  rim.position.set(-72, -30, -88);
  scene.add(hemi, key, rim);

  createStarfield();
  if (props.model) createModel(props.model);

  animate();
}

function animate() {
  if (!renderer || !scene || !camera || !controls) return;
  rafId = requestAnimationFrame(animate);
  const dt = clock?.getDelta() || 0.016;

  if (rootGroup) {
    rootGroup.rotation.y += dt * 0.22;
  }
  if (blackholeDiskUniforms) {
    blackholeDiskUniforms.uTime.value += dt;
  }
  if (starPoints) {
    starPoints.rotation.y += dt * 0.008;
  }
  controls.update();
  renderer.render(scene, camera);
}

function onResize() {
  if (!rootRef.value || !renderer || !camera) return;
  const width = Math.max(320, rootRef.value.clientWidth || 960);
  const height = Math.max(320, rootRef.value.clientHeight || 680);
  renderer.setSize(width, height);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}

function disposeObject3D(obj: THREE.Object3D) {
  obj.traverse((item) => {
    const mesh = item as THREE.Mesh;
    if (mesh.geometry) mesh.geometry.dispose();
    const material = mesh.material as THREE.Material | THREE.Material[] | undefined;
    if (Array.isArray(material)) material.forEach((m) => m.dispose());
    else material?.dispose();
  });
}

function disposeScene() {
  cancelAnimationFrame(rafId);
  rafId = 0;

  if (rootGroup) {
    disposeObject3D(rootGroup);
    scene?.remove(rootGroup);
    rootGroup = null;
  }
  if (starPoints) {
    starPoints.geometry.dispose();
    (starPoints.material as THREE.Material).dispose();
    scene?.remove(starPoints);
    starPoints = null;
  }
  blackholeDiskUniforms = null;

  controls?.dispose();
  controls = null;

  renderer?.dispose();
  renderer = null;
  scene = null;
  camera = null;
  clock = null;
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
  () => props.model,
  () => initScene(),
  { deep: true }
);
</script>

<template>
  <div class="viewer-shell">
    <div class="viewer-head">
      <strong>{{ title || "3D 天体模型" }}</strong>
      <span class="hint">{{ model?.note || "支持鼠标拖拽、滚轮缩放和自由观察" }}</span>
    </div>
    <div ref="rootRef" class="viewer-root"></div>
  </div>
</template>

<style scoped>
.viewer-shell {
  width: 100%;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.viewer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
}

.hint {
  color: var(--astro-text-secondary);
  font-size: 12px;
}

.viewer-root {
  width: 100%;
  height: 100%;
  min-height: 620px;
  border: 1px solid var(--astro-border);
  border-radius: 8px;
  overflow: hidden;
}

@media (max-width: 900px) {
  .viewer-head {
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
  }

  .viewer-root {
    min-height: 440px;
  }
}
</style>
