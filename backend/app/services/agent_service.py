from __future__ import annotations

import re
from typing import Any

from app.services import prompt_templates as tpl
from app.services.data_service import DataService
from app.services.graph_service import GraphService
from app.services.retrieval_service import RetrievalService

INTENT_ENTITY_LOOKUP = "entity_lookup"
INTENT_COMPARISON = "comparison"
INTENT_RELATION = "relation"
INTENT_SCIENCE_QA = "science_qa"
INTENT_FACT_QUERY = "fact_query"
INTENT_GENERAL = "general"

EXOPLANET_PATTERNS = (
    r"\b(?:TOI|HD|K2|Kepler|WASP|TRAPPIST|LHS|GJ|Gliese|CoRoT|HIP|KIC)[-\s]?\d+[A-Za-z]?(?:\s*[bcdefg])?\b",
    r"\b[A-Za-z]{2,8}[-\s]?\d{2,7}\s?[bcdefg]\b",
)

ALIASES: dict[str, str] = {
    "木星": "Jupiter",
    "火星": "Mars",
    "地球": "Earth",
    "土星": "Saturn",
    "金星": "Venus",
    "水星": "Mercury",
    "天王星": "Uranus",
    "海王星": "Neptune",
    "冥王星": "Pluto",
    "太阳": "Sun",
    "月球": "Moon",
    "银河系": "Milky Way",
    "系外行星": "exoplanet",
    "黑洞": "black hole",
    "星云": "nebula",
    "星系": "galaxy",
    "彗星": "comet",
    "小行星": "asteroid",
}

GENERIC_ENTITY_TITLES: frozenset[str] = frozenset(
    {
        "卫星",
        "恒星",
        "行星",
        "彗星",
        "流星",
        "星系",
        "星云",
        "流星群",
        "小行星",
    }
)


