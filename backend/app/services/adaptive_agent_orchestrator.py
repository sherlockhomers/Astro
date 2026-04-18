from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app.config import settings
from app.services.agent_service import AgentService
from app.services.dynamic_data_service import DynamicDataService
from app.services.graph_service import GraphService
from app.services.mcp_tool_service import MCPToolService
from app.services.model_service import ModelService
from app.services.retrieval_service import RetrievalService
from app.services.sqlite_service import get_sqlite_connection
from app.services.fact_rules_loader import FactRulesLoader
from app.services.web_search_service import WebSearchService

try:
    from app.services.cloud_llm_service import CloudLLMService
except ImportError:
    CloudLLMService = None

EXOPLANET_PATTERNS = (
    r"\b(?:TOI|HD|K2|Kepler|WASP|TRAPPIST|LHS|GJ|Gliese|CoRoT|HIP|KIC)[-\s]?\d+[A-Za-z]?(?:\s*[bcdefg])?\b",
    r"\b[A-Za-z]{2,8}[-\s]?\d{2,7}\s?[bcdefg]\b",
)

# 领域事实规则放 backend/data/domain_fact_rules.default.jsonl，通过 FactRulesLoader 读
# （要改规则直接改文件，然后调 reload_fact_rules 就行，不用重启）


