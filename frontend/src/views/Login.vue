<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { login } from "../api";

const router = useRouter();
const route = useRoute();
const form = ref({
  username: "",
  password: "",
});
const loading = ref(false);
const errorMessage = ref("");
const successMessage = ref("");

const canSubmit = computed(
  () => form.value.username.trim().length > 0 && form.value.password.trim().length > 0
);

async function handleLogin() {
  if (!canSubmit.value) {
    errorMessage.value = "Please enter username and password.";
    return;
  }

  loading.value = true;
  errorMessage.value = "";
  successMessage.value = "";
  try {
    const res = await login(form.value.username.trim(), form.value.password);
    if (res.ok) {
      successMessage.value = "Sign in success. Redirecting...";
      const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "/app";
      window.setTimeout(() => router.push(redirect), 500);
    } else {
      errorMessage.value = res.message || "Login failed.";
    }
  } catch {
    errorMessage.value = "Network error.";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="auth-page">
    <section class="auth-intro surface-card">
      <p class="intro-kicker">ASTRO ACCESS</p>
      <h1>Sign in to continue your cosmic exploration</h1>
      <p class="intro-text">
        Secure account login for astronomy Q&A, image retrieval, knowledge graph and 3D exploration.
      </p>
      <el-steps :active="1" finish-status="success" simple>
        <el-step title="Identity" />
        <el-step title="Access" />
      </el-steps>
    </section>

    <section class="auth-form-card surface-card">
      <div class="header">
        <p class="panel-title">Sign in</p>
        <p class="panel-subtitle">Use your account credentials</p>
      </div>

      <el-form label-position="top">
        <el-form-item label="Username">
          <el-input v-model="form.username" placeholder="Enter your username" />
        </el-form-item>
        <el-form-item label="Password">
          <el-input v-model="form.password" type="password" show-password placeholder="Enter your password" />
        </el-form-item>
      </el-form>

      <el-alert v-if="errorMessage" :closable="false" type="error" show-icon>{{ errorMessage }}</el-alert>
      <el-alert v-if="successMessage" :closable="false" type="success" show-icon>{{ successMessage }}</el-alert>

      <div class="actions">
        <el-button type="primary" :loading="loading" :disabled="!canSubmit" @click="handleLogin">Sign in</el-button>
        <el-button text @click="router.push('/register')">Create account</el-button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.auth-page {
  min-height: 100vh;
  padding: 28px;
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  gap: 16px;
}

.auth-intro,
.auth-form-card {
  padding: 28px;
}

.intro-kicker {
  margin: 0 0 8px;
  color: var(--astro-primary);
  font-size: 12px;
  letter-spacing: 1.4px;
}

h1 {
  margin: 0 0 10px;
  font-size: 34px;
  line-height: 1.2;
}

.intro-text {
  margin: 0 0 22px;
  color: var(--astro-text-secondary);
  line-height: 1.8;
}

.header {
  margin-bottom: 8px;
}

.actions {
  margin-top: 16px;
  display: flex;
  gap: 8px;
  align-items: center;
}

@media (max-width: 980px) {
  .auth-page {
    grid-template-columns: 1fr;
  }
}
</style>
