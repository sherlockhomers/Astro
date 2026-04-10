<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { register } from "../api";

const router = useRouter();
const route = useRoute();
const form = ref({
  username: "",
  password: "",
  confirmPassword: ""
});
const loading = ref(false);
const errorMessage = ref("");
const successMessage = ref("");

const passwordStrong = computed(() => /^(?=.*[A-Za-z])(?=.*\d).{8,}$/.test(form.value.password));
const canSubmit = computed(
  () =>
    form.value.username.trim().length >= 3 &&
    passwordStrong.value &&
    form.value.password === form.value.confirmPassword
);



async function handleRegister() {
  if (!canSubmit.value) {
    errorMessage.value = "Please complete all validations before sign up.";
    return;
  }
  loading.value = true;
  errorMessage.value = "";
  successMessage.value = "";
  try {
    const res = await register(form.value.username.trim(), form.value.password);
    if (res.ok) {
      successMessage.value = "Registration successful, redirecting to sign in...";
      const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "/app/qa";
      window.setTimeout(() => router.push({ path: "/login", query: { redirect } }), 900);
    } else {
      errorMessage.value = res.message || "Registration failed.";
    }
  } catch {
    errorMessage.value = "Network error.";
  } finally {
    loading.value = false;
  }
}

</script>

<template>
  <div class="register-page">
    <section class="register-intro surface-card">
      <p class="intro-kicker">CREATE ACCOUNT</p>
      <h1>Build your ASTRO workspace</h1>
      <p class="intro-text">
        Get access to intelligent Q&A, image retrieval and 3D astronomical visualization.
      </p>
      <div class="check-list">
        <p>• 用户名至少 3 位</p>
        <p>• 密码需包含字母和数字且不少于 8 位</p>
      </div>
    </section>

    <section class="register-form surface-card">
      <div class="header">
        <p class="panel-title">Sign up</p>
        <p class="panel-subtitle">Complete the fields and verification process</p>
      </div>

      <el-form label-position="top">
        <el-form-item label="Username">
          <el-input v-model="form.username" placeholder="3+ characters" />
        </el-form-item>

        <el-form-item label="Password">
          <el-input v-model="form.password" type="password" show-password placeholder="At least 8 chars with letters and numbers" />
        </el-form-item>
        <el-form-item label="Confirm password">
          <el-input v-model="form.confirmPassword" type="password" show-password />
        </el-form-item>
      </el-form>

      <div class="status-line">
        <el-tag :type="passwordStrong ? 'success' : 'warning'" effect="plain">Password {{ passwordStrong ? "strong" : "weak" }}</el-tag>
      </div>

      <el-alert v-if="errorMessage" :closable="false" type="error" show-icon>{{ errorMessage }}</el-alert>
      <el-alert v-if="successMessage" :closable="false" type="success" show-icon>{{ successMessage }}</el-alert>

      <div class="actions">
        <el-button type="primary" :disabled="!canSubmit" :loading="loading" @click="handleRegister">Sign up</el-button>
        <el-button text @click="router.push('/login')">Already have account</el-button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.register-page {
  min-height: 100vh;
  padding: 28px;
  display: grid;
  grid-template-columns: 1.05fr 0.95fr;
  gap: 16px;
}

.register-intro,
.register-form {
  padding: 28px;
}

.intro-kicker {
  margin: 0 0 8px;
  color: var(--astro-primary);
  font-size: 12px;
  letter-spacing: 1.4px;
}

h1 {
  margin: 0 0 8px;
  font-size: 34px;
}

.intro-text {
  margin: 0;
  color: var(--astro-text-secondary);
  line-height: 1.7;
}

.check-list {
  margin-top: 18px;
  border-top: 1px solid var(--astro-border);
  padding-top: 14px;
  color: var(--astro-text-secondary);
  line-height: 1.8;
}

.header {
  margin-bottom: 8px;
}

.code-row {
  width: 100%;
  display: grid;
  grid-template-columns: 1fr 120px;
  gap: 10px;
}

.status-line {
  display: flex;
  gap: 8px;
  margin: 4px 0 12px;
  flex-wrap: wrap;
}

.actions {
  margin-top: 14px;
  display: flex;
  gap: 8px;
}

@media (max-width: 980px) {
  .register-page {
    grid-template-columns: 1fr;
  }
}
</style>