class AdaptiveAgentOrchestrator:
    """
    Adaptive QA orchestration:
    1) intent/entity analysis
    2) strategy routing (LLM optional)
    3) adaptive retrieval with multi-round control
    4) answer generation + reflection retry
    5) memory summary + reflection log
    """

    def __init__(
        self,
        agent_service: AgentService,
        retrieval_service: RetrievalService,
        graph_service: GraphService,
        model_service: ModelService,
        dynamic_service: DynamicDataService | None = None,
        web_service: WebSearchService | None = None,
        mcp_service: MCPToolService | None = None,
    ) -> None:
        self._agent = agent_service
        self._retrieval = retrieval_service
        self._graph = graph_service
        self._model = model_service
        self._dynamic = dynamic_service
        self._web = web_service
        self._mcp = mcp_service
        self._cloud_llm: Any = None
        if CloudLLMService is not None:
            try:
                self._cloud_llm = CloudLLMService()
            except Exception:
                self._cloud_llm = None
        self._db_path = settings.sqlite_path
        self._init_db()
        self._fact_rules = FactRulesLoader(
            paths=[
                str(getattr(settings, "domain_fact_rules_default_path", "") or "").strip(),
                str(getattr(settings, "local_fact_rules_path", "") or "").strip(),
            ]
        )

    def reload_fact_rules(self) -> dict[str, Any]:
        bundle = self._fact_rules.reload()
        return {"count": len(bundle.rules), "sources": list(bundle.sources)}

    def run(
        self,
        question: str,
        session_id: str,
        history: list[str] | None = None,
        emit_stage: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        emit = emit_stage or (lambda _stage, _payload=None: None)
        turns = list(history or [])
        analysis = self._agent.analyze(question, turns)
        analysis = self._normalize_analysis(question, analysis)
        emit(
            "analysis",
            {
                "message": self._stage_message("analysis", entities=analysis.get("entities", [])),
                "intent": analysis.get("intent", "general"),
                "entities": list(analysis.get("entities", []))[:3],
            },
        )
        memory = self._load_memory(session_id)

        strategy = self._decide_strategy(
            question=question,
            analysis=analysis,
            memory_summary=memory.get("summary", ""),
        )
        emit(
            "strategy",
            {
                "message": self._stage_message("strategy", strategy=strategy),
                "sources": list(strategy.get("sources", [])),
                "complexity": str(strategy.get("complexity", "medium")),
            },
        )

        retrieval_bundle = {
            "rounds": 0,
            "rag_items": [],
            "citations": [],
            "graph_path": [],
        }
        answer_text = ""
        answer_citations: list[str] = []

        direct_answer = self._match_domain_fact_guard(question)
        if direct_answer and str(strategy.get("complexity", "")) in ("simple", "medium") and not strategy.get("need_retrieval", False):
            answer_text = self._polish_user_answer(
                direct_answer,
                question,
                "zh" if self._contains_cjk(question) else "en",
            )
            emit(
                "retrieval",
                {
                    "message": "\u8fd9\u4e2a\u95ee\u9898\u53ef\u4ee5\u76f4\u63a5\u56de\u7b54\uff0c\u4e0d\u518d\u989d\u5916\u68c0\u7d22\u3002",
                    "round": 0,
                    "items": 0,
                    "sources": ["model"],
                },
            )
            emit(
                "preview",
                {
                    "message": "\u5148\u7ed9\u4f60\u4e00\u4e2a\u5feb\u901f\u7ed3\u8bba\u3002",
                    "delta": answer_text,
                },
            )
        else:
            if any(
                bool(strategy.get(key, False))
                for key in ["need_retrieval", "need_graph", "need_dynamic", "need_web", "need_mcp"]
            ):
                retrieval_bundle = self._retrieve_round(
                    query=question,
                    analysis=analysis,
                    strategy=strategy,
                    round_id=1,
                )
                emit(
                    "retrieval",
                    {
                        "message": self._stage_message("retrieval", retrieval_bundle=retrieval_bundle, round_id=1),
                        "round": 1,
                        "items": len(retrieval_bundle.get("rag_items", [])),
                        "sources": list(strategy.get("sources", [])),
                    },
                )

                preview_text = self._build_preview_answer(question, analysis, strategy, retrieval_bundle)
                if preview_text:
                    emit(
                        "preview",
                        {
                            "message": "\u5148\u7ed9\u4f60\u4e00\u4e2a\u5feb\u901f\u7ed3\u8bba\u3002",
                            "delta": preview_text,
                        },
                    )

                if (
                    strategy.get("need_retrieval", False)
                    and strategy.get("multi_round", False)
                    and not self._is_context_sufficient(question, analysis, retrieval_bundle, strategy)
                ):
                    expanded = self._build_expanded_query(question, analysis, retrieval_bundle)
                    if expanded and expanded != question:
                        emit(
                            "retrieval",
                            {
                                "message": "\u5148\u7ed9\u4f60\u4e00\u4e2a\u5feb\u901f\u7ed3\u8bba\u3002",
                                "round": 2,
                                "query": expanded,
                            },
                        )
                        round_two = self._retrieve_round(
                            query=expanded,
                            analysis=analysis,
                            strategy=strategy,
                            round_id=2,
                        )
                        retrieval_bundle = self._merge_retrieval(retrieval_bundle, round_two)
                        emit(
                            "retrieval",
                            {
                                "message": self._stage_message("retrieval", retrieval_bundle=retrieval_bundle, round_id=2),
                                "round": 2,
                                "items": len(retrieval_bundle.get("rag_items", [])),
                                "sources": list(strategy.get("sources", [])),
                            },
                        )
            else:
                emit(
                    "retrieval",
                    {
                        "message": "\u5148\u7ed9\u4f60\u4e00\u4e2a\u5feb\u901f\u7ed3\u8bba\u3002",
                        "round": 0,
                        "items": 0,
                        "sources": ["model"],
                    },
                )

            emit("compose", {"message": self._stage_message("compose")})
            answer_text, answer_citations = self._generate_answer(
                question=question,
                analysis=analysis,
                strategy=strategy,
                retrieval_bundle=retrieval_bundle,
                memory_summary=memory.get("summary", ""),
                turns=turns,
            )
            answer_text = self._apply_domain_fact_guards(question, answer_text)
            answer_text = self._validate_answer_relevance(question, analysis, answer_text)

        answer_text = self._cloud_enhance_if_needed(question, answer_text, retrieval_bundle, emit)

        reflection = self._reflect_answer(question, analysis, answer_text, retrieval_bundle, answer_citations)
        emit(
            "reflection",
            {
                "message": self._stage_message("reflection", reflection=reflection),
                "issues": list(reflection.get("issues", [])),
            },
        )
        if (
            bool(getattr(settings, "agent_enable_reflection", True))
            and reflection.get("needs_retry", False)
            and self._model.ready
        ):
            retry_text, retry_citations = self._retry_with_reflection(
                question=question,
                analysis=analysis,
                strategy=strategy,
                retrieval_bundle=retrieval_bundle,
                memory_summary=memory.get("summary", ""),
                turns=turns,
                reflection=reflection,
                previous_answer=answer_text,
            )
            if retry_text:
                answer_text = retry_text
                answer_citations = retry_citations
                reflection = self._reflect_answer(
                    question=question,
                    analysis=analysis,
                    answer=answer_text,
                    retrieval_bundle=retrieval_bundle,
                    citations=answer_citations,
                )

        final_citations = self._dedupe(answer_citations + retrieval_bundle.get("citations", []))
        graph_path = retrieval_bundle.get("graph_path", [])

        self._update_memory(session_id, question, answer_text, analysis, reflection)
        self._save_reflection(session_id, question, answer_text, reflection)

        return {
            "answer": answer_text,
            "citations": final_citations,
            "graph_path": graph_path,
            "mode": "adaptive_rag_agent",
            "trace": {
                "intent": analysis.get("intent", "general"),
                "strategy": strategy,
                "memory_used": bool(memory.get("summary")),
                "retrieval_rounds": retrieval_bundle.get("rounds", 1),
                "evidence_summary": self._summarize_evidence(retrieval_bundle),
                "reflection": reflection,
            },
        }

    def _match_domain_fact_guard(self, question: str) -> str:
        return self._fact_rules.match(question)

    def _cloud_enhance_if_needed(
        self,
        question: str,
        answer: str,
        retrieval_bundle: dict[str, Any],
        emit: Any,
    ) -> str:
        """Use cloud LLM to enhance or replace the answer when local quality is low."""
        if not self._cloud_llm or not self._cloud_llm.enabled:
            return answer

        text = str(answer or "").strip()
        should_enhance = False

        if not text or len(text) < 20:
            should_enhance = True
        elif text.count("?") >= 5 or text.count("？") >= 3:
            should_enhance = True
        elif "知识库中暂" in text or "暂未找到" in text or "没有足够信息" in text:
            should_enhance = True
        elif len(text) < 80 and not any(c in text for c in "。！？"):
            should_enhance = True

        if not should_enhance:
            return answer

        emit("cloud_enhance", {"message": "正在通过云端模型增强回答质量。"})

        snippets = []
        for item in (retrieval_bundle.get("rag_items") or [])[:4]:
            if isinstance(item, dict):
                snippet = str(item.get("snippet", "")).strip()
                if snippet:
                    snippets.append(snippet[:200])

        result = self._cloud_llm.enhance_answer(
            question=question,
            local_answer=text if len(text) > 15 else "",
            context_snippets=snippets if snippets else None,
        )

        if result.get("ok") and result.get("answer"):
            return str(result["answer"]).strip()
        return answer

    def _validate_answer_relevance(self, question: str, analysis: dict[str, Any], answer: str) -> str:
        """Check that the answer addresses the question's core entities and specific aspect."""
        q = str(question or "").strip()
        text = str(answer or "").strip()
        if not q or not text or len(text) < 10:
            return text

        entities = [str(e).strip() for e in analysis.get("entities", []) if str(e).strip()]

        corrupted_markers = ["???", "###", "问号", "乱码"]
        if any(marker in text for marker in corrupted_markers) and len(text) < 50:
            guarded = self._match_domain_fact_guard(question)
            if guarded:
                return guarded

        text_lower = text.lower()
        if entities:
            primary_entity = entities[0]
            if primary_entity.lower() not in text_lower:
                found = False
                for e in entities:
                    if e.lower() in text_lower:
                        primary_entity = e
                        found = True
                        break
                if not found:
                    guarded = self._match_domain_fact_guard(question)
                    if guarded:
                        return guarded
                    return f"关于{primary_entity}：{text}"

        aspect_keywords = self._extract_question_aspect(q)
        if aspect_keywords and not any(kw in text_lower for kw in aspect_keywords):
            guarded = self._match_domain_fact_guard(question)
            if guarded:
                return guarded

        return text

    @staticmethod
    def _extract_question_aspect(question: str) -> list[str]:
        """Extract the specific aspect the question is asking about."""
        q = question.lower()
        aspect_map = {
            "结构": ["结构", "内部", "核心", "地壳", "地幔", "构造", "层"],
            "温度": ["温度", "多热", "多冷", "摄氏", "度"],
            "大气": ["大气", "气体", "空气", "大气层", "大气压"],
            "距离": ["距离", "多远", "公里", "光年", "au"],
            "质量": ["质量", "多重", "多大", "千克", "吨"],
            "轨道": ["轨道", "公转", "周期", "自转"],
            "卫星": ["卫星", "月亮", "伴星"],
            "探测": ["探测", "任务", "着陆", "探测器", "飞船"],
            "表面": ["表面", "地表", "地形", "山", "平原", "峡谷"],
            "磁场": ["磁场", "磁层"],
            "形成": ["形成", "起源", "诞生"],
            "发现": ["发现", "观测", "历史"],
        }
        for aspect, keywords in aspect_map.items():
            if any(kw in q for kw in keywords):
                return keywords
        return []

    def _apply_domain_fact_guards(self, question: str, answer: str) -> str:
        text = str(answer or "").strip()
        if not text:
            return text
        guarded = self._fact_rules.match(question)
        return guarded or text

    def _decide_strategy(
        self,
        question: str,
        analysis: dict[str, Any],
        memory_summary: str,
    ) -> dict[str, Any]:
        heuristic = self._heuristic_strategy(question, analysis)
        if bool(getattr(settings, "agent_enable_llm_planner", False)):
            llm_plan = self._llm_strategy(question, analysis, memory_summary, heuristic)
            return self._merge_strategy(heuristic, llm_plan)
        return heuristic

    def _normalize_analysis(self, question: str, analysis: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(analysis or {})
        q = str(question or "").strip()
        q_low = q.lower()

        canonical_entities = [
            "\u592a\u9633", "\u6708\u7403", "\u5730\u7403", "\u706b\u661f", "\u6728\u661f",
            "\u571f\u661f", "\u91d1\u661f", "\u6c34\u661f", "\u5929\u738b\u661f", "\u6d77\u738b\u661f", "\u51a5\u738b\u661f",
            "\u94f6\u6cb3\u7cfb", "\u9ed1\u6d1e", "\u4e2d\u5b50\u661f", "\u8d85\u65b0\u661f", "\u5f57\u661f",
            "\u5c0f\u884c\u661f", "\u7cfb\u5916\u884c\u661f", "\u884c\u661f", "\u6052\u661f",
            "sun", "moon", "earth", "mars", "jupiter", "saturn", "venus", "mercury", "uranus", "neptune", "pluto",
            "milky way", "black hole", "neutron star", "supernova", "comet", "asteroid", "exoplanet",
        ]

        selected: list[str] = []
        selected_lc: set[str] = set()
        for name in canonical_entities:
            if self._contains_cjk(name):
                if name in q and name not in selected:
                    selected.append(name)
                    selected_lc.add(name.lower())
            else:
                low = name.lower()
                if low in q_low and low not in selected_lc:
                    selected.append(name)
                    selected_lc.add(low)

        existing = [str(x).strip() for x in normalized.get("entities", []) if str(x).strip()]
        kept_existing = [x for x in existing if (x in q or x.lower() in q_low)]

        exo_tokens: list[str] = []
        for pattern in EXOPLANET_PATTERNS:
            for match in re.finditer(pattern, q, flags=re.IGNORECASE):
                token = " ".join(str(match.group(0)).split())
                if token and token not in exo_tokens:
                    exo_tokens.append(token)

        final_entities: list[str] = []
        for name in selected + exo_tokens + kept_existing:
            if name and name not in final_entities:
                final_entities.append(name)

        if "\u536b\u661f\u7cfb\u7edf" in q or "\u536b\u661f\u7cfb" in q:
            final_entities = [x for x in final_entities if x not in {"\u661f\u7cfb", "galaxy"}]

        normalized["entities"] = final_entities[:6]
        return normalized

    def _heuristic_strategy(self, question: str, analysis: dict[str, Any]) -> dict[str, Any]:
        q = str(question or "").strip()
        q_low = q.lower()
        intent = str(analysis.get("intent", "general"))
        entities = [str(x).strip() for x in analysis.get("entities", []) if str(x).strip()]

        latest_keys_zh = ["最新", "最近", "今天", "近期", "实时", "新闻", "新发现", "刚刚"]
        latest_keys_en = ["latest", "recent", "today", "this week", "this month", "real-time", "news", "new discovery"]
        has_latest = any(k in q for k in latest_keys_zh) or any(k in q_low for k in latest_keys_en)

        need_graph = intent in {"relation", "comparison"} and len(entities) >= 2
        need_dynamic = self._is_dynamic_query(q, entities)
        explicit_rag_keys = ["知识库", "图谱", "文献", "资料", "RAG", "rag", "检索", "引用"]
        explicit_rag = any(k in q for k in explicit_rag_keys)
        direct_guard = self._match_domain_fact_guard(q)

        complexity = self._classify_complexity(
            question=q,
            intent=intent,
            entities=entities,
            has_latest=has_latest,
            need_graph=need_graph,
            need_dynamic=need_dynamic,
            explicit_rag=explicit_rag,
        )

        need_retrieval = complexity in {"medium", "complex"} or need_graph or need_dynamic or has_latest or explicit_rag
        if direct_guard:
            complexity = "simple"
            need_retrieval = False
            need_graph = False
            need_dynamic = False


        sources: list[str] = []
        if need_retrieval:
            sources.append("kb")
        if need_graph:
            sources.append("kg")
        if need_dynamic:
            sources.append("dynamic")
        if has_latest:
            sources.extend(["mcp", "web"])
        if not sources:
            sources = ["model"]

        top_k_map = {
            "simple": int(getattr(settings, "agent_simple_top_k", 3)),
            "medium": int(getattr(settings, "agent_medium_top_k", 5)),
            "complex": int(getattr(settings, "agent_complex_top_k", 7)),
        }

        return {
            "need_retrieval": need_retrieval,
            "need_graph": need_graph,
            "need_dynamic": need_dynamic,
            "need_web": has_latest,
            "need_mcp": has_latest and bool(getattr(settings, "mcp_tools_enabled", False)),
            "multi_round": complexity == "complex",
            "top_k": max(2, min(10, top_k_map.get(complexity, 5))),
            "sources": list(dict.fromkeys(sources)),
            "reason": "heuristic",
            "complexity": complexity,
            "direct_guard": bool(direct_guard),
        }

    def _classify_complexity(
        self,
        question: str,
        intent: str,
        entities: list[str],
        has_latest: bool,
        need_graph: bool,
        need_dynamic: bool,
        explicit_rag: bool,
    ) -> str:
        q = str(question or "").strip()
        if not q:
            return "simple"

        token_count = len(self._question_keywords(q))
        complex_markers = ["对比", "区别", "联系", "演化", "机制", "为什么", "如何判断", "多轮", "综合", "结合", "最新"]
        explain_markers = ["为什么", "如何", "原理", "机制", "怎么", "形成", "影响", "是否"]
        metric_markers = ["多少", "距离", "质量", "半径", "温度", "年龄", "速度", "周期", "大小", "密度", "数量"]

        if has_latest or need_graph or need_dynamic or explicit_rag:
            return "complex"
        if intent in {"comparison", "relation"} or len(entities) >= 2:
            return "complex"
        if len(q) >= 34 or token_count >= 6:
            return "complex"
        if any(marker in q for marker in complex_markers) and any(marker in q for marker in explain_markers + metric_markers):
            return "complex"
        if any(marker in q for marker in explain_markers + metric_markers):
            return "medium"
        if len(entities) == 1 and len(q) >= 8:
            return "medium"
        return "simple"

    def _build_preview_answer(
        self,
        question: str,
        analysis: dict[str, Any],
        strategy: dict[str, Any],
        retrieval_bundle: dict[str, Any],
    ) -> str:
        direct = self._match_domain_fact_guard(question)
        if direct:
            return self._truncate_preview(direct)
        structured_preview = self._build_structured_preview(question, analysis, strategy)
        if structured_preview:
            return structured_preview
        rag_text, _ = self._compose_answer_from_rag(
            question,
            analysis,
            retrieval_bundle,
            "zh" if self._contains_cjk(question) else "en",
        )
        if rag_text:
            return self._truncate_preview(rag_text)
        return ""

    def _build_structured_preview(
        self,
        question: str,
        analysis: dict[str, Any],
        strategy: dict[str, Any],
    ) -> str:
        entities = [str(x).strip() for x in analysis.get("entities", []) if str(x).strip()]
        intent = str(analysis.get("intent", "general"))
        complexity = str(strategy.get("complexity", "medium"))
        is_zh = self._contains_cjk(question)

        if intent == "comparison" and len(entities) >= 2:
            a, b = entities[:2]
            if is_zh:
                return f"我会先比较{a}和{b}的核心差异，再补充与你问题相关的关键背景。"
            return f"I will first compare the core differences between {a} and {b}, then add the key context tied to your question."

        if complexity == "complex" and entities:
            focus = "、".join(entities[:2])
            if is_zh:
                return f"我先围绕{focus}整理知识线索，再给你一版结构更清晰的回答。"
            return f"I will organize the evidence around {focus} first, then give you a structured answer."

        if complexity == "medium" and entities:
            focus = entities[0]
            if is_zh:
                return f"我先抓住{focus}这个重点，再用一段更自然的方式解释给你。"
            return f"I will focus on {focus} first, then explain it in a more natural way."

        return ""

    def _truncate_preview(self, text: str, max_chars: int = 120) -> str:
        raw = self._clean_answer(text)
        if not raw:
            return ""
        raw = raw.split("\n\n", 1)[0].strip()
        if len(raw) <= max_chars:
            return raw
        return raw[: max_chars - 1].rstrip() + "?"

    def _llm_strategy(
        self,
        question: str,
        analysis: dict[str, Any],
        memory_summary: str,
        base_strategy: dict[str, Any],
    ) -> dict[str, Any]:
        if not self._model.ready:
            return {}
        planner_prompt = (
            "You are an astronomy query planner.\n"
            "Return STRICT JSON only. No markdown.\n"
            "Fields: need_retrieval(bool), need_graph(bool), need_dynamic(bool), need_web(bool), need_mcp(bool), "
            "multi_round(bool), top_k(int 3-12), sources(array of strings), reason(string).\n\n"
            f"Question: {question}\n"
            f"Intent: {analysis.get('intent', 'general')}\n"
            f"Entities: {analysis.get('entities', [])}\n"
            f"SessionSummary: {memory_summary[:240]}\n"
            f"BaseStrategy: {base_strategy}\n"
            "JSON:"
        )
        ok, payload = self._model.answer(planner_prompt, {"analysis": {"intent": "planner"}, "rag_items": []})
        if not ok:
            return {}
        text, _ = self._extract_answer_payload(payload)
        return self._parse_json_like(text)

    def _merge_strategy(self, heuristic: dict[str, Any], llm_plan: dict[str, Any]) -> dict[str, Any]:
        merged = dict(heuristic)
        for key in ["need_retrieval", "need_graph", "need_dynamic", "need_web", "need_mcp", "multi_round"]:
            if isinstance(llm_plan.get(key), bool):
                merged[key] = bool(llm_plan[key])
        if isinstance(llm_plan.get("top_k"), int):
            merged["top_k"] = max(3, min(12, int(llm_plan["top_k"])))
        if isinstance(llm_plan.get("sources"), list):
            clean = [str(x).strip().lower() for x in llm_plan["sources"] if str(x).strip()]
            if clean:
                merged["sources"] = list(dict.fromkeys(clean))
        reason = str(llm_plan.get("reason", "")).strip()
        if reason:
            merged["reason"] = reason
        return merged

    def _retrieve_round(
        self,
        query: str,
        analysis: dict[str, Any],
        strategy: dict[str, Any],
        round_id: int,
    ) -> dict[str, Any]:
        rag_items: list[dict[str, Any]] = []
        citations: list[str] = []
        graph_path: list[dict[str, Any]] = []

        top_k = int(strategy.get("top_k", 5))
        sources = set([str(x).lower() for x in strategy.get("sources", [])])

        if "kb" in sources and strategy.get("need_retrieval", False):
            kb_items = self._retrieve_kb(query, analysis, top_k)
            entities = [str(x).strip() for x in analysis.get("entities", []) if str(x).strip()]
            if entities:
                entity_seed: list[dict[str, Any]] = []
                for ent in entities[:2]:
                    entity_seed.extend(self._retrieve_kb(ent, {"entities": [ent]}, max(2, top_k // 2)))
                kb_items = self._dedupe_rag_items(entity_seed + kb_items)
            for item in kb_items:
                rag_items.append(item)
            if kb_items:
                citations.append("kb:local_hybrid_retrieval")

        # Always enrich with direct entity entries when available.
        for entity_item in self._retrieve_entity_items(analysis):
            rag_items.append(entity_item)
            title = str(entity_item.get("title", "")).strip()
            if title:
                citations.append(f"entity:{title}")

        if "kg" in sources and strategy.get("need_graph", False):
            names = [str(x).strip() for x in analysis.get("entities", []) if str(x).strip()]
            if len(names) >= 2:
                graph_path = self._graph.find_path(names[0], names[1], max_hops=4)
            if graph_path:
                path_text = " | ".join(
                    [f"{str(p.get('from', ''))}-{str(p.get('rel', ''))}->{str(p.get('to', ''))}" for p in graph_path[:8]]
                )
                rag_items.append(
                    {
                        "title": "knowledge_graph_path",
                        "source": "kg",
                        "snippet": path_text,
                        "score": 1.0,
                    }
                )
                citations.append(f"kg:path_hops={len(graph_path)}")

        if "dynamic" in sources and strategy.get("need_dynamic", False) and self._dynamic is not None:
            target = self._pick_dynamic_target(query, analysis)
            if target:
                dyn = self._dynamic.query_exoplanet(target)
                if isinstance(dyn, dict):
                    rag_items.append(
                        {
                            "title": str(dyn.get("name", target)),
                            "source": "dynamic",
                            "snippet": json.dumps(dyn, ensure_ascii=False),
                            "score": 1.0,
                        }
                    )
                    citations.append(f"dynamic:{target}")

        if "mcp" in sources and strategy.get("need_mcp", False) and self._mcp is not None and self._mcp.enabled:
            mcp_query = self._build_lookup_query(query, analysis)
            mcp_data = self._mcp.query_latest_astronomy(mcp_query)
            if isinstance(mcp_data, dict):
                summary = str(mcp_data.get("summary", "")).strip()
                if summary:
                    rag_items.append(
                        {
                            "title": "latest_astronomy",
                            "source": "mcp",
                            "snippet": summary,
                            "score": 0.98,
                        }
                    )
                citations.extend([str(x) for x in mcp_data.get("citations", []) if str(x).strip()])

        if "web" in sources and strategy.get("need_web", False) and self._web is not None and self._web.enabled:
            web_query = self._build_lookup_query(query, analysis)
            web = self._web.search(web_query)
            if isinstance(web, dict):
                summary = str(web.get("summary", "")).strip()
                if summary:
                    rag_items.append(
                        {
                            "title": str(web.get("title", "")).strip() or "web_result",
                            "source": str(web.get("provider", "web")).strip(),
                            "snippet": summary,
                            "score": 0.9,
                        }
                    )
                if web.get("url"):
                    citations.append(f"web:{web.get('url')}")

        return {
            "rounds": round_id,
            "rag_items": self._dedupe_rag_items(rag_items)[:20],
            "citations": self._dedupe(citations),
            "graph_path": graph_path,
        }

    def _retrieve_entity_items(self, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        names = [str(x).strip() for x in analysis.get("entities", []) if str(x).strip()]
        for name in names[:4]:
            entity = self._agent.find_entity_by_name(name)
            if not entity:
                continue
            desc = str(entity.get("description", "")).strip()
            if not desc:
                raw = entity.get("raw", {})
                try:
                    desc = json.dumps(raw, ensure_ascii=False)[:900]
                except Exception:
                    desc = ""
            if not desc:
                continue
            out.append(
                {
                    "title": str(entity.get("name", name)),
                    "source": str(entity.get("source_file", "entity")).strip() or "entity",
                    "snippet": desc,
                    "score": 1.15,
                }
            )
        return out

    def _retrieve_kb(self, query: str, analysis: dict[str, Any], top_k: int) -> list[dict[str, Any]]:
        try:
            items, _ = self._retrieval.search(query, top_k=max(8, top_k * 3))
        except Exception:
            return []

        tokens = self._question_keywords(query)
        entities = [str(x).strip().lower() for x in analysis.get("entities", []) if str(x).strip()]
        min_score = float(getattr(settings, "agent_kb_min_score", 0.45))

        ranked: list[tuple[float, dict[str, Any]]] = []
        for item in items:
            title = str(item.get("title", "")).strip()
            source = str(item.get("source", "")).strip() or "kb"
            snippet = str(item.get("snippet", "")).strip()
            if source.lower() == "mock":
                continue
            if not snippet and not title:
                continue

            hay = f"{title} {snippet}".lower()
            overlap = sum(1 for t in tokens if t in hay)
            entity_hit = any(ent in hay for ent in entities if ent)
            base_score = self._as_float(item.get("score"), 0.0)

            if overlap == 0 and not entity_hit:
                continue
            if base_score < min_score and overlap < 2 and not entity_hit:
                continue

            mix = base_score + overlap * 0.18 + (0.25 if entity_hit else 0.0)
            ranked.append(
                (
                    mix,
                    {
                        "title": title,
                        "source": source,
                        "snippet": snippet[:900],
                        "score": round(mix, 4),
                    },
                )
            )

        ranked.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in ranked[:top_k]]

    def _is_context_sufficient(
        self,
        question: str,
        analysis: dict[str, Any],
        retrieval_bundle: dict[str, Any],
        strategy: dict[str, Any],
    ) -> bool:
        if not strategy.get("need_retrieval", False):
            return True
        rag_items = list(retrieval_bundle.get("rag_items", []))
        if not rag_items:
            return False

        complexity = str(strategy.get("complexity", "medium"))
        joined = " ".join([str(x.get("title", "")) + " " + str(x.get("snippet", "")) for x in rag_items]).lower()
        tokens = self._question_keywords(question)
        token_hit = sum(1 for t in tokens if t in joined)
        entities = [str(x).strip().lower() for x in analysis.get("entities", []) if str(x).strip()]
        entity_hit = sum(1 for e in entities if e in joined)
        high_score = sum(1 for x in rag_items if float(x.get("score", 0.0) or 0.0) >= 0.72)

        if strategy.get("need_web", False) or strategy.get("need_mcp", False):
            if any(str(x.get("source", "")).lower() in {"mcp", "wikipedia_zh", "wikipedia_en", "web"} for x in rag_items):
                return True

        if complexity == "simple":
            return entity_hit >= 1 or high_score >= 1
        if complexity == "medium":
            return token_hit >= 2 or entity_hit >= 1 or high_score >= 2 or len(rag_items) >= 4
        return token_hit >= 3 or entity_hit >= 1 or high_score >= 3 or len(rag_items) >= 5

    def _build_expanded_query(self, question: str, analysis: dict[str, Any], retrieval_bundle: dict[str, Any]) -> str:
        base = str(question or "").strip()
        entities = [str(x).strip() for x in analysis.get("entities", []) if str(x).strip()]
        titles = [str(x.get("title", "")).strip() for x in retrieval_bundle.get("rag_items", [])[:3]]
        extras = [x for x in entities + titles if x and x.lower() not in base.lower()]
        if not extras:
            return base
        return f"{base} {' '.join(extras[:2])}".strip()

    def _merge_retrieval(self, first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
        merged_items = self._dedupe_rag_items(list(first.get("rag_items", [])) + list(second.get("rag_items", [])))
        merged_citations = self._dedupe(list(first.get("citations", [])) + list(second.get("citations", [])))
        graph_path = list(first.get("graph_path", [])) or list(second.get("graph_path", []))
        return {
            "rounds": max(int(first.get("rounds", 1)), int(second.get("rounds", 1))),
            "rag_items": merged_items[:24],
            "citations": merged_citations,
            "graph_path": graph_path,
        }

    def _generate_answer(
        self,
        question: str,
        analysis: dict[str, Any],
        strategy: dict[str, Any],
        retrieval_bundle: dict[str, Any],
        memory_summary: str,
        turns: list[str],
    ) -> tuple[str, list[str]]:
        rag_items = list(retrieval_bundle.get("rag_items", []))
        target_lang = "zh" if self._contains_cjk(question) else "en"
        latest_mode = bool(strategy.get("need_web", False) or strategy.get("need_mcp", False))

        if latest_mode:
            latest_text, latest_cits = self._compose_latest_digest(rag_items, target_lang)
            if latest_text:
                return self._polish_user_answer(latest_text, question, target_lang), latest_cits

        compare_text, compare_cits = self._compose_structured_comparison_answer(question, analysis, target_lang)
        if compare_text:
            return compare_text, compare_cits

        if self._model.ready:
            model_question = self._build_model_question(
                question=question,
                analysis=analysis,
                strategy=strategy,
                memory_summary=memory_summary,
                rag_items=rag_items,
                target_lang=target_lang,
            )
            ok, payload = self._model.answer(
                question=model_question,
                context={
                    "user_question": question,
                    "analysis": analysis,
                    "history": turns[-6:],
                    "rag_items": rag_items[:10],
                    "strategy": strategy,
                    "session_memory": memory_summary[:320],
                    "target_lang": target_lang,
                },
            )
            if ok:
                text, cits = self._extract_answer_payload(payload)
                text = self._polish_user_answer(self._clean_answer(text), question, target_lang)
                if text and self._answer_is_relevant(question, analysis, text, target_lang):
                    return text, cits

        rag_text, rag_cits = self._compose_answer_from_rag(question, analysis, retrieval_bundle, target_lang)
        if rag_text:
            return rag_text, rag_cits

        agent_result = self._agent.answer(question, turns)
        fallback_text = self._polish_user_answer(str(agent_result.get("answer", "")).strip(), question, target_lang)
        fallback_cits = [str(x) for x in agent_result.get("citations", []) if str(x).strip()]
        if fallback_text and self._answer_is_relevant(question, analysis, fallback_text, target_lang):
            return fallback_text, fallback_cits

        if self._web is not None and self._web.enabled:
            web_query = self._build_lookup_query(question, analysis)
            web = self._web.search(web_query)
            if isinstance(web, dict):
                summary = str(web.get("summary", "")).strip()
                title = str(web.get("title", "")).strip()
                if summary:
                    text = f"{title}：{summary}" if title and target_lang == "zh" else (f"{title}: {summary}" if title else summary)
                    text = self._polish_user_answer(text, question, target_lang)
                    if self._answer_is_relevant(question, analysis, text, target_lang):
                        cits = [f"web:{web.get('url')}" ] if web.get("url") else ["web:wikipedia"]
                        return text, cits

        if target_lang == "zh":
            return "当前还没有足够可靠的证据来完整回答这个问题。你可以补充更具体的天体、现象或条件，我再继续展开。", []
        return "I currently do not have enough reliable evidence to answer this question. Please add a concrete object, phenomenon, or condition.", []

    def _compose_structured_comparison_answer(
        self,
        question: str,
        analysis: dict[str, Any],
        target_lang: str,
    ) -> tuple[str, list[str]]:
        if target_lang != "zh":
            return "", []
        if str(analysis.get("intent", "")) != "comparison":
            return "", []

        entities = [str(x).strip() for x in analysis.get("entities", []) if str(x).strip()]
        if len(entities) < 2:
            return "", []

        a, b = entities[:2]
        compare = self._graph.compare_entities(a, b)
        if not isinstance(compare, dict) or not compare.get("ok"):
            return "", []

        metrics = {str(item.get("key", "")): item for item in compare.get("metrics", []) if isinstance(item, dict)}
        mass = metrics.get("mass_earth")
        diameter = metrics.get("diameter_km")
        moons = metrics.get("moon_count")
        temp = metrics.get("surface_temp_c")

        def num(item: dict[str, Any] | None, side: str) -> float | None:
            if not isinstance(item, dict):
                return None
            value = item.get(side)
            return float(value) if isinstance(value, (int, float)) else None

        summary_parts: list[str] = []
        pair = {a, b}
        if pair == {"木星", "土星"}:
            summary_parts.append(
                "如果聚焦内部结构，木星和土星都属于以氢、氦为主的巨行星，但木星质量更大、内部压强更高，土星的平均密度更低。"
            )
        elif pair == {"天王星", "海王星"}:
            summary_parts.append(
                "如果聚焦内部结构，天王星和海王星都常被归入冰巨行星，但海王星通常被认为内部能量更活跃，天王星的自转轴倾角则更极端。"
            )

        if isinstance(num(mass, "a"), float) and isinstance(num(mass, "b"), float):
            mass_a = num(mass, "a")
            mass_b = num(mass, "b")
            if mass_a and mass_b:
                leader = a if mass_a > mass_b else b
                summary_parts.append(f"从体量和引力控制能力看，{leader}更强。")

        if isinstance(num(diameter, "a"), float) and isinstance(num(diameter, "b"), float):
            d_a = num(diameter, "a")
            d_b = num(diameter, "b")
            if d_a and d_b and abs(d_a - d_b) > 1000:
                leader = a if d_a > d_b else b
                summary_parts.append(f"从可见尺寸看，{leader}也更大。")

        if isinstance(num(moons, "a"), float) and isinstance(num(moons, "b"), float):
            moon_a = int(num(moons, "a") or 0)
            moon_b = int(num(moons, "b") or 0)
            if moon_a != moon_b:
                richer = a if moon_a > moon_b else b
                summary_parts.append(f"卫星系统方面，{richer}目前记录到的天然卫星数量更多。")
                if pair == {"木星", "土星"}:
                    summary_parts.append("木星的代表性亮点是伽利略四大卫星，土星则以土卫六和复杂环-卫星相互作用研究更出名。")

        if isinstance(num(temp, "a"), float) and isinstance(num(temp, "b"), float):
            t_a = num(temp, "a")
            t_b = num(temp, "b")
            if t_a is not None and t_b is not None and abs(t_a - t_b) >= 10:
                colder = a if t_a < t_b else b
                summary_parts.append(f"表面或云顶温度上，{colder}通常更低。")

        if not summary_parts:
            summary = str(compare.get("summary", "")).strip()
            if summary:
                summary_parts.append(summary + "。")

        if not summary_parts:
            return "", []

        answer = "\n\n".join(summary_parts)
        return self._polish_user_answer(answer, question, target_lang), [f"compare:{a}:{b}"]

    def _compose_latest_digest(self, rag_items: list[dict[str, Any]], target_lang: str) -> tuple[str, list[str]]:
        latest = []
        for item in rag_items:
            source = str(item.get("source", "")).lower()
            if source in {"mcp", "wikipedia_zh", "wikipedia_en", "web"}:
                latest.append(item)
        if not latest:
            return "", []

        lines: list[str] = []
        citations: list[str] = []
        for idx, item in enumerate(latest[:3], start=1):
            title = str(item.get("title", "")).strip() or f"update-{idx}"
            snippet = str(item.get("snippet", "")).strip()
            source = str(item.get("source", "")).strip() or "external"
            if not snippet:
                continue
            if target_lang == "zh" and not self._contains_cjk(snippet):
                snippet = self._translate_snippet_to_zh(snippet)
            if target_lang == "zh":
                lines.append(f"{idx}. {title}（来源：{source}）：{snippet[:260]}")
            else:
                lines.append(f"{idx}. {title} (source: {source}): {snippet[:260]}")
            citations.append(f"latest:{source}:{title}")

        if not lines:
            return "", []
        if target_lang == "zh":
            text = "最近值得关注的天文动态如下：\n" + "\n".join(lines)
        else:
            text = "Recent astronomy updates:\n" + "\n".join(lines)
        return text, self._dedupe(citations)

    def _translate_snippet_to_zh(self, text: str) -> str:
        raw = str(text or "").strip()
        if not raw:
            return ""
        if not self._model.ready:
            return raw
        prompt = (
            "请把下面这段天文资讯准确翻译成简体中文，只做翻译，不要补充新事实：\n"
            f"{raw}\n"
            "中文翻译："
        )
        ok, payload = self._model.answer(prompt, {"analysis": {"intent": "translate"}, "rag_items": []})
        if not ok:
            return raw
        translated, _ = self._extract_answer_payload(payload)
        translated = self._clean_answer(translated)
        if translated and self._contains_cjk(translated):
            return translated
        return raw

    def _build_model_question(
        self,
        question: str,
        analysis: dict[str, Any],
        strategy: dict[str, Any],
        memory_summary: str,
        rag_items: list[dict[str, Any]],
        target_lang: str,
    ) -> str:
        refs: list[str] = []
        for item in rag_items[:5]:
            title = str(item.get("title", "")).strip()
            source = str(item.get("source", "")).strip()
            snippet = str(item.get("snippet", "")).strip()
            if not snippet and not title:
                continue
            refs.append(f"- [{source}] {title}: {snippet[:260]}")

        if target_lang == "zh":
            style_req = (
                "Respond in Simplified Chinese.\n"
                "You are writing for astronomy enthusiasts on a public science education platform.\n"
                "Use a natural, vivid, and professional tone.\n"
                "Output 2-3 coherent paragraphs instead of technical bullet points.\n"
                "The first sentence must answer the user's question directly.\n"
                "Then explain mechanism, background, and why the topic is interesting or worth observing.\n"
                "Do not mention internal tools, routing, strategy, citations, or system status.\n"
            )
        else:
            style_req = (
                "Respond in English.\n"
                "Write for astronomy enthusiasts in a public science education product.\n"
                "Use 2-3 coherent paragraphs with a natural and professional tone.\n"
                "The first sentence must answer the question directly.\n"
                "Then explain mechanism, background, and why it matters.\n"
                "Do not mention internal tools, routing, strategy, citations, or system status.\n"
            )

        return (
            "You are a professional astronomy science communicator.\n"
            + style_req
            + "Keep the answer focused and fact-based.\n\n"
            + f"User question: {question}\n"
            + f"Intent: {analysis.get('intent', 'general')}\n"
            + f"Entities: {analysis.get('entities', [])}\n"
            + f"Session summary: {memory_summary[:300]}\n"
            + f"Strategy sources: {strategy.get('sources', [])}\n"
            + ("References:\n" + "\n".join(refs) + "\n\n" if refs else "")
            + "Final answer:"
        )

    def _retry_with_reflection(
        self,
        question: str,
        analysis: dict[str, Any],
        strategy: dict[str, Any],
        retrieval_bundle: dict[str, Any],
        memory_summary: str,
        turns: list[str],
        reflection: dict[str, Any],
        previous_answer: str,
    ) -> tuple[str, list[str]]:
        issues = [str(x) for x in reflection.get("issues", [])]
        if not issues:
            return "", []

        target_lang = "zh" if self._contains_cjk(question) else "en"
        rag_items = list(retrieval_bundle.get("rag_items", []))
        if target_lang == "zh":
            retry_prompt = (
                "请重写并修复上一版回答。\n"
                f"用户问题：{question}\n"
                f"上一版回答：{previous_answer}\n"
                f"问题列表：{issues}\n"
                "要求：只输出最终中文答案，成段表达，不输出任何内部信息。"
            )
        else:
            retry_prompt = (
                "Rewrite and fix the previous answer.\n"
                f"Question: {question}\n"
                f"Previous answer: {previous_answer}\n"
                f"Issues: {issues}\n"
                "Return only the final user-facing answer."
            )

        ok, payload = self._model.answer(
            retry_prompt,
            {
                "analysis": analysis,
                "strategy": strategy,
                "history": turns[-6:],
                "session_memory": memory_summary,
                "rag_items": rag_items[:10],
            },
        )
        if not ok:
            return "", []
        text, cits = self._extract_answer_payload(payload)
        cleaned = self._clean_answer(text)
        if cleaned and self._answer_is_relevant(question, analysis, cleaned, target_lang):
            return cleaned, cits
        return "", []

    def _reflect_answer(
        self,
        question: str,
        analysis: dict[str, Any],
        answer: str,
        retrieval_bundle: dict[str, Any],
        citations: list[str],
    ) -> dict[str, Any]:
        text = str(answer or "").strip()
        issues: list[str] = []

        if len(text) < 60:
            issues.append("answer_too_short")

        if re.search(r"(/api/v1|tool_plan|trace|internal|pipeline|system:)", text.lower()):
            issues.append("internal_leak")

        target_lang = "zh" if self._contains_cjk(question) else "en"
        if target_lang == "zh" and not self._contains_cjk(text):
            issues.append("non_chinese_output")

        if not self._answer_is_relevant(question, analysis, text, target_lang):
            issues.append("low_question_alignment")

        if retrieval_bundle.get("rag_items") and not citations:
            issues.append("missing_citations")

        need_number = any(
            k in str(question).lower()
            for k in ["多少", "多大", "多远", "温度", "质量", "半径", "体积", "how many", "distance", "temperature", "mass", "radius"]
        )
        if need_number and not re.search(r"\d", text):
            issues.append("missing_quantitative_hint")

        severe = {"internal_leak", "non_chinese_output", "low_question_alignment"}
        needs_retry = len(issues) >= 2 or any(x in severe for x in issues)
        return {
            "score": max(0.0, 1.0 - len(issues) * 0.18),
            "issues": issues,
            "needs_retry": needs_retry,
        }

    def _answer_is_relevant(self, question: str, analysis: dict[str, Any], answer: str, target_lang: str) -> bool:
        q = str(question or "").strip().lower()
        a = str(answer or "").strip().lower()
        if not a:
            return False
        if len(a) < 36:
            return False

        if target_lang == "zh" and not self._contains_cjk(answer):
            return False

        entities = [str(x).strip().lower() for x in analysis.get("entities", []) if str(x).strip()]
        entities_in_question = [ent for ent in entities if ent in q]
        intent = str(analysis.get("intent", "")).strip().lower()

        q_tokens = self._question_keywords(question)
        if q_tokens:
            hit = sum(1 for t in q_tokens if t in a)
            needed = 1
            if hit < needed and not any(ent in a for ent in entities_in_question[:3]):
                return False

        if intent == "comparison" and len(entities_in_question) >= 2:
            entity_hits = sum(1 for ent in entities_in_question[:3] if ent in a)
            compare_cues = ["比较", "差异", "区别", "相比", "两者", "各自", "而", "更"]
            if entity_hits < 2:
                return False
            if target_lang == "zh" and not any(cue in answer for cue in compare_cues):
                return False
        elif entities_in_question and not any(ent in a for ent in entities_in_question[:3]):
            return False

        if target_lang == "zh":
            challenge_q = any(k in q for k in ["最难", "难点", "挑战", "困难", "难在哪里", "难在哪"])
            if challenge_q:
                challenge_cues = [
                    "难点",
                    "挑战",
                    "困难",
                    "瓶颈",
                    "风险",
                    "受限",
                    "代价",
                    "技术门槛",
                ]
                if not any(c in answer for c in challenge_cues):
                    return False
            if "探测任务" in q or "任务角度" in q:
                mission_cues = ["任务", "探测器", "轨道", "着陆", "通信", "热控", "辐射", "推进", "电源", "样本"]
                if not any(c in answer for c in mission_cues):
                    return False

        if re.search(r"(tool_plan|pipeline|internal status|系统状态|内部流程)", a):
            return False
        return True

    def _compose_answer_from_rag(
        self,
        question: str,
        analysis: dict[str, Any],
        retrieval_bundle: dict[str, Any],
        target_lang: str,
    ) -> tuple[str, list[str]]:
        rag_items = list(retrieval_bundle.get("rag_items", []))
        if not rag_items:
            return "", []

        tokens = self._question_keywords(question)
        entities = [str(x).strip().lower() for x in analysis.get("entities", []) if str(x).strip()]
        latest_mode = any(k in str(question).lower() for k in ["\u6700\u65b0", "\u6700\u8fd1", "news", "latest", "recent", "today"])

        def score_item(item: dict[str, Any]) -> float:
            title = str(item.get("title", "")).lower()
            snippet = str(item.get("snippet", "")).lower()
            source = str(item.get("source", "")).lower()
            score = self._as_float(item.get("score"), 0.0)
            lexical = sum(1 for t in tokens if t in title or t in snippet)
            entity_hit = 1 if any(e in title or e in snippet for e in entities) else 0
            source_bonus = 0.2 if source in {"mcp", "dynamic", "kg"} or source.startswith("wikipedia") else 0.0
            return score + lexical * 0.2 + entity_hit * 0.25 + source_bonus

        ranked = sorted(rag_items, key=score_item, reverse=True)
        chosen: list[dict[str, Any]] = []
        for item in ranked:
            title = str(item.get("title", "")).strip()
            snippet = str(item.get("snippet", "")).strip()
            if not snippet and not title:
                continue
            hay = f"{title} {snippet}".lower()
            source = str(item.get("source", "")).lower()
            if latest_mode and source in {"mcp", "wikipedia_zh", "wikipedia_en", "web"}:
                chosen.append(item)
                if len(chosen) >= 3:
                    break
                continue
            entity_match = any(e in hay for e in entities if e)
            if tokens and not any(t in hay for t in tokens) and not entity_match:
                continue
            chosen.append(item)
            if len(chosen) >= 3:
                break

        if not chosen:
            return "", []

        parts: list[str] = []
        seen_parts: set[str] = set()
        for item in chosen:
            snippet = str(item.get("snippet", "")).strip()
            if not snippet:
                continue
            if target_lang == "zh" and not self._contains_cjk(snippet):
                snippet = self._translate_snippet_to_zh(snippet)
            snippet = re.sub(r"\s+", " ", snippet).strip(" \u3002\uff1b;,.\uff1a:")
            if len(snippet) < 8:
                continue
            if snippet in seen_parts:
                continue
            seen_parts.add(snippet)
            parts.append(snippet)

        if not parts:
            return "", []

        if target_lang == "zh":
            head = f"\u5148\u8bf4\u7ed3\u8bba\uff1a{parts[0]}\u3002"
            detail = ""
            if len(parts) >= 2:
                detail = "\n\n\u8fdb\u4e00\u6b65\u770b\uff0c" + "\uff1b".join(parts[1:3]) + "\u3002"
            text = self._polish_user_answer((head + detail).strip(), question, target_lang)
        else:
            head = f"In short, {parts[0]}."
            detail = ""
            if len(parts) >= 2:
                detail = "\n\nMore specifically, " + "; ".join(parts[1:3]) + "."
            text = (head + detail).strip()

        citations: list[str] = []
        for item in chosen:
            src = str(item.get("source", "")).strip() or "kb"
            title = str(item.get("title", "")).strip()
            citations.append(f"rag:{src}:{title}" if title else f"rag:{src}")
        return text.strip(), self._dedupe(citations)

    def _extract_answer_payload(self, payload: dict[str, Any] | str) -> tuple[str, list[str]]:
        if isinstance(payload, dict):
            text = str(payload.get("answer", "") or payload.get("text", "")).strip()
            citations = [str(x).strip() for x in payload.get("citations", []) if str(x).strip()]
            return text, citations
        raw = str(payload or "").strip()
        if raw.startswith("{") and raw.endswith("}"):
            parsed = self._parse_json_like(raw)
            if parsed:
                text = str(parsed.get("answer", "") or parsed.get("text", "")).strip()
                cits = [str(x).strip() for x in parsed.get("citations", []) if str(x).strip()]
                if text:
                    return text, cits
        return raw, []

    def _clean_answer(self, text: str) -> str:
        lines = [line.strip() for line in str(text or "").splitlines()]
        banned = ["trace", "tool_plan", "/api/v1", "pipeline", "internal status", "\u7cfb\u7edf\u72b6\u6001", "\u5185\u90e8\u6d41\u7a0b"]
        kept: list[str] = []
        for line in lines:
            if not line:
                continue
            low = line.lower()
            if any(x in low for x in banned):
                continue
            kept.append(line)
        out = "\n".join(kept).strip()
        out = re.sub(r"[ \t]+", " ", out)
        out = re.sub(r"\n{3,}", "\n\n", out)
        return out

    def _polish_user_answer(self, text: str, question: str, target_lang: str) -> str:
        out = self._clean_answer(text)
        if not out:
            return ""
        if target_lang != "zh":
            return out

        out = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", out)
        out = re.sub(r"(?<=[\u4e00-\u9fff])\?(?=[\u4e00-\u9fff])", "？", out)
        out = out.replace("\u3002\u3002", "\u3002").replace("\uff1a\uff1a", "\uff1a")
        out = out.replace("\n\n\n", "\n\n").strip()

        if len(out) < 80 and not out.startswith("\u5148\u8bf4\u7ed3\u8bba"):
            if out.endswith("\u3002"):
                out = f"\u5148\u8bf4\u7ed3\u8bba\uff1a{out}"
            else:
                out = f"\u5148\u8bf4\u7ed3\u8bba\uff1a{out}\u3002"

        if len(out) < 180 and any(k in question for k in ["\u4e3a\u4ec0\u4e48", "\u5982\u4f55", "\u600e\u4e48\u770b", "\u610f\u5473\u7740\u4ec0\u4e48", "\u6709\u4ec0\u4e48\u5f71\u54cd"]):
            if "\u5982\u679c\u4f60\u613f\u610f" not in out:
                out = out.rstrip("\u3002") + "\u3002\u5982\u679c\u4f60\u613f\u610f\uff0c\u6211\u8fd8\u53ef\u4ee5\u7ee7\u7eed\u5c55\u5f00\u5b83\u80cc\u540e\u7684\u5f62\u6210\u673a\u5236\u3001\u89c2\u6d4b\u65b9\u5f0f\uff0c\u4ee5\u53ca\u76f8\u5173\u53d1\u73b0\u4e3a\u4ec0\u4e48\u91cd\u8981\u3002"
        return out

    def _summarize_evidence(self, retrieval_bundle: dict[str, Any]) -> dict[str, Any]:
        items = list(retrieval_bundle.get("rag_items", []))
        source_counts: dict[str, int] = {}
        top_titles: list[str] = []
        for item in items:
            source = str(item.get("source", "")).strip() or "unknown"
            source_counts[source] = source_counts.get(source, 0) + 1
            title = str(item.get("title", "")).strip()
            if title and title not in top_titles:
                top_titles.append(title)
        return {
            "rounds": int(retrieval_bundle.get("rounds", 1) or 1),
            "item_count": len(items),
            "source_counts": source_counts,
            "top_titles": top_titles[:5],
            "has_graph_path": bool(retrieval_bundle.get("graph_path")),
        }

    def _stage_message(
        self,
        stage: str,
        entities: list[str] | None = None,
        strategy: dict[str, Any] | None = None,
        retrieval_bundle: dict[str, Any] | None = None,
        reflection: dict[str, Any] | None = None,
        round_id: int | None = None,
    ) -> str:
        if stage == "analysis":
            focus = "\u3001".join([str(x) for x in (entities or [])[:3] if str(x).strip()])
            if focus:
                return f"\u6b63\u5728\u7406\u89e3\u4f60\u7684\u95ee\u9898\uff0c\u5148\u805a\u7126\u5230“{focus}”\u8fd9\u4e2a\u4e3b\u9898\u3002"
            return "\u6b63\u5728\u7406\u89e3\u4f60\u7684\u95ee\u9898\uff0c\u5148\u5224\u65ad\u6d89\u53ca\u7684\u4e3b\u9898\u548c\u5173\u952e\u5929\u4f53\u3002"
        if stage == "strategy":
            sources = [str(x) for x in (strategy or {}).get("sources", []) if str(x).strip()]
            label_map = {
                "kb": "\u672c\u5730\u77e5\u8bc6\u5e93",
                "kg": "\u77e5\u8bc6\u56fe\u8c31",
                "dynamic": "\u52a8\u6001\u5929\u6587\u6570\u636e",
                "mcp": "\u5916\u90e8\u5de5\u5177",
                "web": "\u8054\u7f51\u4fe1\u606f",
                "model": "\u6a21\u578b\u76f4\u7b54",
            }
            readable = "\u3001".join([label_map.get(src, src) for src in sources]) or "\u6a21\u578b\u76f4\u7b54"
            complexity = str((strategy or {}).get("complexity", "medium"))
            complexity_text = {
                "simple": "\u76f4\u63a5\u56de\u7b54",
                "medium": "\u5355\u8f6e\u68c0\u7d22",
                "complex": "\u591a\u8f6e\u68c0\u7d22",
            }.get(complexity, "\u81ea\u9002\u5e94\u68c0\u7d22")
            return f"\u5df2\u89c4\u5212\u56de\u7b54\u7b56\u7565\uff1a{complexity_text}\uff0c\u5f53\u524d\u4f18\u5148\u4f7f\u7528 {readable}\u3002"
        if stage == "retrieval":
            items = len((retrieval_bundle or {}).get("rag_items", []))
            if round_id and round_id >= 2:
                return f"\u8865\u5145\u68c0\u7d22\u5df2\u5b8c\u6210\uff0c\u76ee\u524d\u6574\u7406\u5230 {items} \u6761\u6709\u6548\u7ebf\u7d22\u3002"
            return f"\u6b63\u5728\u68c0\u7d22\u76f8\u5173\u77e5\u8bc6\u4e0e\u6570\u636e\uff0c\u76ee\u524d\u5df2\u62ff\u5230 {items} \u6761\u5019\u9009\u7ebf\u7d22\u3002"
        if stage == "compose":
            return "\u6b63\u5728\u628a\u7ebf\u7d22\u6574\u7406\u6210\u66f4\u81ea\u7136\u3001\u66f4\u9002\u5408\u9605\u8bfb\u7684\u79d1\u666e\u56de\u7b54\u3002"
        if stage == "reflection":
            issues = list((reflection or {}).get("issues", []))
            if issues:
                return "\u6b63\u5728\u68c0\u67e5\u7b54\u6848\u662f\u5426\u504f\u9898\u3001\u9057\u6f0f\u6216\u8868\u8ff0\u4e0d\u591f\u51c6\u786e\u3002"
            return "\u5df2\u5b8c\u6210\u7b54\u6848\u81ea\u68c0\uff0c\u6b63\u5728\u8f93\u51fa\u6700\u7ec8\u7ed3\u679c\u3002"
        return "\u6b63\u5728\u5904\u7406\u3002"

    def _question_keywords(self, text: str) -> list[str]:
        content = str(text or "").lower()
        raw = re.findall(r"[\u4e00-\u9fff]{2,}|[a-z][a-z0-9\-]{2,}", content)
        stop = {
            "什么",
            "怎么",
            "如何",
            "为什么",
            "多少",
            "多大",
            "多远",
            "曾经",
            "现在",
            "目前",
            "最近",
            "一下",
            "详细",
            "解释",
            "科普",
            "回答",
            "值得",
            "关注",
            "请用",
            "中文",
            "天文新闻",
            "这个",
            "那个",
            "请问",
            "what",
            "why",
            "how",
            "many",
            "much",
            "latest",
            "recent",
            "today",
            "week",
            "the",
            "and",
        }
        out: list[str] = []
        for token in raw:
            if token in stop or len(token) < 2:
                continue
            if self._contains_cjk(token) and len(token) > 4:
                # Lightweight CJK segmentation via 2-gram windows.
                for i in range(0, len(token) - 1):
                    gram = token[i : i + 2]
                    if gram in stop or gram in out:
                        continue
                    out.append(gram)
                continue
            if token not in out:
                out.append(token)
        return out[:12]

    def _parse_json_like(self, text: str) -> dict[str, Any]:
        raw = str(text or "").strip()
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            pass
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def _build_lookup_query(self, question: str, analysis: dict[str, Any]) -> str:
        q = str(question or "").strip()
        entities = [str(x).strip() for x in analysis.get("entities", []) if str(x).strip()]
        if entities:
            return " ".join(entities[:2])
        tokens = self._question_keywords(q)
        if tokens:
            return " ".join(tokens[:2])
        return q

    def _pick_dynamic_target(self, question: str, analysis: dict[str, Any]) -> str | None:
        q = str(question or "")
        for pattern in EXOPLANET_PATTERNS:
            m = re.search(pattern, q, flags=re.IGNORECASE)
            if m:
                return str(m.group(0)).strip()
        for name in analysis.get("entities", []):
            n = str(name).strip()
            if not n:
                continue
            if any(re.search(pattern, n, flags=re.IGNORECASE) for pattern in EXOPLANET_PATTERNS):
                return n
        return None

    @staticmethod
    def _contains_cjk(text: str) -> bool:
        return bool(re.search(r"[\u4e00-\u9fff]", str(text or "")))

    def _is_dynamic_query(self, question: str, entities: list[str]) -> bool:
        q_low = str(question or "").lower()
        if "绯诲琛屾槦" in str(question or "") or "exoplanet" in q_low:
            return True
        if any(re.search(pattern, q_low, flags=re.IGNORECASE) for pattern in EXOPLANET_PATTERNS):
            return True
        for ent in entities:
            if any(re.search(pattern, ent, flags=re.IGNORECASE) for pattern in EXOPLANET_PATTERNS):
                return True
        return False

    @staticmethod
    def _as_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except Exception:
            return default

    def _dedupe(self, items: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for item in items:
            value = str(item).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            out.append(value)
        return out

    def _dedupe_rag_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in items:
            key = "|".join(
                [
                    str(item.get("title", "")).strip().lower(),
                    str(item.get("source", "")).strip().lower(),
                    str(item.get("snippet", "")).strip()[:140].lower(),
                ]
            )
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    def _connect(self) -> sqlite3.Connection:
        return get_sqlite_connection(self._db_path)

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS qa_agent_memory (
                    session_id TEXT PRIMARY KEY,
                    summary TEXT NOT NULL,
                    topic_tags TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS qa_reflection_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    reflection_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def _load_memory(self, session_id: str) -> dict[str, Any]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT summary, topic_tags FROM qa_agent_memory WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return {"summary": "", "topic_tags": []}
        summary = str(row["summary"] or "")
        raw = str(row["topic_tags"] or "[]")
        try:
            tags = json.loads(raw)
        except Exception:
            tags = []
        if not isinstance(tags, list):
            tags = []
        return {"summary": summary, "topic_tags": tags}

    def _update_memory(
        self,
        session_id: str,
        question: str,
        answer: str,
        analysis: dict[str, Any],
        reflection: dict[str, Any],
    ) -> None:
        memory = self._load_memory(session_id)
        previous = str(memory.get("summary", "")).strip()
        turn_summary = self._build_turn_summary(question, answer, analysis, reflection)
        merged = f"{previous}\n{turn_summary}".strip() if previous else turn_summary
        if len(merged) > 1800:
            merged = merged[-1800:]

        tags = set([str(x) for x in memory.get("topic_tags", []) if str(x).strip()])
        for entity in analysis.get("entities", [])[:6]:
            name = str(entity).strip()
            if name:
                tags.add(name)
        tag_list = [x for x in list(tags) if x][:14]

        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO qa_agent_memory (session_id, summary, topic_tags, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(session_id) DO UPDATE SET
                    summary = excluded.summary,
                    topic_tags = excluded.topic_tags,
                    updated_at = datetime('now')
                """,
                (session_id, merged, json.dumps(tag_list, ensure_ascii=False)),
            )
            conn.commit()
        finally:
            conn.close()

    def _save_reflection(
        self,
        session_id: str,
        question: str,
        answer: str,
        reflection: dict[str, Any],
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO qa_reflection_logs (session_id, question, answer, reflection_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    session_id,
                    str(question),
                    str(answer),
                    json.dumps(reflection, ensure_ascii=False),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _build_turn_summary(
        self,
        question: str,
        answer: str,
        analysis: dict[str, Any],
        reflection: dict[str, Any],
    ) -> str:
        intent = str(analysis.get("intent", "general"))
        entities = [str(x) for x in analysis.get("entities", []) if str(x).strip()]
        short_answer = str(answer or "").strip().replace("\n", " ")
        if len(short_answer) > 180:
            short_answer = short_answer[:180] + "..."
        issues = ",".join([str(x) for x in reflection.get("issues", [])]) or "none"
        entity_text = "|".join(entities[:5]) if entities else "none"
        return (
            f"[{datetime.utcnow().isoformat()}] intent={intent}; entities={entity_text}; "
            f"question={question}; answer={short_answer}; reflection={issues}"
        )

