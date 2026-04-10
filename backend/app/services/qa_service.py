from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any

from app.config import settings
from app.services import prompt_templates as tpl
from app.services.agent_service import AgentService
from app.services.adaptive_agent_orchestrator import AdaptiveAgentOrchestrator
from app.services.data_service import DataService
from app.services.dynamic_data_service import DynamicDataService
from app.services.graph_service import GraphService
from app.services.image_label_utils import astronomy_label_family, is_catalog_like_title, normalize_astronomy_label
from app.services.image_service import ImageService
from app.services.mcp_tool_service import MCPToolService
from app.services.model_service import ModelService
from app.services.retrieval_service import RetrievalService
from app.services.sqlite_service import get_sqlite_connection
from app.services.web_search_service import WebSearchService

EXOPLANET_PATTERNS = (
    r"\b(?:TOI|HD|K2|Kepler|WASP|TRAPPIST|LHS|GJ|Gliese|CoRoT|HIP|KIC)[-\s]?\d+[A-Za-z]?(?:\s*[bcdefg])?\b",
    r"\b[A-Za-z]{2,8}[-\s]?\d{2,7}\s?[bcdefg]\b",
)


class QAService:
    """End-to-end QA orchestration with model-first summarization."""

    def __init__(
        self,
        data_service: DataService,
        retrieval_service: RetrievalService,
        graph_service: GraphService,
        model_service: ModelService,
        image_service: ImageService | None = None,
        dynamic_service: DynamicDataService | None = None,
        web_service: WebSearchService | None = None,
        mcp_service: MCPToolService | None = None,
    ) -> None:
        self._data_service = data_service
        self._retrieval_service = retrieval_service
        self._graph_service = graph_service
        self._model_service = model_service
        self._image_service = image_service
        self._dynamic_service = dynamic_service
        self._web_service = web_service
        self._agent = AgentService(data_service, retrieval_service, graph_service)
        self._orchestrator = AdaptiveAgentOrchestrator(
            agent_service=self._agent,
            retrieval_service=retrieval_service,
            graph_service=graph_service,
            model_service=model_service,
            dynamic_service=dynamic_service,
            web_service=web_service,
            mcp_service=mcp_service,
        )
        self._session_ctx: dict[str, list[str]] = {}
        self._db_path = settings.sqlite_path
        self._answer_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._cache_hits = 0
        self._cache_misses = 0
        self._cache_evictions = 0
        self._init_db()

    def ask(
        self,
        question: str,
        session_id: str | None = None,
    ) -> tuple[str, list[str], list[dict], str]:
        result = self.ask_detailed(question, session_id)
        return (
            str(result.get("answer", "")).strip(),
            list(result.get("citations", [])),
            list(result.get("graph_path", [])),
            str(result.get("session_id", "")).strip(),
        )

    def ask_detailed_with_timeout(
        self,
        question: str,
        session_id: str | None = None,
        emit_stage: Any | None = None,
        max_total_seconds: float | None = None,
    ) -> dict[str, Any]:
        timeout_sec = float(max_total_seconds or 0)
        if timeout_sec <= 0:
            return self.ask_detailed(question, session_id, emit_stage=emit_stage)

        pool = ThreadPoolExecutor(max_workers=1)
        future = pool.submit(self.ask_detailed, question, session_id, emit_stage)
        try:
            return future.result(timeout=timeout_sec)
        except FuturesTimeoutError as exc:
            future.cancel()
            raise TimeoutError(f"QA pipeline exceeded {timeout_sec:.1f}s") from exc
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    def ask_detailed(
        self,
        question: str,
        session_id: str | None = None,
        emit_stage: Any | None = None,
    ) -> dict[str, Any]:
        emit = emit_stage or (lambda _stage, _payload=None: None)
        started = time.perf_counter()
        sid = session_id or self._new_session_id()

        t0 = time.perf_counter()
        history = self._load_history(sid)
        history_ms = (time.perf_counter() - t0) * 1000
        emit("history", {"message": "正在结合上下文理解你的问题。"})
        contextual_q = self._build_contextual_question(question, history)
        cache_key = self._make_cache_key(contextual_q)
        cached = self._get_cached_answer(cache_key, contextual_q)
        if cached is not None:
            emit("cache", {"message": "命中历史缓存，正在快速整理回答。", "cache_hit": True})
            answer = str(cached.get("answer", "")).strip() or "当前没有足够信息回答这个问题。"
            citations = [str(x).strip() for x in cached.get("citations", []) if str(x).strip()]
            graph_path = list(cached.get("graph_path", []))
            trace = dict(cached.get("trace", {}))
            trace["cache"] = {
                "hit": True,
                "age_seconds": float(cached.get("age_seconds", 0.0)),
            }
            self._remember_turn(sid, question, answer)
            total_ms = (time.perf_counter() - started) * 1000
            return {
                "answer": answer,
                "citations": citations,
                "graph_path": graph_path,
                "mode": "adaptive_rag_agent",
                "session_id": sid,
                "trace": trace,
                "timings_ms": {
                    "history_load": round(history_ms, 2),
                    "cache_lookup": round(float(cached.get("lookup_ms", 0.0)), 2),
                    "orchestrator": 0.0,
                    "fallback": 0.0,
                    "total": round(total_ms, 2),
                },
                "cache": {
                    "hit": True,
                    "enabled": self._cache_enabled(),
                    "stats": self.get_cache_stats(),
                },
            }

        emit("cache", {"message": "正在规划回答路径并准备检索。", "cache_hit": False})
        orchestrator_started = time.perf_counter()
        result = self._orchestrator.run(contextual_q, sid, history, emit_stage=emit)
        orchestrator_ms = (time.perf_counter() - orchestrator_started) * 1000

        answer = str(result.get("answer", "")).strip()
        citations = [str(x).strip() for x in result.get("citations", []) if str(x).strip()]
        graph_path = list(result.get("graph_path", []))
        trace = dict(result.get("trace", {}))
        answer_source = "adaptive_orchestrator"
        fallback_ms = 0.0

        if (not answer) or self._looks_corrupted_answer(answer):
            emit("fallback", {"message": "主链路信息不足，正在补充备用回答。"})
            fallback_started = time.perf_counter()
            fallback = self._agent.answer(contextual_q, history)
            fallback_ms = (time.perf_counter() - fallback_started) * 1000
            answer = str(fallback.get("answer", "")).strip() or "当前没有足够信息回答这个问题。"
            citations = [str(x) for x in fallback.get("citations", []) if str(x).strip()]
            graph_path = list(fallback.get("graph_path", []))
            answer_source = "fallback_agent"

        citations = [c for c in self._dedupe(citations) if not c.startswith("system:")]
        self._remember_turn(sid, question, answer)
        trace["answer_source"] = answer_source
        trace["contextual_question"] = contextual_q
        trace["history_turns"] = len(history)
        trace["cache"] = {"hit": False}
        emit("complete", {"message": "答案已生成，正在准备输出。"})

        if self._should_use_cache(contextual_q):
            self._put_cached_answer(
                cache_key,
                {
                    "answer": answer,
                    "citations": citations,
                    "graph_path": graph_path,
                    "trace": trace,
                },
            )

        total_ms = (time.perf_counter() - started) * 1000
        return {
            "answer": answer,
            "citations": citations,
            "graph_path": graph_path,
            "mode": "adaptive_rag_agent",
            "session_id": sid,
            "trace": trace,
            "timings_ms": {
                "history_load": round(history_ms, 2),
                "cache_lookup": 0.0,
                "orchestrator": round(orchestrator_ms, 2),
                "fallback": round(fallback_ms, 2),
                "total": round(total_ms, 2),
            },
            "cache": {
                "hit": False,
                "enabled": self._cache_enabled(),
                "stats": self.get_cache_stats(),
            },
        }

    def ask_with_image_detailed_with_timeout(
        self,
        question: str,
        image_bytes: bytes,
        filename: str,
        session_id: str | None = None,
        max_total_seconds: float | None = None,
    ) -> dict[str, Any]:
        timeout_sec = float(max_total_seconds or 0)
        if timeout_sec <= 0:
            return self.ask_with_image_detailed(question, image_bytes, filename, session_id)

        pool = ThreadPoolExecutor(max_workers=1)
        future = pool.submit(self.ask_with_image_detailed, question, image_bytes, filename, session_id)
        try:
            return future.result(timeout=timeout_sec)
        except FuturesTimeoutError as exc:
            future.cancel()
            raise TimeoutError(f"Image QA pipeline exceeded {timeout_sec:.1f}s") from exc
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    def build_image_preview(self, question: str, image_bytes: bytes, filename: str) -> dict[str, Any]:
        prediction = self._image_service.predict(filename, image_bytes) if self._image_service else {"ok": False}
        image_payload = (
            self._image_service.search_by_image_bytes(image_bytes, page=1, page_size=3)
            if self._image_service
            else {"items": []}
        )
        focus_name = self._pick_image_focus(prediction, image_payload, question)
        answer = self._compose_grounded_image_answer(
            question=question,
            focus_name=focus_name,
            prediction=prediction,
            image_payload=image_payload,
            rag_items=[],
        )
        return {
            "focus_name": focus_name,
            "prediction": prediction,
            "image_payload": image_payload,
            "answer": answer,
        }

    def ask_with_image_detailed(
        self,
        question: str,
        image_bytes: bytes,
        filename: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        sid = session_id or self._new_session_id()
        image_sha1 = hashlib.sha1(image_bytes).hexdigest()
        cache_probe_question = f"[image]{question.strip()}::{image_sha1}"
        cache_key = self._make_cache_key(cache_probe_question)
        cached = self._get_cached_answer(cache_key, cache_probe_question)
        if cached is not None:
            answer = str(cached.get("answer", "")).strip() or "\u6682\u65f6\u6ca1\u6709\u62ff\u5230\u7a33\u5b9a\u7ed3\u679c\uff0c\u8bf7\u6362\u4e00\u5f20\u66f4\u6e05\u6670\u7684\u56fe\u7247\u518d\u8bd5\u3002"
            citations = [str(x).strip() for x in cached.get("citations", []) if str(x).strip()]
            graph_path = list(cached.get("graph_path", []))
            self._remember_turn(sid, question, answer)
            total_ms = (time.perf_counter() - started) * 1000
            return {
                "answer": answer,
                "citations": citations,
                "graph_path": graph_path,
                "mode": "image_grounded_agent",
                "session_id": sid,
                "trace": {"cache": {"hit": True}, "image_sha1": image_sha1},
                "timings_ms": {"total": round(total_ms, 2)},
                "cache": {"hit": True, "enabled": self._cache_enabled(), "stats": self.get_cache_stats()},
            }

        prediction = self._image_service.predict(filename, image_bytes) if self._image_service else {"ok": False}
        image_payload = (
            self._image_service.search_by_image_bytes(image_bytes, page=1, page_size=3)
            if self._image_service
            else {"items": []}
        )
        focus_name = self._pick_image_focus(prediction, image_payload, question)
        analysis = {"intent": "image_qa", "entities": [focus_name] if focus_name else []}
        query_for_kb = self._build_image_grounded_query(question, focus_name, prediction)
        generic_identification = self._is_generic_image_identification_question(question)
        prediction_confidence = self._as_float(prediction.get("confidence"))
        image_items = list(image_payload.get("items", []))
        top_image_score = self._as_float(image_items[0].get("score")) if image_items else None
        top_image_title = str(image_items[0].get("title", "")).strip() if image_items else ""
        retrieval_strong = bool(
            image_items
            and isinstance(top_image_score, float)
            and top_image_score >= 0.70
            and focus_name
        )

        rag_items: list[dict[str, Any]] = []
        need_kb_grounding = bool(focus_name) and not (
            generic_identification
            and (
                retrieval_strong
                or (isinstance(prediction_confidence, float) and prediction_confidence >= 0.72 and bool(top_image_title))
            )
        )
        if need_kb_grounding:
            try:
                retrieved, _ = self._retrieval_service.search(query_for_kb, top_k=3)
            except Exception:
                retrieved = []
            for item in retrieved:
                source = str(item.get("source", "")).strip().lower()
                if source == "mock":
                    continue
                score = self._as_float(item.get("score")) or 0.0
                if score < 0.42:
                    continue
                rag_items.append(
                    {
                        "title": str(item.get("title", "")).strip(),
                        "source": source or "kb",
                        "snippet": str(item.get("snippet", "")).strip()[:420],
                        "score": score,
                    }
                )
            entity = self._agent.find_entity_by_name(focus_name)
            if entity:
                rag_items.insert(
                    0,
                    {
                        "title": str(entity.get("name", focus_name)).strip(),
                        "source": str(entity.get("source_file", "entity")).strip() or "entity",
                        "snippet": str(entity.get("description", "")).strip()[:420],
                        "score": 1.1,
                    },
                )

        grounded_answer = self._compose_grounded_image_answer(
            question=question,
            focus_name=focus_name,
            prediction=prediction,
            image_payload=image_payload,
            rag_items=rag_items,
        )

        model_answer = ""
        model_citations: list[str] = []
        allow_direct_grounded_answer = generic_identification and (
            retrieval_strong
            or (
                isinstance(prediction_confidence, float)
                and prediction_confidence >= 0.72
                and bool(rag_items)
                and bool(focus_name)
            )
        )

        if self._model_service.vision_ready and not allow_direct_grounded_answer:
            ok, payload = self._model_service.answer_with_image(
                question=question,
                image_bytes=image_bytes,
                filename=filename,
                context={
                    "focus_name": focus_name,
                    "prediction": prediction,
                    "similar_images": list(image_payload.get("items", []))[:3],
                    "rag_items": rag_items[:4],
                },
            )
            if ok:
                model_answer, model_citations = self._extract_model_output(payload)
                model_answer = self._clean_user_facing_answer(model_answer)
                if not self._image_model_answer_looks_relevant(question, focus_name, model_answer):
                    model_answer = ""
                    model_citations = []

        if not model_answer and not allow_direct_grounded_answer and self._model_service.ready and (focus_name or rag_items):
            prompt = self._build_image_text_prompt(question, focus_name, prediction, image_payload, rag_items)
            ok, payload = self._call_model_with_timeout(
                prompt,
                {
                    "analysis": analysis,
                    "rag_items": rag_items[:4],
                    "image_prediction": prediction,
                    "image_results": list(image_payload.get("items", []))[:3],
                },
                timeout_sec=max(8.0, float(getattr(settings, "qa_image_timeout_seconds", 30.0)) * 0.65),
            )
            if ok:
                model_answer, model_citations = self._extract_model_output(payload)
                model_answer = self._clean_user_facing_answer(model_answer)
                if not self._image_model_answer_looks_relevant(question, focus_name, model_answer):
                    model_answer = ""
                    model_citations = []

        answer = model_answer or grounded_answer or "\u6211\u8fd8\u4e0d\u80fd\u7a33\u5b9a\u8bc6\u522b\u8fd9\u5f20\u56fe\u7247\u91cc\u7684\u5929\u4f53\u3002\u5efa\u8bae\u6362\u4e00\u5f20\u66f4\u6e05\u6670\u3001\u4e3b\u4f53\u66f4\u5c45\u4e2d\u7684\u56fe\u7247\u518d\u8bd5\u3002"
        citations = self._dedupe(model_citations + self._image_citations(image_payload))
        graph_path: list[dict[str, Any]] = []

        self._remember_turn(sid, question, answer)
        self._put_cached_answer(
            cache_key,
            {
                "answer": answer,
                "citations": citations,
                "graph_path": graph_path,
                "trace": {
                    "focus_name": focus_name,
                    "prediction": prediction,
                    "image_result_count": len(list(image_payload.get("items", []))),
                },
            },
        )

        total_ms = (time.perf_counter() - started) * 1000
        return {
            "answer": answer,
            "citations": citations,
            "graph_path": graph_path,
            "mode": "image_grounded_agent",
            "session_id": sid,
            "trace": {
                "focus_name": focus_name,
                "prediction": prediction,
                "image_result_count": len(list(image_payload.get("items", []))),
                "cache": {"hit": False},
            },
            "timings_ms": {"total": round(total_ms, 2)},
            "cache": {"hit": False, "enabled": self._cache_enabled(), "stats": self.get_cache_stats()},
        }

    def _pick_image_focus(self, prediction: dict[str, Any], image_payload: dict[str, Any], question: str) -> str:
        votes: dict[str, float] = {}
        predicted_name = self._normalize_image_entity_name(str(prediction.get("name", "") or prediction.get("label", "")).strip())
        prediction_confidence = self._as_float(prediction.get("confidence")) or 0.0
        if predicted_name:
            votes[predicted_name] = votes.get(predicted_name, 0.0) + max(0.58, prediction_confidence)

        for idx, item in enumerate(list(image_payload.get("items", []))[:3]):
            name = self._normalize_image_entity_name(str(item.get("title", "")).strip())
            if not name:
                continue
            weight = 1.35 if idx == 0 else 0.55 if idx == 1 else 0.35
            score = self._as_float(item.get("score")) or 0.0
            votes[name] = votes.get(name, 0.0) + score * weight

        question_lower = str(question or "").lower()
        for name in ["太阳", "水星", "金星", "地球", "月球", "火星", "木星", "土星", "天王星", "海王星", "冥王星", "黑洞"]:
            if name in question_lower:
                votes[name] = votes.get(name, 0.0) + 1.2

        if votes:
            best = max(votes, key=votes.get)
            if best.lower() != "unknown":
                if astronomy_label_family(best) == "black_hole":
                    return "黑洞"
                return best
        return ""

    @staticmethod
    def _contains_cjk(text: str) -> bool:
        return bool(re.search(r"[\u4e00-\u9fff]", str(text or "")))

    @staticmethod
    def _is_generic_image_identification_question(question: str) -> bool:
        q = str(question or "").strip().lower()
        if not q:
            return False
        patterns = [
            "\u8fd9\u662f\u4ec0\u4e48",
            "\u8fd9\u662f\u4ec0\u4e48\u5929\u4f53",
            "\u56fe\u91cc\u662f\u4ec0\u4e48",
            "\u56fe\u7247\u91cc\u662f\u4ec0\u4e48",
            "\u8bc6\u522b\u8fd9\u4e2a\u5929\u4f53",
            "what is this",
            "what celestial body",
            "identify this object",
        ]
        return any(token in q for token in patterns)

    def _normalize_image_entity_name(self, raw_name: str) -> str:
        raw = str(raw_name or "").strip()
        if not raw:
            return ""
        if raw.lower() in {"unknown", "none", "n/a"}:
            return ""
        normalized = normalize_astronomy_label(raw)
        if normalized:
            return normalized
        canonical_names = [
            "太阳", "水星", "金星", "地球", "月球", "火星", "木星", "土星",
            "天王星", "海王星", "冥王星", "黑洞", "超大质量黑洞", "恒星级黑洞", "中等质量黑洞",
            "银河系", "星云", "行星状星云", "发射星云", "反射星云", "彗星", "小行星", "小行星带",
            "旋涡星系", "椭圆星系", "不规则星系", "木卫一", "木卫二", "木卫三", "木卫四", "土卫六",
        ]
        lowered = raw.lower()
        alias_map = {
            "moon": "月球",
            "sun": "太阳",
            "mercury": "水星",
            "venus": "金星",
            "earth": "地球",
            "mars": "火星",
            "jupiter": "木星",
            "saturn": "土星",
            "uranus": "天王星",
            "neptune": "海王星",
            "pluto": "冥王星",
            "black hole": "黑洞",
            "supermassive black hole": "超大质量黑洞",
            "stellar black hole": "恒星级黑洞",
            "intermediate black hole": "中等质量黑洞",
            "nebula": "星云",
            "planetary nebula": "行星状星云",
            "emission nebula": "发射星云",
            "reflection nebula": "反射星云",
            "spiral galaxy": "旋涡星系",
            "elliptical galaxy": "椭圆星系",
            "irregular galaxy": "不规则星系",
            "galaxy": "星系",
            "comet": "彗星",
            "asteroid": "小行星",
            "asteroid belt": "小行星带",
            "constellation": "星座",
            "international space station": "国际空间站",
            "space station": "空间站",
        }
        if lowered in alias_map:
            return alias_map[lowered]
        for name in canonical_names:
            if name in raw:
                return name
        for alias, name in alias_map.items():
            if alias in lowered:
                return name
        entity = self._data_service.find_best_entity_for_question(raw)
        if entity:
            return str(entity.get("name", "")).strip()
        return raw

    def _build_image_grounded_query(self, question: str, focus_name: str, prediction: dict[str, Any]) -> str:
        q = str(question or "").strip()
        if focus_name and focus_name not in q:
            return f"{focus_name} {q}".strip()
        predicted = str(prediction.get("label", "")).strip()
        if predicted and predicted not in q:
            return f"{q} {predicted}".strip()
        return q

    def _image_model_answer_looks_relevant(self, question: str, focus_name: str, answer: str) -> bool:
        text = str(answer or "").strip()
        if not text or len(text) < 8:
            return False
        if self._contains_cjk(question) and not self._contains_cjk(text):
            return False
        generic = any(token in str(question or "") for token in [
            "这是什么",
            "这是什么天体",
            "图里是什么",
            "图片里是什么",
            "识别这个天体",
        ])
        if generic and focus_name and focus_name not in text:
            return False
        if re.search(r"(/api/v1|internal|pipeline|tool_plan|system:)", text.lower()):
            return False
        return True

    def _build_image_text_prompt(
        self,
        question: str,
        focus_name: str,
        prediction: dict[str, Any],
        image_payload: dict[str, Any],
        rag_items: list[dict[str, Any]],
    ) -> str:
        refs: list[str] = []
        for item in rag_items[:4]:
            refs.append(f"- [{item.get('source', 'kb')}] {item.get('title', '')}: {str(item.get('snippet', ''))[:220]}")
        similar = []
        for item in list(image_payload.get("items", []))[:3]:
            similar.append(f"- {item.get('title', '')}，相似度 {float(item.get('score', 0.0)):.2f}")
        predicted = str(prediction.get("name", "") or prediction.get("label", "") or focus_name).strip() or "未知天体"
        prompt = [
            "你是天文科普助手。请根据给定的视觉识别线索和知识片段，回答用户的识图问题。",
            "要求：先直接判断图中主体是什么，再用1到2段自然中文解释，不要输出后台术语，不要编造看不见的细节。",
            f"用户问题：{question}",
            f"候选主体：{predicted}",
        ]
        if similar:
            prompt.append("相似图片结果：")
            prompt.extend(similar)
        if refs:
            prompt.append("知识参考：")
            prompt.extend(refs)
        prompt.append("请输出面向普通用户的中文科普回答。")
        return "\n".join(prompt)

    def _compose_grounded_image_answer(
        self,
        question: str,
        focus_name: str,
        prediction: dict[str, Any],
        image_payload: dict[str, Any],
        rag_items: list[dict[str, Any]],
    ) -> str:
        if not focus_name:
            return ""

        generic = any(token in str(question or "") for token in [
            "这是什么",
            "这是什么天体",
            "图里是什么",
            "图片里是什么",
            "识别这个天体",
        ])
        confidence = self._as_float(prediction.get("confidence"))
        confidence_text = f"识别置信度约 {confidence:.2f}" if isinstance(confidence, float) else ""
        top_item = list(image_payload.get("items", []))[:1]
        top_title = str(top_item[0].get("title", "")).strip() if top_item else ""
        description = ""
        if rag_items:
            description = str(rag_items[0].get("snippet", "")).strip()
        if not description and focus_name:
            entity = self._agent.find_entity_by_name(focus_name)
            if entity:
                description = str(entity.get("description", "")).strip()

        focus_blurb = self._image_focus_brief(focus_name)
        lead = f"这张图里的主体更接近{focus_name}。" if generic else f"结合图片特征和检索结果，这张图更可能是{focus_name}。"
        details: list[str] = [lead]
        if focus_blurb:
            details.append(focus_blurb)
        if description:
            first = re.split(r"[。！？.!?]", description, maxsplit=1)[0].strip()
            if first and first not in "".join(details):
                details.append(first + "。")
        elif confidence_text and not focus_blurb:
            details.append(f"当前判断的识别置信度约为 {confidence_text.replace('识别置信度约 ', '')}。")
        if top_title and not is_catalog_like_title(top_title):
            normalized_top = self._normalize_image_entity_name(top_title)
            if normalized_top and normalized_top != focus_name and astronomy_label_family(normalized_top) != astronomy_label_family(focus_name):
                details.append(f"相似结果也更接近{normalized_top}。")
        return "".join(details).strip()

    @staticmethod
    def _image_focus_brief(focus_name: str) -> str:
        blurbs = {
            "月球": "它通常表现为灰白色球体，表面布满陨石坑和月海区域。",
            "火星": "它通常呈现偏红或橙红色外观，常见暗色地形和极冠特征。",
            "木星": "它常出现明显的带状云层结构，颜色以浅黄和棕色为主。",
            "土星": "它最突出的特征是宽阔明亮的行星环和淡黄色盘面。",
            "天王星": "它通常呈均匀的青蓝色，盘面纹理较少。",
            "海王星": "它常呈深蓝色，局部可能出现高层云或暗色风暴。",
            "彗星": "它常有明亮彗核与向外延伸的彗尾，尾部方向受太阳风影响。",
            "小行星": "它更常呈不规则岩石质外观，而不是规则的球形盘面。",
            "小行星带": "这类图像通常展示大量小天体沿轨道带分布的整体结构。",
            "超大质量黑洞": "这类图像常以中心暗区、周围高温吸积盘或喷流结构来表现强引力环境。",
            "恒星级黑洞": "这类图像多通过吸积盘或伴星物质被吸积的示意来呈现。",
            "中等质量黑洞": "它通常以吸积盘或致密引力中心的可视化示意出现。",
            "黑洞": "这类图像常以中心暗区和周围发光吸积盘来表现极强引力环境。",
            "旋涡星系": "它通常具有清晰的旋臂结构，恒星和尘埃沿盘面向外盘旋分布。",
            "椭圆星系": "它通常呈较平滑的椭圆形光斑，缺少明显旋臂结构。",
            "不规则星系": "它没有稳定对称的盘面或旋臂结构，形态往往更散乱。",
            "行星状星云": "它通常呈环状或壳层状亮斑，是恒星晚期抛射气体形成的星云。",
            "发射星云": "它常出现红色或粉红色发光区域，来自被年轻恒星电离的气体。",
            "反射星云": "它常呈蓝色雾状结构，主要由尘埃反射附近恒星的光形成。",
            "星云": "它通常表现为大范围弥散的发光或反光云气结构。",
        }
        return blurbs.get(str(focus_name or "").strip(), "")

    def _select_best_answer(
        self,
        question: str,
        analysis: dict[str, Any],
        model_answer: str | None,
        base_answer: str,
        dynamic_payload: dict[str, Any] | None,
        web_payload: dict[str, Any] | None,
        prefer_web: bool = False,
    ) -> tuple[str, bool]:
        if model_answer and self._model_answer_looks_relevant(question, analysis, model_answer):
            return model_answer.strip(), True

        if dynamic_payload is not None:
            return self._compose_dynamic_answer(dynamic_payload), False

        base_relevant = self._answer_looks_relevant(question, analysis, base_answer)
        if web_payload is not None and (prefer_web or self._is_weak_answer(base_answer) or not base_relevant):
            return self._compose_web_answer(web_payload), False

        if base_answer.strip() and base_relevant:
            return base_answer.strip(), False

        return "当前没有足够信息回答这个问题。你可以换一个更具体的问法。", False

    def _compose_dynamic_answer(self, payload: dict[str, Any]) -> str:
        name = str(payload.get("name") or payload.get("requested_name") or "目标天体").strip()
        host = str(payload.get("host_star") or "未知").strip()
        year = payload.get("discovery_year")
        method = str(payload.get("discovery_method") or "未知").strip()
        mass = payload.get("mass_earth")
        radius = payload.get("radius_earth")
        period = payload.get("orbital_period_days")
        dist = payload.get("distance_pc")

        def fmt(v: Any, digits: int = 2) -> str:
            if isinstance(v, (int, float)):
                return f"{float(v):.{digits}f}".rstrip("0").rstrip(".")
            if v in (None, "", "unknown"):
                return "未知"
            return str(v)

        return (
            f"{name} 的公开数据如下：\n"
            f"- 宿主恒星：{host}；发现年份：{fmt(year, 0)}；发现方式：{method}\n"
            f"- 质量约 {fmt(mass)} 倍地球；半径约 {fmt(radius)} 倍地球\n"
            f"- 轨道周期约 {fmt(period)} 天；距离约 {fmt(dist)} pc"
        )

    def _compose_web_answer(self, payload: dict[str, Any]) -> str:
        title = str(payload.get("title") or "").strip()
        summary = str(payload.get("summary") or "").strip()
        url = str(payload.get("url") or "").strip()
        if not summary:
            return "暂时未能获取到可用的联网资料。"
        first_sent = re.split(r"[。.!?！？]", summary, maxsplit=1)[0].strip()
        lines: list[str] = []
        if first_sent:
            lines.append(f"结论：{first_sent}")
            lines.append("")
        if title:
            lines.append(f"补充说明（来源词条：{title}）：")
        lines.append(summary)
        if url:
            lines.append("")
            lines.append(f"参考来源：{url}")
        return "\n".join(lines).strip()

    def _append_image_results(self, answer: str, items: list[dict[str, Any]]) -> str:
        lines = [answer.strip(), "", "相关图片："]
        for idx, item in enumerate(items, start=1):
            title = str(item.get("title", "")).strip() or f"result-{idx}"
            score = item.get("score")
            score_txt = f"{float(score):.3f}" if isinstance(score, (int, float)) else "-"
            image_url = str(item.get("image_url", "")).strip()
            lines.append(f"{idx}. {title}（匹配度 {score_txt}）：{image_url}")
        return "\n".join(lines).strip()

    def _try_model_enhance(
        self,
        question: str,
        history: list[str],
        analysis: dict[str, Any],
        agent_result: dict[str, Any],
        dynamic_payload: dict[str, Any] | None,
        image_payload: dict[str, Any] | None,
        web_payload: dict[str, Any] | None,
    ) -> tuple[str | None, list[str]]:
        if not self._model_service.ready:
            return None, []

        rag_items = self._build_model_rag_items(
            question=question,
            analysis=analysis,
            dynamic_payload=dynamic_payload,
            image_payload=image_payload,
            web_payload=web_payload,
        )

        timeout_sec = max(18.0, float(getattr(settings, "model_enhance_timeout_seconds", 90.0)))
        agent_answer = str(agent_result.get("answer", "")).strip()
        safe_analysis = {
            "intent": str(analysis.get("intent", "general")),
            "entities": [str(x) for x in analysis.get("entities", [])[:4]],
            "tool_plan": [str(x) for x in analysis.get("tool_plan", [])[:4]],
        }

        attempts = [
            {
                "history": history[-5:],
                "analysis": safe_analysis,
                "agent_answer": "",
                "rag_items": rag_items[:5],
                "pipeline_steps": ["问题分析", "相关知识检索", "模型总结"],
                "constraints": (
                    "仅输出面向用户的最终答案。"
                    "如果参考资料不相关，优先基于天文常识直接回答。"
                    "不要输出系统状态、工具计划或报错。"
                ),
            },
            {
                "history": history[-2:],
                "analysis": {"intent": safe_analysis["intent"], "entities": safe_analysis["entities"][:2]},
                "agent_answer": "",
                "rag_items": rag_items[:2],
                "pipeline_steps": ["直接回答"],
                "constraints": "直接回答问题并保持科普风格，不输出内部状态。",
            },
        ]

        for idx, ctx in enumerate(attempts):
            ok, result = self._call_model_with_timeout(question, ctx, timeout_sec if idx == 0 else max(12.0, timeout_sec * 0.55))
            if not ok:
                continue
            text, cits = self._extract_model_output(result)
            cleaned = self._clean_user_facing_answer(text)
            if cleaned:
                if not cits:
                    cits = ["model:starwhisper"]
                return cleaned, cits
        return None, []

    def _build_model_rag_items(
        self,
        question: str,
        analysis: dict[str, Any],
        dynamic_payload: dict[str, Any] | None,
        image_payload: dict[str, Any] | None,
        web_payload: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        rag_items: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add_item(title: str, source: str, snippet: str) -> None:
            t = str(title or "").strip()
            s = str(source or "").strip()
            p = str(snippet or "").strip()
            if not (t or p):
                return
            key = f"{t.lower()}|{s.lower()}|{p[:80].lower()}"
            if key in seen:
                return
            seen.add(key)
            rag_items.append({"title": t, "source": s, "snippet": p[:420]})

        try:
            retrieved, _ = self._retrieval_service.search(question, top_k=6)
        except Exception:
            retrieved = []
        for item in retrieved:
            source = str(item.get("source", "")).strip()
            if source.lower() == "mock":
                continue
            score = self._as_float(item.get("score"))
            if score is not None and score < 0.55:
                continue
            add_item(
                title=str(item.get("title", "")),
                source=source or "retrieval",
                snippet=str(item.get("snippet", "")),
            )

        for ent_name in analysis.get("entities", [])[:3]:
            entity = self._agent.find_entity_by_name(str(ent_name))
            if entity:
                add_item(
                    title=str(entity.get("name", "")),
                    source=str(entity.get("source_file", "")) or "entity",
                    snippet=str(entity.get("description", "")),
                )

        if dynamic_payload:
            add_item(
                title=str(dynamic_payload.get("name", "")),
                source=str(dynamic_payload.get("provider", "dynamic")),
                snippet=str(dynamic_payload),
            )
        if web_payload:
            add_item(
                title=str(web_payload.get("title", "")),
                source=str(web_payload.get("provider", "web")),
                snippet=str(web_payload.get("summary", "")),
            )
        if isinstance(image_payload, dict):
            for item in list(image_payload.get("items", []))[:2]:
                add_item(
                    title=str(item.get("title", "")),
                    source=str(item.get("source", "image_search")),
                    snippet=f"image_url={item.get('image_url', '')}",
                )

        return rag_items

    def _call_model_with_timeout(
        self,
        question: str,
        context: dict[str, Any],
        timeout_sec: float,
    ) -> tuple[bool, dict[str, Any] | str]:
        pool = ThreadPoolExecutor(max_workers=1)
        future = pool.submit(self._model_service.answer, question, context)
        try:
            return future.result(timeout=max(6.0, float(timeout_sec)))
        except Exception:
            future.cancel()
            return False, ""
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    def _extract_model_output(self, result: dict[str, Any] | str) -> tuple[str, list[str]]:
        if isinstance(result, dict):
            text = str(result.get("answer", "") or result.get("text", "")).strip()
            cits = [str(x).strip() for x in result.get("citations", []) if str(x).strip()]
            return text, cits

        raw = str(result or "").strip()
        if not raw:
            return "", []
        if raw.startswith("{") and raw.endswith("}"):
            try:
                payload = json.loads(raw)
                if isinstance(payload, dict):
                    text = str(payload.get("answer", "") or payload.get("text", "")).strip()
                    cits = [str(x).strip() for x in payload.get("citations", []) if str(x).strip()]
                    if text:
                        return text, cits
            except Exception:
                pass
        return raw, []

    def _clean_user_facing_answer(self, text: str) -> str:
        if not text:
            return ""
        banned_fragments = (
            "STARWHISPER_REQUIRED",
            "/api/v1/model/status",
            "内部状态",
            "tool_plan",
            "pipeline_steps",
        )
        dropped_prefixes = (
            "问题分析",
            "意图:",
            "实体:",
            "最终回答",
            "analysis:",
            "intent:",
            "entities:",
        )

        kept_lines: list[str] = []
        for line in str(text).splitlines():
            stripped = line.strip()
            if not stripped:
                kept_lines.append("")
                continue
            lower = stripped.lower()
            if any(token.lower() in lower for token in banned_fragments):
                continue
            if any(stripped.startswith(prefix) for prefix in dropped_prefixes):
                continue
            kept_lines.append(line.rstrip())
        cleaned = "\n".join(kept_lines).strip()
        return cleaned

    @staticmethod
    def _as_float(value: Any) -> float | None:
        try:
            return float(value)
        except Exception:
            return None

    def _pick_dynamic_target(
        self,
        question: str,
        analysis: dict[str, Any],
        agent_result: dict[str, Any],
    ) -> str | None:
        for token in self._extract_exoplanet_tokens(question):
            return token
        if not self._question_requests_dynamic(question):
            return None
        for name in analysis.get("entities", []):
            n = str(name).strip()
            if self._is_exoplanet_name(n):
                return n
        for name in agent_result.get("entities_found", []):
            n = str(name).strip()
            if self._is_exoplanet_name(n):
                return n
        return None

    def _question_requests_dynamic(self, question: str) -> bool:
        q = str(question or "").lower()
        return any(
            k in q
            for k in [
                "最新",
                "最近",
                "实时",
                "今天",
                "系外行星",
                "latest",
                "recent",
                "real-time",
                "exoplanet",
                "nasa",
            ]
        )

    def _question_requests_web(self, question: str, analysis: dict[str, Any], base_answer: str) -> bool:
        if not self._web_service or not self._web_service.enabled:
            return False
        q = str(question or "").lower()
        if any(k in q for k in ["最新", "最近", "实时", "今天", "联网", "搜索", "latest", "recent", "today", "current", "news"]):
            return True
        if any(
            k in q
            for k in [
                "多少",
                "多大",
                "多远",
                "温度",
                "体积",
                "半径",
                "直径",
                "质量",
                "为什么",
                "怎么",
                "how",
                "why",
                "temperature",
                "distance",
                "mass",
                "radius",
            ]
        ):
            return True
        if self._is_weak_answer(base_answer):
            return True
        intent = str(analysis.get("intent", ""))
        return intent in {"science_qa", "general", "fact_query"} and len(q) >= 4

    def _question_needs_image_output(self, question: str) -> bool:
        q = str(question or "").lower()
        return any(k in q for k in ["图片", "图像", "照片", "image", "photo", "搜图", "以图搜图", "以文搜图"])

    def _build_web_query(self, question: str, analysis: dict[str, Any], agent_result: dict[str, Any]) -> str:
        q = str(question or "").strip()
        if not q:
            return q

        fixed_terms = [
            "宇宙",
            "太阳",
            "地球",
            "月球",
            "火星",
            "木星",
            "土星",
            "金星",
            "水星",
            "天王星",
            "海王星",
            "冥王星",
            "银河系",
            "仙女座",
            "黑洞",
            "中子星",
            "超新星",
            "白矮星",
            "行星",
            "恒星",
            "彗星",
            "小行星",
            "星云",
        ]
        matched_terms = [t for t in fixed_terms if t in q]
        if matched_terms:
            metric_terms = [
                k
                for k in ["温度", "距离", "半径", "质量", "体积", "年龄", "直径", "速度", "轨道周期", "多大", "多远"]
                if k in q
            ]
            return " ".join(matched_terms[:2] + metric_terms[:1]).strip()

        generic_terms = {"天体", "行星", "恒星", "卫星", "星系", "星云", "宇宙"}
        entities: list[str] = []
        for name in analysis.get("entities", []):
            n = str(name).strip()
            if n and n not in entities:
                entities.append(n)
        for name in agent_result.get("entities_found", []):
            n = str(name).strip()
            if n and n not in entities:
                entities.append(n)

        focus = ""
        for n in entities:
            if len(n) >= 2 and n not in generic_terms:
                focus = n
                break
        if not focus and entities:
            focus = entities[0]

        metric_terms = [
            k
            for k in ["温度", "距离", "半径", "质量", "体积", "年龄", "直径", "速度", "轨道周期", "多大", "多远"]
            if k in q
        ]
        if focus:
            return " ".join([focus] + metric_terms[:2]).strip()
        return q

    def _answer_looks_relevant(self, question: str, analysis: dict[str, Any], answer: str) -> bool:
        q = str(question or "").strip().lower()
        a = str(answer or "").strip().lower()
        if not a:
            return False
        if len(a) < 36:
            return False

        entities = [str(x).strip().lower() for x in analysis.get("entities", []) if str(x).strip()]
        for ent in entities[:4]:
            if len(ent) >= 2 and ent in q and ent not in a:
                return False

        anchor_terms = [
            "宇宙",
            "太阳",
            "地球",
            "月球",
            "火星",
            "木星",
            "土星",
            "金星",
            "水星",
            "黑洞",
            "银河系",
            "仙女座",
            "系外行星",
            "中子星",
            "超新星",
        ]
        q_anchors = [t for t in anchor_terms if t in q]
        if q_anchors:
            hit_count = sum(1 for t in q_anchors if t in a)
            if len(q_anchors) == 1 and hit_count < 1:
                return False
            if len(q_anchors) >= 2 and hit_count < min(2, len(q_anchors)):
                return False

        need_number = any(k in q for k in ["多少", "多大", "多远", "温度", "距离", "质量", "半径", "体积", "速度"])
        if need_number and not re.search(r"\d", a):
            return False

        q_keywords = self._question_keywords(q)
        if q_keywords:
            kw_hit = sum(1 for k in q_keywords if k in a)
            required = 1 if len(q_keywords) <= 2 else 2
            if kw_hit < required:
                return False

        return True

    def _model_answer_looks_relevant(self, question: str, analysis: dict[str, Any], answer: str) -> bool:
        return self._answer_looks_relevant(question, analysis, answer)

    @staticmethod
    def _question_keywords(text: str) -> list[str]:
        tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[a-z][a-z0-9\-]{2,}", text.lower())
        if not tokens:
            return []
        stop = {
            "什么",
            "怎么",
            "如何",
            "为什么",
            "多少",
            "多大",
            "多远",
            "分别",
            "一下",
            "一下子",
            "现在",
            "目前",
            "已知",
            "以及",
            "或者",
            "这个",
            "那个",
            "以及",
            "and",
            "the",
            "what",
            "why",
            "how",
            "much",
            "many",
        }
        out: list[str] = []
        seen: set[str] = set()
        for t in tokens:
            if t in stop:
                continue
            if len(t) < 2:
                continue
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
        return out[:6]

    def _is_weak_answer(self, answer: str) -> bool:
        text = str(answer or "").strip()
        if not text:
            return True
        low = text.lower()
        weak_keys = [
            "暂无",
            "未找到",
            "未收录",
            "不够",
            "请先加载",
            "数据源尚未加载",
            "no result",
            "not found",
        ]
        if any(k in low for k in weak_keys):
            return True
        return len(text) < 12

    def _extract_exoplanet_tokens(self, text: str) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for pattern in EXOPLANET_PATTERNS:
            for match in re.finditer(pattern, text or "", flags=re.IGNORECASE):
                token = " ".join(str(match.group(0)).split())
                if not token:
                    continue
                low = token.lower()
                if low in seen:
                    continue
                seen.add(low)
                out.append(token)
        return out

    def _is_exoplanet_name(self, value: str) -> bool:
        text = str(value or "")
        if not text:
            return False
        return any(re.search(p, text, flags=re.IGNORECASE) for p in EXOPLANET_PATTERNS)

    def _dynamic_citations(self, payload: dict[str, Any] | None) -> list[str]:
        if payload is None:
            return []
        provider = str(payload.get("provider") or "dynamic")
        name = str(payload.get("name") or payload.get("requested_name") or "")
        if name:
            return [f"dynamic:{provider}:{name}"]
        return [f"dynamic:{provider}"]

    def _image_citations(self, payload: dict[str, Any] | None) -> list[str]:
        if not isinstance(payload, dict):
            return []
        items = payload.get("items")
        if not isinstance(items, list):
            return []
        out: list[str] = []
        for item in items[:3]:
            url = str(item.get("image_url", "")).strip()
            if url:
                out.append(f"image:{url}")
        return out

    def _web_citations(self, payload: dict[str, Any] | None) -> list[str]:
        if not isinstance(payload, dict):
            return []
        url = str(payload.get("url", "")).strip()
        provider = str(payload.get("provider", "web")).strip()
        title = str(payload.get("title", "")).strip()
        if url:
            return [f"web:{provider}:{url}"]
        if title:
            return [f"web:{provider}:{title}"]
        return [f"web:{provider}"]

    def _build_contextual_question(self, question: str, history: list[str]) -> str:
        if not history:
            return question
        q = str(question or "").strip()
        if not q:
            return q
        if any(k in q.lower() for k in ["它", "这个", "那个", "it", "that", "this"]):
            recent = " ".join(history[-2:])
            return f"{recent} 当前问题: {q}"
        return q

    def _remember_turn(self, session_id: str, question: str, answer: str) -> None:
        turns = self._session_ctx.setdefault(session_id, [])
        turns.append(f"Q: {question}")
        turns.append(f"A: {answer[:240]}")
        if len(turns) > 14:
            self._session_ctx[session_id] = turns[-14:]
        self._persist_history(session_id, self._session_ctx[session_id])

    @staticmethod
    def _dedupe(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            s = str(item).strip()
            if not s or s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out

    def _cache_enabled(self) -> bool:
        return int(getattr(settings, "qa_cache_ttl_seconds", 0) or 0) > 0 and int(
            getattr(settings, "qa_cache_max_entries", 0) or 0
        ) > 0

    def _should_use_cache(self, question: str) -> bool:
        if not self._cache_enabled():
            return False
        q = str(question or "").strip().lower()
        if len(q) < 4:
            return False
        # 对“挑战/最难/难点”类问题禁用缓存，避免把泛化旧答案误用到新语境。
        challenge_keys = [
            "最难",
            "难点",
            "挑战",
            "困难",
            "难在哪",
            "难在哪里",
            "mission challenge",
            "hardest",
            "difficulty",
        ]
        if any(k in q for k in challenge_keys):
            return False
        freshness_keys = [
            "最新",
            "最近",
            "实时",
            "今天",
            "本周",
            "本月",
            "news",
            "latest",
            "recent",
            "today",
            "current",
        ]
        return not any(k in q for k in freshness_keys)

    def _make_cache_key(self, question: str) -> str:
        normalized = " ".join(str(question or "").strip().lower().split())
        return hashlib.sha1(normalized.encode("utf-8")).hexdigest()

    def _prune_cache(self) -> None:
        if not self._answer_cache:
            return
        ttl = max(0, int(getattr(settings, "qa_cache_ttl_seconds", 0) or 0))
        now_ts = time.time()
        expired_keys = [
            key
            for key, payload in self._answer_cache.items()
            if now_ts - float(payload.get("created_at", now_ts)) > ttl
        ]
        for key in expired_keys:
            self._answer_cache.pop(key, None)
        max_entries = max(0, int(getattr(settings, "qa_cache_max_entries", 0) or 0))
        while len(self._answer_cache) > max_entries:
            self._answer_cache.popitem(last=False)
            self._cache_evictions += 1

    def _get_cached_answer(self, cache_key: str, question: str) -> dict[str, Any] | None:
        if not self._should_use_cache(question):
            return None
        lookup_started = time.perf_counter()
        self._prune_cache()
        payload = self._answer_cache.get(cache_key)
        if payload is None:
            self._cache_misses += 1
            return None
        self._answer_cache.move_to_end(cache_key)
        self._cache_hits += 1
        now_ts = time.time()
        return {
            "answer": str(payload.get("answer", "")).strip(),
            "citations": list(payload.get("citations", [])),
            "graph_path": list(payload.get("graph_path", [])),
            "trace": dict(payload.get("trace", {})),
            "age_seconds": round(max(0.0, now_ts - float(payload.get("created_at", now_ts))), 3),
            "lookup_ms": (time.perf_counter() - lookup_started) * 1000,
        }

    def _put_cached_answer(self, cache_key: str, payload: dict[str, Any]) -> None:
        if not self._cache_enabled():
            return
        self._answer_cache[cache_key] = {
            "answer": str(payload.get("answer", "")).strip(),
            "citations": list(payload.get("citations", [])),
            "graph_path": list(payload.get("graph_path", [])),
            "trace": dict(payload.get("trace", {})),
            "created_at": time.time(),
        }
        self._answer_cache.move_to_end(cache_key)
        self._prune_cache()

    def get_cache_stats(self) -> dict[str, Any]:
        self._prune_cache()
        return {
            "enabled": self._cache_enabled(),
            "ttl_seconds": max(0, int(getattr(settings, "qa_cache_ttl_seconds", 0) or 0)),
            "max_entries": max(0, int(getattr(settings, "qa_cache_max_entries", 0) or 0)),
            "size": len(self._answer_cache),
            "hits": int(self._cache_hits),
            "misses": int(self._cache_misses),
            "evictions": int(self._cache_evictions),
        }

    def clear_cache(self) -> int:
        removed = len(self._answer_cache)
        self._answer_cache.clear()
        return removed

    def _new_session_id(self) -> str:
        import uuid

        return uuid.uuid4().hex[:12]

    @staticmethod
    def _looks_corrupted_answer(answer: str) -> bool:
        text = str(answer or "").strip()
        if not text:
            return True
        q_count = text.count("?")
        if q_count >= 8 and q_count >= int(len(text) * 0.15):
            return True
        if re.search(r"[A-Za-z\u4e00-\u9fff]", text) is None:
            return True
        compact = re.sub(r"\s+", "", text)
        if len(compact) >= 30 and len(set(compact)) <= 4:
            return True
        return False

    def _connect(self) -> sqlite3.Connection:
        return get_sqlite_connection(self._db_path)

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS qa_sessions (
                    session_id TEXT PRIMARY KEY,
                    history_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def _load_history(self, session_id: str) -> list[str]:
        if session_id in self._session_ctx:
            return list(self._session_ctx[session_id])
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT history_json FROM qa_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            self._session_ctx[session_id] = []
            return []

        try:
            history = json.loads(str(row["history_json"]))
        except Exception:
            history = []
        if not isinstance(history, list):
            history = []
        history = [str(x) for x in history][-14:]
        self._session_ctx[session_id] = history
        return list(history)

    def _persist_history(self, session_id: str, history: list[str]) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO qa_sessions (session_id, history_json, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(session_id) DO UPDATE SET
                    history_json = excluded.history_json,
                    updated_at = datetime('now')
                """,
                (session_id, json.dumps(history, ensure_ascii=False)),
            )
            conn.commit()
        finally:
            conn.close()
