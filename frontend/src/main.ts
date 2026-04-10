import { createApp } from "vue";
import { createPinia } from "pinia";
import { ElMessage } from "element-plus";
import App from "./App.vue";
import router from "./router";
import { setGlobalErrorHandler } from "./api";
import "./style.css";
import "./styles/theme.css";

const app = createApp(App);
app.use(createPinia());
app.use(router);

setGlobalErrorHandler((message: string, _status: number) => {
  ElMessage.error({ message, grouping: true, duration: 4000 });
});

app.mount("#app");
