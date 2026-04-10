import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import Components from "unplugin-vue-components/vite";
import { ElementPlusResolver } from "unplugin-vue-components/resolvers";

export default defineConfig({
  plugins: [
    vue(),
    Components({
      dts: false,
      resolvers: [ElementPlusResolver({ importStyle: "css" })]
    })
  ],
  server: {
    port: 5173
  },
  build: {
    chunkSizeWarningLimit: 900,
    target: "es2020",
    minify: "terser",
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true,
      },
    },
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return;

          if (id.includes("element-plus")) return "element-plus";
          if (id.includes("echarts")) return "echarts";
          if (id.includes("three")) return "three";
          if (id.includes("marked")) return "markdown";
          if (
            id.includes("vue-router") ||
            id.includes("pinia") ||
            id.includes("/vue/")
          ) {
            return "vue-core";
          }
          if (
            id.includes("lucide-vue-next") ||
            id.includes("@element-plus/icons-vue")
          ) {
            return "icons";
          }
          if (id.includes("axios")) return "network";
          return "vendor";
        }
      }
    }
  }
});
