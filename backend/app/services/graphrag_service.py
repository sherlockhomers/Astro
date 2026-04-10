"""
GraphRAG 检索模块 — 知识图谱增强检索（运行逻辑.md 模块 2.2）。

工作流：
1. 接收用户问题，提取关键天文实体
2. 在知识图谱中执行多跳查询
3. 将图查询结果转换为流畅的科普风格描述
"""

from __future__ import annotations

from typing import Any

from app.services.data_service import DataService
from app.services.graph_service import GraphService
from app.services.retrieval_service import RetrievalService
from app.services import prompt_templates as tpl

_ALIASES: dict[str, str] = {
    "木星": "Jupiter", "火星": "Mars", "地球": "Earth",
    "土星": "Saturn", "金星": "Venus", "水星": "Mercury",
    "天王星": "Uranus", "海王星": "Neptune", "冥王星": "Pluto",
    "银河系": "Milky Way", "国际空间站": "International Space Station",
}


class GraphRAGService:

    def __init__(
        self,
        data_service: DataService,
        retrieval_service: RetrievalService,
        graph_service: GraphService,
    ) -> None:
        self._data_service = data_service
        self._retrieval_service = retrieval_service
        self._graph_service = graph_service

    def query(self, question: str) -> dict[str, Any]:
        normalized = self._expand_aliases(question)
        entities = self._extract_entities(normalized)
        intent = self._infer_intent(normalized, entities)

        retrieval_items, retrieval_note = self._retrieval_service.hybrid_search(
            normalized, None, top_k=40,
        )
        retrieval_items = self._filter_catalog(retrieval_items)

        if not retrieval_items:
            fallback, f_note = self._retrieval_service.search(normalized, top_k=30)
            retrieval_items = self._filter_catalog(fallback)
            retrieval_note = f"{retrieval_note} | fallback={f_note}"

        if not retrieval_items:
            retrieval_items = self._keyword_retrieval(normalized, top_k=10)
            retrieval_note += " | fallback=keyword_search"

        path = self._resolve_path(entities)
        schema = self._graph_service.graph_schema_summary()

        context = {
            "entities": entities,
            "intent": intent,
            "retrieval_top": retrieval_items[:5],
            "subgraph_edges": self._graph_service.preview_paths(top_k=20)[:10],
            "schema": schema,
            "reasoning_path": path,
        }

        answer = self._generate_fluent_answer(normalized, context)
        citations = self._build_citations(context)

        return {
            "answer": answer,
            "trace": {
                "step1_intent": intent,
                "step2_retrieval_note": retrieval_note,
                "step2_retrieval_count": len(retrieval_items),
                "step3_context": context,
                "step4_generation": "graphrag-fluent-generator",
            },
            "citations": citations,
        }

    # ------------------------------------------------------------------
    #  流畅答案生成（核心改进）
    # ------------------------------------------------------------------

    def _generate_fluent_answer(
        self, question: str, context: dict[str, Any]
    ) -> str:
        entities = context["entities"]
        intent = context["intent"]
        top = context["retrieval_top"]
        path = context["reasoning_path"]

        if intent == "comparison" and len(entities) >= 2:
            entity_a = self._find_full_entity(entities[0])
            entity_b = self._find_full_entity(entities[1])
            if entity_a and entity_b:
                return tpl.format_comparison(entity_a, entity_b, question)

        if intent == "relation_reasoning" and len(entities) >= 2:
            return tpl.format_relation_path(entities[0], entities[1], path)

        if entities:
            primary = self._find_full_entity(entities[0])
            if primary:
                body = tpl._get_body(primary)
                if body:
                    answer = tpl.format_science_article(
                        question,
                        str(primary.get("name", "")),
                        str(primary.get("category", "")),
                        body,
                    )
                    for extra_name in entities[1:3]:
                        extra = self._find_full_entity(extra_name)
                        if extra:
                            extra_body = tpl._get_body(extra)
                            extra_sents = tpl.extract_relevant_sentences(
                                extra_body, question, max_sentences=2,
                            )
                            if extra_sents:
                                answer += "\n\n" + "。".join(extra_sents) + "。"
                    return answer

        if top:
            lead_entity = self._find_full_entity(str(top[0].get("title", "")))
            if lead_entity:
                body = tpl._get_body(lead_entity)
                if body:
                    return tpl.format_general_qa(
                        question,
                        str(lead_entity.get("name", "")),
                        str(lead_entity.get("category", "")),
                        body,
                    )
            snippets = [str(item.get("snippet", "")).strip() for item in top[:3] if item.get("snippet")]
            if snippets:
                return "。".join(s.rstrip("。") for s in snippets if s) + "。"

        return tpl.format_no_result(question)

    # ------------------------------------------------------------------
    #  辅助方法
    # ------------------------------------------------------------------

    def _find_full_entity(self, name: str) -> dict[str, Any] | None:
        target = name.strip().lower()
        for entity in self._data_service.export_entities():
            if str(entity.get("name", "")).strip().lower() == target:
                return entity
        return None

    def _extract_entities(self, question: str) -> list[str]:
        result: list[str] = []
        for entity in self._data_service.export_entities():
            name = str(entity.get("name", "")).strip()
            if name and len(name) >= 2 and name in question:
                result.append(name)
            if len(result) >= 5:
                break
        return result

    def _infer_intent(self, question: str, entities: list[str]) -> str:
        q = question.lower()
        if any(k in q for k in ["关系", "路径", "关联", "属于"]):
            return "relation_reasoning"
        if any(k in q for k in ["比较", "差异", "哪个大", "哪个更", "对比", "区别"]):
            return "comparison"
        if entities:
            return "entity_fact_lookup"
        return "semantic_retrieval"

    def _resolve_path(self, entities: list[str]) -> list[dict[str, str]]:
        if len(entities) < 2:
            return []
        return self._graph_service.find_path(entities[0], entities[1], max_hops=4)

    def _build_citations(self, context: dict[str, Any]) -> list[str]:
        citations: list[str] = []
        for entity in context.get("entities", [])[:5]:
            citations.append(f"entity:{entity}")
        for item in context.get("retrieval_top", [])[:5]:
            eid = item.get("id")
            if eid:
                citations.append(f"doc:{eid}")
        path = context.get("reasoning_path", [])
        if path:
            citations.append(f"graph:path_hops={len(path)}")
        return citations or ["system:retrieval"]

    def _filter_catalog(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [x for x in items if "images_catalog" not in str(x.get("source", "")).lower()]

    def _keyword_retrieval(self, query: str, top_k: int) -> list[dict[str, Any]]:
        rows = self._data_service.search(query, top_k=top_k * 3)
        return self._filter_catalog(rows)[:top_k]

    def _expand_aliases(self, question: str) -> str:
        text = question
        lowered = text.lower()
        for cn, en in _ALIASES.items():
            if cn in text and en.lower() not in lowered:
                text = f"{text} {en}"
                lowered = text.lower()
        return text
