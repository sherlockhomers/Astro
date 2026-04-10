"""Cloud LLM service for answer enhancement.

Uses OpenAI-compatible API (works with OpenAI, DeepSeek, Qwen, etc.)
to enhance or generate answers when local model is insufficient.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger("astrograph")

SYSTEM_PROMPT = """你是一位专业的天文科普助手，名为AstroGraph。你的回答必须满足以下要求：
1. 用简洁、准确、通俗易懂的中文回答天文问题
2. 先给出核心结论，再解释原因和背景
3. 如果涉及数值，使用国际单位（公里、摄氏度、光年等）
4. 回答控制在200-400字，避免过长
5. 不要编造数据，如果不确定请说明
6. 用连贯的段落表达，避免列表和模板腔"""


class CloudLLMService:
    """Lightweight cloud LLM client for answer enhancement."""

    def __init__(self) -> None:
        self._enabled = bool(settings.cloud_llm_enabled) and bool(settings.cloud_llm_api_key)
        self._provider = str(settings.cloud_llm_provider).strip().lower()
        self._api_key = str(settings.cloud_llm_api_key).strip()
        self._model = str(settings.cloud_llm_model).strip() or "gpt-4o-mini"
        self._timeout = max(5.0, float(settings.cloud_llm_timeout_seconds))
        self._max_tokens = max(100, int(settings.cloud_llm_max_tokens))
        self._base_url = self._resolve_base_url()
        self._last_error: str | None = None

    def _resolve_base_url(self) -> str:
        if self._provider == "deepseek":
            return "https://api.deepseek.com/v1"
        if self._provider in ("qwen", "tongyi", "dashscope"):
            return "https://dashscope.aliyuncs.com/compatible-mode/v1"
        return "https://api.openai.com/v1"

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enhance_answer(
        self,
        question: str,
        local_answer: str = "",
        context_snippets: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate or enhance an answer using cloud LLM."""
        if not self._enabled:
            return {"ok": False, "answer": "", "reason": "cloud_llm_disabled"}

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        user_content = f"用户问题：{question.strip()}"
        if local_answer:
            user_content += f"\n\n本地模型初步回答（可能不准确，需要你改写或纠正）：\n{local_answer.strip()}"
        if context_snippets:
            snippets_text = "\n".join([f"- {s}" for s in context_snippets[:5]])
            user_content += f"\n\n知识库参考片段：\n{snippets_text}"
        user_content += "\n\n请给出准确、流畅的中文科普回答："

        messages.append({"role": "user", "content": user_content})

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "messages": messages,
                        "max_tokens": self._max_tokens,
                        "temperature": 0.3,
                        "top_p": 0.9,
                    },
                )
                response.raise_for_status()
                data = response.json()

            answer = ""
            choices = data.get("choices", [])
            if choices:
                answer = str(choices[0].get("message", {}).get("content", "")).strip()

            if not answer:
                self._last_error = "Empty response from cloud LLM"
                return {"ok": False, "answer": "", "reason": "empty_response"}

            self._last_error = None
            return {
                "ok": True,
                "answer": answer,
                "model": self._model,
                "provider": self._provider,
                "usage": data.get("usage", {}),
            }

        except httpx.TimeoutException:
            self._last_error = "Cloud LLM request timed out"
            logger.warning("Cloud LLM timeout for question: %s", question[:80])
            return {"ok": False, "answer": "", "reason": "timeout"}
        except httpx.HTTPStatusError as exc:
            self._last_error = f"Cloud LLM HTTP {exc.response.status_code}"
            logger.warning("Cloud LLM HTTP error: %s", exc)
            return {"ok": False, "answer": "", "reason": f"http_{exc.response.status_code}"}
        except Exception as exc:
            self._last_error = f"Cloud LLM error: {type(exc).__name__}: {exc}"
            logger.warning("Cloud LLM error: %s", exc)
            return {"ok": False, "answer": "", "reason": "error"}

    def get_status(self) -> dict[str, Any]:
        return {
            "enabled": self._enabled,
            "provider": self._provider,
            "model": self._model,
            "last_error": self._last_error,
        }