class AgentService:
    """Deterministic orchestration agent for local KB/KG."""

    def __init__(
        self,
        data_service: DataService,
        retrieval_service: RetrievalService,
        graph_service: GraphService,
    ) -> None:
        self._data = data_service
        self._retrieval = retrieval_service
        self._graph = graph_service
        # 实体名索引映射：O(n) 构建一次，O(1) 查询
        self._entity_index: dict[str, dict[str, Any]] = {}
        self._index_revision = -1

    def _ensure_entity_index(self) -> None:
        """惰性构建实体索引，数据变更时自动重建。"""
        if self._index_revision == self._data.revision:
            return
        self._entity_index.clear()
        for entity in self._data.export_entities():
            name = str(entity.get("name", "")).strip()
            if not name:
                continue
            name_lc = name.lower()
            # 同名保留第一条（与原有逻辑一致）
            if name_lc not in self._entity_index:
                self._entity_index[name_lc] = entity
        self._index_revision = self._data.revision

    def find_entities_batch(self, names: list[str]) -> dict[str, dict[str, Any]]:
        """一次性 O(n) 批量查找多个实体名，避免 N 次重复检查 revision。"""
        self._ensure_entity_index()
        return {n: self._entity_index[n.lower()] for n in names if n.lower() in self._entity_index}

    def find_entity_by_name(self, name: str) -> dict[str, Any] | None:
        target = str(name).strip().lower()
        if not target:
            return None
        self._ensure_entity_index()
        return self._entity_index.get(target)

    def analyze(self, question: str, history: list[str] | None = None) -> dict[str, Any]:
        q = self._normalize_question(question)
        expanded_q = self._expand_aliases(q)
        intent = self._analyze_intent(expanded_q)
        entities = self._extract_entities(expanded_q)
        entity_names = [str(x.get("name", "")).strip() for x in entities if str(x.get("name", "")).strip()]
        tools = self._tool_plan(intent=intent, question=expanded_q, entity_names=entity_names)
        return {
            "question": question,
            "normalized_question": q,
            "expanded_question": expanded_q,
            "intent": intent,
            "entities": entity_names,
            "tool_plan": tools,
            "history_size": len(history or []),
        }

    def answer(self, question: str, history: list[str] | None = None) -> dict[str, Any]:
        identity = self._answer_identity(question)
        if identity is not None:
            return self._result(
                answer=identity,
                citations=["builtin:assistant_profile"],
                graph_path=[],
                intent=INTENT_GENERAL,
                entities_found=[],
                analysis={"intent": INTENT_GENERAL, "tool_plan": ["builtin"]},
            )

        builtin = self._answer_builtin_fact(question)
        if builtin is not None:
            return self._result(
                answer=builtin,
                citations=["builtin:astronomy"],
                graph_path=[],
                intent=INTENT_FACT_QUERY,
                entities_found=[],
                analysis={"intent": INTENT_FACT_QUERY, "tool_plan": ["builtin"]},
            )

        if not self._data.loaded:
            return self._result(
                answer="数据源尚未加载，请先加载 Excel/CSV 数据后再提问。",
                citations=["system:DATA_NOT_READY"],
                graph_path=[],
                intent=INTENT_GENERAL,
                entities_found=[],
                analysis={"intent": INTENT_GENERAL, "tool_plan": []},
            )

        analysis = self.analyze(question, history)
        intent = str(analysis["intent"])
        entities = [self.find_entity_by_name(name) for name in analysis["entities"]]
        entities = [e for e in entities if e]
        entity_names = [str(e.get("name", "")) for e in entities]
        explicit_tokens = self._extract_exoplanet_tokens(question)
        direct_entity_hit = any(len(name) >= 2 and name.lower() in str(question).lower() for name in entity_names)

        if not self._looks_astronomy_question(question) and not direct_entity_hit and not explicit_tokens:
            probe, _ = self._retrieval.search(question, top_k=3)
            top_score = float(probe[0].get("score", 0.0) or 0.0) if probe else 0.0
            if top_score < 0.2:
                return self._result(
                    answer=(
                        "我是 ASTRO 天文科普助手，主要回答天文学相关问题。"
                        "你可以直接问某个天体、天文现象或任务，例如“火星为什么是红色的”或“木星有多少颗卫星”。"
                    ),
                    citations=["builtin:assistant_scope"],
                    graph_path=[],
                    intent=INTENT_GENERAL,
                    entities_found=[],
                    analysis=analysis,
                )

        if intent in {INTENT_RELATION, INTENT_COMPARISON} and len(entities) < 2:
            hint = "、".join(entity_names) if entity_names else "无"
            return self._result(
                answer=f"这是一个需要两个实体的问题，但当前仅识别到：{hint}。请再补充另一个实体名称。",
                citations=[f"entity:{n}" for n in entity_names] or ["system:NO_RESULT"],
                graph_path=[],
                intent=intent,
                entities_found=entity_names,
                analysis=analysis,
            )

        if intent == INTENT_RELATION and len(entities) >= 2:
            return self._handle_relation(entities, analysis)
        if intent == INTENT_COMPARISON and len(entities) >= 2:
            return self._handle_comparison(question, entities, analysis)
        if intent == INTENT_FACT_QUERY and entities:
            return self._handle_fact_query(question, entities[0], analysis)
        if entities:
            return self._handle_entity_qa(question, entities, intent, analysis)
        return self._handle_search_qa(question, intent, analysis)

    def _normalize_question(self, question: str) -> str:
        text = str(question or "").strip()
        text = text.replace("\u3000", " ")
        text = re.sub(r"\s+", " ", text)
        return text

    def _expand_aliases(self, question: str) -> str:
        q = question
        q_lower = q.lower()
        for zh, en in ALIASES.items():
            if zh in q and en.lower() not in q_lower:
                q = f"{q} {en}"
                q_lower = q.lower()
        return q

    def _tool_plan(self, intent: str, question: str, entity_names: list[str]) -> list[str]:
        plan: list[str] = []
        if intent in {INTENT_FACT_QUERY, INTENT_ENTITY_LOOKUP, INTENT_SCIENCE_QA, INTENT_GENERAL}:
            plan.append("retrieval")
        if intent in {INTENT_RELATION, INTENT_COMPARISON}:
            plan.append("graph")
        if self._has_image_need(question):
            plan.append("image")
        if self._has_dynamic_need(question) or self._extract_exoplanet_tokens(question):
            plan.append("dynamic")
        if any(self._is_exoplanet_token(n) for n in entity_names):
            plan.append("dynamic")

        out: list[str] = []
        seen: set[str] = set()
        for x in plan:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    def _analyze_intent(self, question: str) -> str:
        q = question.lower()
        if re.search(r"\b(vs|compare|comparison|relation|path|link|different|difference)\b", q):
            if any(k in q for k in ["compare", "comparison", "vs", "different", "difference"]):
                return INTENT_COMPARISON
            return INTENT_RELATION
        if any(kw in q for kw in ["关系", "路径", "关联", "属于", "联系", "连接"]):
            return INTENT_RELATION
        if any(kw in q for kw in ["比较", "对比", "差异", "区别", "不同", "更大", "更小"]):
            return INTENT_COMPARISON
        if any(
            kw in q
            for kw in [
                "多少",
                "几",
                "多大",
                "多远",
                "多重",
                "质量",
                "半径",
                "轨道周期",
                "发现时间",
                "发现方式",
                "体积",
                "直径",
                "温度",
            ]
        ):
            return INTENT_FACT_QUERY
        if any(kw in q for kw in ["为什么", "怎么", "如何", "原理", "机制", "形成", "是什么"]):
            return INTENT_SCIENCE_QA
        return INTENT_GENERAL

    def _extract_entities(self, question: str) -> list[dict[str, Any]]:
        matched: list[tuple[int, dict[str, Any]]] = []
        q_lower = question.lower()
        explicit_tokens = self._extract_exoplanet_tokens(question)
        explicit_entities: list[dict[str, Any]] = []
        for token in explicit_tokens:
            full = self.find_entity_by_name(token)
            if full is not None:
                explicit_entities.append(full)
            else:
                explicit_entities.append({"name": token, "category": "exoplanet_token", "raw": {}, "description": ""})

        # 使用索引进行 O(1) 查找，而非遍历全部实体
        self._ensure_entity_index()
        if not self._entity_index:
            search_results, _ = self._retrieval.search(question, top_k=16)
            entities: list[dict[str, Any]] = []
            hit_map = self.find_entities_batch([
                str(item.get("title", "")).strip() for item in search_results[:8]
            ])
            for item in search_results[:8]:
                title = str(item.get("title", "")).strip()
                if not title:
                    continue
                if title.lower() in hit_map:
                    entities.append(hit_map[title.lower()])
            if explicit_tokens:
                for token in explicit_tokens:
                    entities.append({"name": token, "category": "exoplanet_token", "raw": {}, "description": ""})
            return entities[:6]

        for name_lc, entity in self._entity_index.items():
            name = str(entity.get("name", "")).strip()
            if len(name) < 2:
                continue
            if name_lc in q_lower or name in question:
                matched.append((len(name), entity))

        matched.sort(key=lambda x: -x[0])
        if matched:
            ranked = self._rank_entities_for_question(question, [e for _, e in matched])
            merged: list[dict[str, Any]] = []
            seen: set[str] = set()
            for ent in explicit_entities + ranked:
                name = str(ent.get("name", "")).strip()
                if not name:
                    continue
                key = name.lower()
                if key in seen:
                    continue
                seen.add(key)
                merged.append(ent)
            return merged[:6]

        search_results, _ = self._retrieval.search(question, top_k=16)
        entities: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        hit_map = self.find_entities_batch([
            str(item.get("title", "")).strip() for item in search_results[:8]
        ])
        for item in search_results[:8]:
            title = str(item.get("title", "")).strip()
            if not title or title in seen_names:
                continue
            if title.lower() in hit_map:
                entities.append(hit_map[title.lower()])
                seen_names.add(title)

        if explicit_tokens:
            for token in explicit_tokens:
                if token not in seen_names:
                    entities.append({"name": token, "category": "exoplanet_token", "raw": {}, "description": ""})
                    seen_names.add(token)

        return entities[:6]

    def _rank_entities_for_question(self, question: str, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        subjects = [s for s in sorted(ALIASES.keys(), key=len, reverse=True) if s in question]
        explicit = self._extract_exoplanet_tokens(question)

        def sort_key(ent: dict[str, Any]) -> tuple[int, int]:
            name = str(ent.get("name", "")).strip()
            if not name:
                return (4, 0)
            if explicit and any(name.lower() == x.lower() for x in explicit):
                return (0, -len(name))
            for subj in subjects:
                if name == subj or name.startswith(subj) or subj in name:
                    return (1, -len(name))
            if name in GENERIC_ENTITY_TITLES:
                return (3, -len(name))
            return (2, -len(name))

        return sorted(entities, key=sort_key)

    def _handle_relation(self, entities: list[dict[str, Any]], analysis: dict[str, Any]) -> dict[str, Any]:
        src = str(entities[0].get("name", ""))
        tgt = str(entities[1].get("name", ""))
        path = self._graph.find_path(src, tgt, max_hops=4)
        answer = tpl.format_relation_path(src, tgt, path)
        citations = [f"entity:{src}", f"entity:{tgt}"]
        if path:
            citations.append(f"graph:path_hops={len(path)}")
        return self._result(answer, citations, path, INTENT_RELATION, [src, tgt], analysis)

    def _handle_comparison(self, question: str, entities: list[dict[str, Any]], analysis: dict[str, Any]) -> dict[str, Any]:
        a, b = entities[0], entities[1]
        answer = tpl.format_comparison(a, b, question)
        citations = [f"entity:{a.get('name', '')}", f"entity:{b.get('name', '')}"]
        return self._result(answer, citations, [], INTENT_COMPARISON, [str(a.get("name", "")), str(b.get("name", ""))], analysis)

    def _handle_fact_query(self, question: str, entity: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
        name = str(entity.get("name", ""))
        fact_line = self._extract_specific_fact(question, entity.get("raw", {}), name)
        detail = tpl.format_entity_detail(entity, question)
        answer = fact_line if fact_line else detail
        if fact_line and detail and fact_line not in detail:
            answer = f"{fact_line}\n\n{detail}"
        return self._result(answer, [f"entity:{name}"], [], INTENT_FACT_QUERY, [name], analysis)

    def _handle_entity_qa(self, question: str, entities: list[dict[str, Any]], intent: str, analysis: dict[str, Any]) -> dict[str, Any]:
        primary = entities[0]
        name = str(primary.get("name", ""))
        category = str(primary.get("category", ""))
        body = tpl._get_body(primary)
        answer = tpl.format_science_article(question, name, category, body)
        citations = [f"entity:{name}"]

        for extra in entities[1:3]:
            extra_body = tpl._get_body(extra)
            if not extra_body:
                continue
            extra_sents = tpl.extract_relevant_sentences(extra_body, question, max_sentences=2)
            if extra_sents:
                answer += "\n\n" + " ".join(extra_sents)
                citations.append(f"entity:{extra.get('name', '')}")

        return self._result(
            answer,
            citations,
            [],
            intent or INTENT_SCIENCE_QA,
            [str(e.get("name", "")) for e in entities[:3]],
            analysis,
        )

    def _handle_search_qa(self, question: str, intent: str, analysis: dict[str, Any]) -> dict[str, Any]:
        search_results, _ = self._retrieval.search(question, top_k=20)
        if not search_results:
            return self._result(tpl.format_no_result(question), ["system:NO_RESULT"], [], intent, [], analysis)

        filtered_results = self._filter_search_results_for_question(question, analysis, search_results)
        if filtered_results:
            search_results = filtered_results
        elif self._question_has_explicit_anchor(question, analysis):
            return self._result(tpl.format_no_result(question), ["system:NO_RESULT"], [], intent, [], analysis)

        explicit_token = self._extract_explicit_object_token(question)
        top = search_results[0]
        top_score = float(top.get("score", 0.0) or 0.0)
        if top_score < 0.32 and not explicit_token:
            return self._result(
                "这个问题在当前知识库里没有足够高置信度的匹配结果。你可以补充更具体的天体名或关键条件。",
                ["system:NO_RESULT"],
                [],
                intent,
                [],
                analysis,
            )

        if explicit_token:
            title_lc = str(top.get("title", "")).lower()
            if explicit_token.lower() not in title_lc:
                return self._result(
                    f"知识库中暂未找到“{explicit_token}”的可靠条目，建议补充该实体数据后再查询。",
                    ["system:NO_RESULT"],
                    [],
                    intent,
                    [],
                    analysis,
                )

        full_entity = self.find_entity_by_name(str(top.get("title", "")))
        if full_entity:
            body = tpl._get_body(full_entity)
            if body:
                answer = tpl.format_general_qa(
                    question,
                    str(full_entity.get("name", "")),
                    str(full_entity.get("category", "")),
                    body,
                )
                return self._result(
                    answer,
                    [f"entity:{full_entity.get('name', '')}"],
                    [],
                    intent,
                    [str(full_entity.get("name", ""))],
                    analysis,
                )

        snippets: list[str] = []
        citation_ids: list[str] = []
        for item in search_results[:3]:
            s = str(item.get("snippet", "")).strip()
            if not s:
                continue
            snippets.append(s.rstrip("。"))
            citation_ids.append(f"entity:{item.get('id', '')}")
        if snippets:
            return self._result("。".join(snippets) + "。", citation_ids, [], intent, [], analysis)
        return self._result(tpl.format_no_result(question), ["system:NO_RESULT"], [], intent, [], analysis)

    def _filter_search_results_for_question(
        self,
        question: str,
        analysis: dict[str, Any],
        search_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        q = str(question or "").lower()
        if not q:
            return search_results

        anchors = [
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
            "黑洞",
            "银河系",
            "中子星",
            "超新星",
            "星云",
            "星系",
            "行星",
            "恒星",
        ]
        required_terms = [term for term in anchors if term in q]
        for ent in analysis.get("entities", []):
            name = str(ent).strip().lower()
            if len(name) >= 2 and name in q and name not in required_terms:
                required_terms.append(name)

        q_keywords = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-z][a-z0-9\-]{2,}", q))
        out: list[dict[str, Any]] = []
        for item in search_results:
            title = str(item.get("title", "")).strip()
            snippet = str(item.get("snippet", "")).strip()
            haystack = f"{title} {snippet}".lower()
            if required_terms and not any(term.lower() in haystack for term in required_terms):
                continue
            if q_keywords:
                hit_count = sum(1 for token in list(q_keywords)[:6] if token in haystack)
                if required_terms and hit_count < 1:
                    continue
            out.append(item)
        return out

    def _question_has_explicit_anchor(self, question: str, analysis: dict[str, Any]) -> bool:
        q = str(question or "").lower()
        anchors = [
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
            "黑洞",
            "银河系",
            "中子星",
            "超新星",
            "星云",
            "星系",
            "行星",
            "恒星",
        ]
        if any(term in q for term in anchors):
            return True
        for ent in analysis.get("entities", []):
            name = str(ent).strip().lower()
            if len(name) >= 2 and name in q:
                return True
        return False

    def _extract_specific_fact(self, question: str, raw: dict[str, Any], entity_name: str) -> str:
        if not isinstance(raw, dict):
            return ""
        q = question.lower()
        norm = {str(k).strip().lower(): v for k, v in raw.items()}

        def pick(keys: list[str]) -> str:
            for key in keys:
                val = norm.get(key.lower())
                if val is None:
                    continue
                txt = str(val).strip()
                if txt and txt.lower() not in {"none", "nan", "null", "unknown"}:
                    return txt
            return ""

        field_rules: list[tuple[list[str], str, list[str]]] = [
            (["质量", "mass"], "质量", ["mass", "mass (earth masses)", "pl_bmasse", "质量"]),
            (["半径", "radius"], "半径", ["radius", "radius (km)", "pl_rade", "半径"]),
            (["轨道", "周期", "period", "orbital"], "轨道周期", ["period (days)", "orbital_period", "pl_orbper", "轨道周期"]),
            (["发现", "discover"], "发现信息", ["discovery method", "discovery_method", "发现方式", "disc_year", "发现年份"]),
            (["距离", "distance"], "距离", ["distance", "distance (ly)", "distance_pc", "距离", "sy_dist"]),
            (["体积", "volume"], "体积", ["volume", "volume_km3", "体积"]),
            (["直径", "diameter"], "直径", ["diameter", "diameter_km", "直径"]),
            (["温度", "temperature"], "温度", ["temperature", "temp", "surface_temperature", "温度"]),
        ]

        for triggers, label, keys in field_rules:
            if any(t in q for t in triggers):
                value = pick(keys)
                if value:
                    return f"{entity_name}的{label}为：{value}。"
        return ""

    def _extract_explicit_object_token(self, question: str) -> str | None:
        for p in (r"[\"'「」『』](.+?)[\"'「」『』]",):
            m = re.search(p, question)
            if m:
                value = str(m.group(1)).strip()
                if value:
                    return value
        for p in EXOPLANET_PATTERNS:
            m = re.search(p, question, flags=re.IGNORECASE)
            if m:
                return " ".join(m.group(0).split())
        return None

    def _extract_exoplanet_tokens(self, text: str) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for p in EXOPLANET_PATTERNS:
            for m in re.finditer(p, text, flags=re.IGNORECASE):
                token = " ".join(str(m.group(0)).split())
                if not token:
                    continue
                low = token.lower()
                if low in seen:
                    continue
                seen.add(low)
                out.append(token)
        return out

    def _is_exoplanet_token(self, value: str) -> bool:
        text = str(value or "")
        if not text:
            return False
        return any(re.search(p, text, flags=re.IGNORECASE) for p in EXOPLANET_PATTERNS)

    def _has_image_need(self, question: str) -> bool:
        q = question.lower()
        return any(k in q for k in ["图", "图片", "图像", "照片", "image", "photo", "similar image", "以图搜图", "以文搜图"])

    def _has_dynamic_need(self, question: str) -> bool:
        q = question.lower()
        return any(k in q for k in ["最新", "实时", "今天", "近期", "系外行星", "latest", "recent", "exoplanet", "nasa"])

    def _answer_builtin_fact(self, question: str) -> str | None:
        q = str(question or "").lower()
        if not q:
            return None

        if ("离地球最近" in q or "closest to earth" in q) and any(
            k in q for k in ["天体", "星体", "celestial", "object", "planet", "是什么", "which"]
        ):
            return (
                "离地球最近的天然天体是月球，平均距离约 38.4 万千米。\n\n"
                "补充说明：月地距离会在近地点和远地点之间变化。"
            )

        if ("火星" in q or "mars" in q) and ("体积" in q or "volume" in q):
            return (
                "火星体积约为 1.63×10^11 立方千米，约为地球体积的 15%。\n\n"
                "补充说明：火星平均半径约 3389.5 千米。"
            )

        if ("火星" in q or "mars" in q) and ("地球" in q or "earth" in q) and any(
            k in q for k in ["距离", "多远", "公里", "千米", "au", "天文单位"]
        ):
            return (
                "地球与火星之间的距离会随轨道位置变化，不是固定值。\n\n"
                "常用量级：最近约 5.4×10⁷ km（约 0.37 AU），最远约 4×10⁸ km（约 2.7 AU），"
                "平均可粗略记为约 2.25×10⁸ km（约 1.5 AU）。\n\n"
                "航天任务耗时取决于发射窗口与转移轨道，不能只用瞬时距离去除以速度。"
            )

        if (
            "太阳表面" in q
            or "photosphere" in q
            or "sun surface" in q
            or "surface temperature of the sun" in q
            or ("sun" in q and "surface" in q and "temperature" in q)
        ) and ("温度" in q or "temperature" in q):
            return (
                "太阳光球层（通常所说“太阳表面”）温度大约在 5500°C 左右（约 5778K）。\n\n"
                "补充说明：太阳外层大气（如日冕）温度可高得多。"
            )

        if ("太阳系最大" in q or "largest planet" in q) and any(k in q for k in ["行星", "planet", "是什么", "which"]):
            return "太阳系最大的行星是木星。"

        if ("地球" in q or "earth" in q) and ("直径" in q or "diameter" in q):
            return "地球平均直径约 12742 千米。"

        return None

    def _answer_identity(self, question: str) -> str | None:
        q = str(question or "").lower()
        if not q:
            return None
        hints = ["你是什么模型", "你是谁", "你能做什么", "what model are you", "who are you", "what can you do"]
        if any(x in q for x in hints):
            return (
                "我是 ASTRO 天文科普助手。"
                "我会先做问题分析，再结合本地知识库、知识图谱和图像检索来回答，必要时补充联网信息。"
            )
        return None

    def _looks_astronomy_question(self, question: str) -> bool:
        q = str(question or "").lower()
        if not q:
            return False
        keywords = [
            "天文",
            "宇宙",
            "星",
            "行星",
            "恒星",
            "银河",
            "黑洞",
            "星云",
            "彗星",
            "小行星",
            "太空",
            "太阳系",
            "地球",
            "月球",
            "火星",
            "木星",
            "金星",
            "水星",
            "土星",
            "天王星",
            "海王星",
            "exoplanet",
            "planet",
            "star",
            "galaxy",
            "nebula",
            "black hole",
            "nasa",
            "jwst",
        ]
        return any(k in q for k in keywords)

    def _result(
        self,
        answer: str,
        citations: list[str],
        graph_path: list[dict[str, str]],
        intent: str,
        entities_found: list[str],
        analysis: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "answer": answer.strip(),
            "citations": citations,
            "graph_path": graph_path,
            "intent": intent,
            "entities_found": entities_found,
            "analysis": analysis,
        }
