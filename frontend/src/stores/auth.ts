import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { login as apiLogin, logout as apiLogout, refreshAuth, me as apiMe } from "../api";

const ACCESS_TOKEN_KEY = "astro_access_token";
const LEGACY_TOKEN_KEY = "astro_token";

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string | null>(
    localStorage.getItem(ACCESS_TOKEN_KEY) || localStorage.getItem(LEGACY_TOKEN_KEY) || null
  );
  const userId = ref<number | null>(null);
  const username = ref<string>("");
  const createdAt = ref<string | null>(null);
  const loading = ref(false);

  const isLoggedIn = computed(() => Boolean(token.value));

  function setToken(t: string | null) {
    token.value = t;
    if (t) {
      localStorage.setItem(ACCESS_TOKEN_KEY, t);
      localStorage.setItem(LEGACY_TOKEN_KEY, t);
    } else {
      localStorage.removeItem(ACCESS_TOKEN_KEY);
      localStorage.removeItem(LEGACY_TOKEN_KEY);
    }
  }

  async function login(user: string, password: string) {
    loading.value = true;
    try {
      const data = await apiLogin(user, password);
      if (data?.ok && (data?.access_token || data?.token)) {
        setToken(data.access_token || data.token);
        userId.value = data.user_id ?? null;
        username.value = data.username ?? user;
      }
      return data;
    } finally {
      loading.value = false;
    }
  }

  async function logout() {
    try {
      await apiLogout();
    } finally {
      setToken(null);
      userId.value = null;
      username.value = "";
      createdAt.value = null;
    }
  }

  async function refresh() {
    try {
      const data = await refreshAuth();
      if (data?.ok && (data?.access_token || data?.token)) {
        setToken(data.access_token || data.token);
        userId.value = data.user_id ?? null;
        username.value = data.username ?? "";
        return true;
      }
      setToken(null);
      return false;
    } catch {
      setToken(null);
      return false;
    }
  }

  async function fetchProfile() {
    if (!token.value) return;
    try {
      const data = await apiMe();
      if (data?.ok) {
        userId.value = data.user_id ?? null;
        username.value = data.username ?? "";
        createdAt.value = data.created_at ?? null;
      }
    } catch {
      // profile fetch is best-effort
    }
  }

  async function ensureSession(): Promise<boolean> {
    if (token.value) return true;
    return refresh();
  }

  return {
    token,
    userId,
    username,
    createdAt,
    loading,
    isLoggedIn,
    setToken,
    login,
    logout,
    refresh,
    fetchProfile,
    ensureSession,
  };
});
