import { createRouter, createWebHistory } from "vue-router";
import { ensureSession } from "../api";
import Landing from "../views/Landing.vue";

const router = createRouter({
  history: createWebHistory(),
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
        }
      ]
    }
  ]
});

router.beforeEach(async (to) => {
  const requiresAuth = to.matched.some((record) => Boolean(record.meta?.requiresAuth));
  const guestOnly = to.matched.some((record) => Boolean(record.meta?.guestOnly));

  let loggedIn = false;
  try {
    loggedIn = await ensureSession();
  } catch {
    loggedIn = false;
  }

  if (requiresAuth && !loggedIn) {
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

export default router;
