import { defineStore } from "pinia";
import { ref } from "vue";

const QA_PERSIST_KEY = "astro_qa_session_id";

export const useQaStore = defineStore("qa", () => {
  const sessionId = ref(localStorage.getItem(QA_PERSIST_KEY) || "");
  const lastQuestion = ref("");
  const totalAsked = ref(0);

  function setSessionId(id: string) {
    sessionId.value = id;
    localStorage.setItem(QA_PERSIST_KEY, id);
  }

  function recordQuestion(question: string) {
    lastQuestion.value = question;
    totalAsked.value += 1;
  }

  function reset() {
    sessionId.value = "";
    lastQuestion.value = "";
    localStorage.removeItem(QA_PERSIST_KEY);
  }

  return {
    sessionId,
    lastQuestion,
    totalAsked,
    setSessionId,
    recordQuestion,
    reset,
  };
});
