import { createRouter, createWebHistory } from "vue-router";
import { ElMessage } from "element-plus";
import { ensureSession } from "../api";
import Landing from "../views/Landing.vue";

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior() {
    return { top: 0 };
  },
  routes: [
    {
      path: "/",
      name: "Landing",
      component: Landing
    },
    {
      path: "/login",
      name: "Login",
      component: () => import("../views/Login.vue"),
      meta: { guestOnly: true }
    },
    {
      path: "/register",
      name: "Register",
      component: () => import("../views/Register.vue"),
      meta: { guestOnly: true }
    },
    {
      path: "/celestial/:id",
      name: "CelestialDetail",
      component: () => import("../views/CelestialDetail.vue")
    },
    {
      path: "/app",
      component: () => import("../layouts/DashboardLayout.vue"),
      meta: { requiresAuth: true },
      children: [
        {
          path: "",
          redirect: "/app/qa"
        },
        {
          path: "qa",
          name: "QA",
          component: () => import("../views/dashboard/QA.vue")
        },
        {
          path: "image-search",
          name: "ImageSearch",
          component: () => import("../views/dashboard/ImageSearch.vue")
        },
        {
          path: "knowledge",
          name: "Knowledge",
          component: () => import("../views/dashboard/Knowledge.vue")
        },
        {
          path: "starfield",
          name: "Starfield",
          component: () => import("../views/dashboard/Starfield.vue")
        },
        {
          path: "profile",
          name: "Profile",
          component: () => import("../views/dashboard/Profile.vue")
        },
        {
          path: "evaluation",
          name: "Evaluation",
          component: () => import("../views/dashboard/Evaluation.vue")
        },
        {
          path: "tools",
          name: "AstroTools",
          component: () => import("../views/dashboard/AstroTools.vue")
        }
      ]
    },
    {
      path: "/:pathMatch(.*)*",
      name: "NotFound",
      redirect: "/"
    }
  ]
});

// 登录态缓存：只缓存"确认登录成功"的情况，失败不缓存。
// 失败缓存会踩坑 —— 用户在另一个 tab 登录了，本 tab 一直以为没登录。
const SESSION_CACHE_TTL_MS = 30_000;
let sessionValidUntil = 0;

function markSessionValid() {
  sessionValidUntil = Date.now() + SESSION_CACHE_TTL_MS;
}

function isSessionCacheFresh() {
  return sessionValidUntil > Date.now();
}

router.beforeEach(async (to, from) => {
  const requiresAuth = to.matched.some((record) => Boolean(record.meta?.requiresAuth));
  const guestOnly = to.matched.some((record) => Boolean(record.meta?.guestOnly));

  if (!requiresAuth && !guestOnly) {
    return true;
  }

  const token = localStorage.getItem("astro_access_token") || localStorage.getItem("astro_token");

  let loggedIn = false;
  if (token) {
    if (isSessionCacheFresh()) {
      loggedIn = true;
    } else {
      try {
        loggedIn = await ensureSession();
        if (loggedIn) {
          markSessionValid();
        } else {
          sessionValidUntil = 0;
        }
      } catch {
        loggedIn = false;
        sessionValidUntil = 0;
      }
    }
  }

  if (requiresAuth && !loggedIn) {
    if (from.name !== "Login" && from.name !== "Register") {
      ElMessage.warning({ message: "请先登录后再访问", grouping: true });
    }
    return {
      path: "/login",
      query: { redirect: to.fullPath }
    };
  }

  if (guestOnly && loggedIn) {
    return "/app/qa";
  }

  return true;
});

export function resetSessionCache() {
  sessionValidUntil = 0;
}

export default router;
