from __future__ import annotations

from typing import Any

from app.services.data_service import DataService
from app.services.graph_service import GraphService
from app.services.model3d_service import Model3DService
from app.services.retrieval_service import RetrievalService

GENERIC_FOCUS_TERMS = {
    "\u5929\u4f53",
    "\u536b\u661f",
    "\u884c\u661f",
    "\u6052\u661f",
    "\u661f\u4e91",
    "\u661f\u7cfb",
    "\u592a\u9633\u7cfb",
    "\u8f68\u9053",
    "\u89c2\u6d4b",
}

BUILTIN_ENTITY_CANDIDATES = [
    "\u592a\u9633",
    "\u6c34\u661f",
    "\u91d1\u661f",
    "\u5730\u7403",
    "\u6708\u7403",
    "\u706b\u661f",
    "\u6728\u661f",
    "\u571f\u661f",
    "\u5929\u738b\u661f",
    "\u6d77\u738b\u661f",
    "\u51a5\u738b\u661f",
    "\u9ed1\u6d1e",
    "\u94f6\u6cb3\u7cfb",
]

PLANET_NAMES = {
    "\u5730\u7403",
    "\u6c34\u661f",
    "\u91d1\u661f",
    "\u706b\u661f",
    "\u6728\u661f",
    "\u571f\u661f",
    "\u5929\u738b\u661f",
    "\u6d77\u738b\u661f",
    "\u51a5\u738b\u661f",
}

SMALL_BODY_NAMES = {"\u6708\u7403", "\u5f57\u661f", "\u5c0f\u884c\u661f"}
DEEP_SPACE_NAMES = {"\u9ed1\u6d1e", "\u94f6\u6cb3\u7cfb", "\u661f\u4e91"}


class ExploreService:
    def __init__(
        self,
        data_service: DataService,
        retrieval_service: RetrievalService,
        graph_service: GraphService,
        model3d_service: Model3DService,
    ) -> None:
        self._data_service = data_service
        self._retrieval_service = retrieval_service
        self._graph_service = graph_service
        self._model3d_service = model3d_service

    def query(self, query: str, image_hint: str | None = None) -> dict[str, Any]:
        raw = str(query or "").strip()
        if not raw:
            return {
                "query": "",
                "intent": "general",
                "headline": "",
                "note": "",
                "focus_entity": "",
                "focus_card": {},
                "related_images": [],
                "retrieval_note": "",
                "graph": {},
                "graph_highlights": [],
                "compare": {},
                "model3d": {},
                "follow_ups": [],
                "entry_points": [],
            }

        intent = self._infer_intent(raw, image_hint=image_hint)
        compare_entities = self._extract_entities(raw)
        focus_entity = self._resolve_focus_entity(raw, compare_entities)
        focus_query = focus_entity or raw

        related_images, retrieval_note = self._retrieval_service.hybrid_search(focus_query, image_hint, 4)
        related_images = [
            {
                "id": str(item.get("id", "")),
                "title": str(item.get("title", "")).strip() or focus_query,
                "score": float(item.get("score", 0.0) or 0.0),
                "source": str(item.get("source", "")).strip() or "knowledge",
                "snippet": str(item.get("snippet", "")).strip(),
                "image_url": item.get("image_url"),
            }
            for item in related_images
            if str(item.get("source", "")).strip().lower() != "mock"
        ]

        graph_payload = self._graph_service.visualization_subgraph(
            query=focus_query,
            max_nodes=90,
            max_links=140,
            max_hops=2 if intent in {"compare", "relation"} else 1,
            include_related=intent in {"compare", "relation"},
        )
        if int(graph_payload.get("rendered_nodes", 0) or 0) == 0 and focus_entity:
            graph_payload = self._fallback_builtin_graph(focus_entity, compare_entities=compare_entities)
        graph_highlights = self._build_graph_highlights(graph_payload, focus_entity or focus_query)

        compare_payload: dict[str, Any] = {}
        if intent == "compare" and len(compare_entities) >= 2:
            compare_payload = self._normalize_compare(
                self._graph_service.compare_entities(compare_entities[0], compare_entities[1])
            )

        model_payload = self._model3d_service.search(focus_query)
        focus_card = self._build_focus_card(focus_entity, related_images)
        follow_ups = self._build_follow_ups(
            raw,
            intent=intent,
            focus_entity=focus_entity,
            focus_card=focus_card,
            compare_entities=compare_entities,
        )

        headline = self._build_headline(raw, intent=intent, focus_entity=focus_entity, compare_payload=compare_payload)
        note = self._build_note(
            focus_entity=focus_entity or raw,
            image_count=len(related_images),
            graph_payload=graph_payload,
            model_payload=model_payload,
            compare_payload=compare_payload,
        )

        return {
            "query": raw,
            "intent": intent,
            "headline": headline,
            "note": note,
            "focus_entity": focus_entity,
            "focus_card": focus_card,
            "related_images": related_images,
            "retrieval_note": retrieval_note,
            "graph": {
                "focus": str(graph_payload.get("focus", focus_query)),
                "nodes": list(graph_payload.get("nodes", []))[:90],
                "links": list(graph_payload.get("links", []))[:140],
                "categories": list(graph_payload.get("categories", []))[:16],
                "seed_nodes": list(graph_payload.get("seed_nodes", []))[:4],
                "rendered_nodes": int(graph_payload.get("rendered_nodes", 0) or 0),
                "rendered_links": int(graph_payload.get("rendered_links", 0) or 0),
            },
            "graph_highlights": graph_highlights,
            "compare": compare_payload,
            "model3d": model_payload,
            "follow_ups": follow_ups,
            "entry_points": [
                {"label": "\u67e5\u770b\u76f8\u5173\u56fe\u7247", "path": "/app/image-search", "query": focus_query},
                {"label": "\u8fdb\u5165\u5173\u7cfb\u56fe\u8c31", "path": "/app/knowledge", "query": focus_query},
                {"label": "\u8fdb\u5165 3D \u6a21\u578b", "path": "/app/starfield", "query": focus_query},
            ],
        }

    def _infer_intent(self, query: str, image_hint: str | None = None) -> str:
        lowered = query.lower()
        if image_hint and str(image_hint).strip():
            return "visual"
        if any(token in lowered for token in ("\u5bf9\u6bd4", "\u6bd4\u8f83", "\u533a\u522b", "\u4e0d\u540c", "\u5dee\u5f02", "vs", " versus ")):
            return "compare"
        if any(token in lowered for token in ("\u5173\u7cfb", "\u8def\u5f84", "\u5173\u8054", "\u8054\u7cfb", "\u7cfb\u7edf")):
            return "relation"
        if any(token in lowered for token in ("3d", "\u4e09\u7ef4", "\u6a21\u578b", "\u8f68\u9053", "\u516c\u8f6c", "\u81ea\u8f6c", "\u661f\u56fe")):
            return "spatial"
        if any(token in lowered for token in ("\u56fe\u7247", "\u56fe\u50cf", "\u7167\u7247", "\u957f\u4ec0\u4e48\u6837", "\u770b\u8d77\u6765")):
            return "visual"
        if any(token in lowered for token in ("\u4e3a\u4ec0\u4e48", "\u5982\u4f55", "\u600e\u4e48", "\u539f\u7406", "\u610f\u5473\u7740\u4ec0\u4e48")):
            return "explain"
        return "fact"

    def _extract_entities(self, query: str) -> list[str]:
        lowered = str(query or "").strip().lower()
        if not lowered:
            return []

        seen: set[str] = set()
        found: list[str] = []
        for entity in self._data_service.export_entities():
            name = str(entity.get("name", "")).strip()
            if not name:
                continue
            marker = name.lower()
            if marker and marker in lowered and name not in seen:
                found.append(name)
                seen.add(name)
                if len(found) >= 4:
                    return found

        builtin_resolver = getattr(self._graph_service, "_builtin_entity", None)
        if callable(builtin_resolver):
            for item in BUILTIN_ENTITY_CANDIDATES:
                if item.lower() in lowered and item not in seen and builtin_resolver(item):
                    found.append(item)
                    seen.add(item)
                    if len(found) >= 4:
                        break
        return found

    def _resolve_focus_entity(self, query: str, compare_entities: list[str]) -> str:
        preferred = self._pick_focus_candidate(compare_entities)
        entity = self._data_service.find_best_entity_for_question(query)
        if entity:
            name = str(entity.get("name", "")).strip()
            if preferred and self._is_generic_focus(name) and not self._is_generic_focus(preferred):
                return preferred
            return name

        if preferred:
            return preferred

        model_guess = self._model3d_service.search(query)
        if model_guess.get("ok"):
            entity_payload = model_guess.get("entity", {})
            return str(entity_payload.get("name", "")).strip()

        query_lc = str(query or "").strip().lower()
        for entity_row in self._data_service.export_entities():
            name = str(entity_row.get("name", "")).strip()
            if name and (query_lc in name.lower() or name.lower() in query_lc):
                return name
        return ""

    def _pick_focus_candidate(self, names: list[str]) -> str:
        candidates = [str(name or "").strip() for name in names if str(name or "").strip()]
        if not candidates:
            return ""
        candidates.sort(key=lambda item: (1 if self._is_generic_focus(item) else 0, len(item), item))
        return candidates[0]

    def _is_generic_focus(self, value: str) -> bool:
        return str(value or "").strip() in GENERIC_FOCUS_TERMS

    def _build_focus_card(self, focus_entity: str, related_images: list[dict[str, Any]]) -> dict[str, Any]:
        entity = None
        if focus_entity:
            entity = self._data_service.find_best_entity_for_question(focus_entity)
        if entity is None and focus_entity:
            builtin_resolver = getattr(self._graph_service, "_builtin_entity", None)
            if callable(builtin_resolver):
                entity = builtin_resolver(focus_entity)
        if entity is None:
            return {}

        raw = entity.get("raw") if isinstance(entity.get("raw"), dict) else {}
        metrics = self._extract_metrics(raw)
        lead_image = next((item.get("image_url") for item in related_images if item.get("image_url")), None)
        return {
            "name": str(entity.get("name", "")).strip(),
            "category": str(entity.get("category", "")).strip() or "unknown",
            "description": self._trim_text(str(entity.get("description", "")).strip(), 180),
            "source_file": str(entity.get("source_file", "")).strip(),
            "lead_image_url": lead_image,
            "metrics": metrics,
        }

    def _extract_metrics(self, raw: dict[str, Any]) -> list[dict[str, str]]:
        metric_defs = [
            (("diameter_km", "diameter"), "\u76f4\u5f84", "km", "{:,.0f} km"),
            (("distance_from_earth_km",), "\u8ddd\u5730\u8ddd\u79bb", "km", "{:,.0f} km"),
            (("mass_earth",), "\u8d28\u91cf", "\u5730\u7403=1", "{:.3g} \u5730\u7403"),
            (("surface_temp_c", "temperature"), "\u8868\u9762\u6e29\u5ea6", "\u00b0C", "{:.0f}\u00b0C"),
            (("moon_count", "satellite_count"), "\u536b\u661f\u6570\u91cf", "\u9897", "{:.0f} \u9897"),
            (("orbital_period_days",), "\u516c\u8f6c\u5468\u671f", "\u5929", "{:.0f} \u5929"),
            (("discovery_year",), "\u53d1\u73b0\u5e74\u4efd", "", "{:.0f}"),
        ]
        metrics: list[dict[str, str]] = []
        for keys, label, unit, fmt in metric_defs:
            value = None
            for key in keys:
                candidate = raw.get(key)
                if candidate not in (None, ""):
                    value = candidate
                    break
            number = self._safe_float(value)
            if number is not None:
                metrics.append({"label": label, "value": fmt.format(number), "unit": unit})
            elif value not in (None, ""):
                metrics.append({"label": label, "value": str(value), "unit": unit})
            if len(metrics) >= 4:
                break
        return metrics

    def _build_graph_highlights(self, graph_payload: dict[str, Any], focus: str) -> list[str]:
        links = list(graph_payload.get("links", []))
        focus_name = str(focus or "").strip()
        highlights: list[str] = []
        seen: set[str] = set()
        for link in links:
            source = str(link.get("source", "")).strip()
            target = str(link.get("target", "")).strip()
            rel = str(link.get("name", "")).strip() or "RELATED_TO"
            if not source or not target:
                continue
            if focus_name and source != focus_name and target != focus_name:
                continue
            other = target if source == focus_name else source
            line = f"{focus_name or source} -[{rel}]-> {other}"
            if line not in seen:
                seen.add(line)
                highlights.append(line)
            if len(highlights) >= 6:
                break
        return highlights

    def _fallback_builtin_graph(self, focus_entity: str, compare_entities: list[str]) -> dict[str, Any]:
        builtin_resolver = getattr(self._graph_service, "_builtin_entity", None)
        builtin_path = getattr(self._graph_service, "_fallback_solar_path", None)
        if not callable(builtin_resolver):
            return {
                "focus": focus_entity,
                "nodes": [],
                "links": [],
                "categories": [],
                "seed_nodes": [],
                "rendered_nodes": 0,
                "rendered_links": 0,
            }

        focus_node = builtin_resolver(focus_entity)
        if not focus_node:
            return {
                "focus": focus_entity,
                "nodes": [],
                "links": [],
                "categories": [],
                "seed_nodes": [],
                "rendered_nodes": 0,
                "rendered_links": 0,
            }

        nodes: list[dict[str, Any]] = [
            {
                "id": focus_node["name"],
                "name": focus_node["name"],
                "category": str(focus_node.get("category", "unknown")),
                "value": 2,
                "is_seed": True,
            }
        ]
        links: list[dict[str, str]] = []

        related_target = compare_entities[1] if len(compare_entities) >= 2 else "\u592a\u9633"
        if callable(builtin_path):
            path = list(builtin_path(focus_node["name"], related_target))
            seen_nodes = {focus_node["name"]}
            for edge in path:
                src = str(edge.get("from", "")).strip()
                dst = str(edge.get("to", "")).strip()
                rel = str(edge.get("rel", "")).strip()
                if src and dst and rel:
                    links.append({"source": src, "target": dst, "name": rel})
                for item in (src, dst):
                    if item and item not in seen_nodes:
                        payload = builtin_resolver(item)
                        if payload:
                            nodes.append(
                                {
                                    "id": payload["name"],
                                    "name": payload["name"],
                                    "category": str(payload.get("category", "unknown")),
                                    "value": 1,
                                    "is_seed": False,
                                }
                            )
                            seen_nodes.add(item)

        categories = sorted({str(node.get("category", "unknown")) for node in nodes})
        return {
            "focus": focus_entity,
            "nodes": nodes,
            "links": links,
            "categories": categories,
            "seed_nodes": [focus_entity],
            "rendered_nodes": len(nodes),
            "rendered_links": len(links),
        }

    def _normalize_compare(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not payload or not payload.get("ok"):
            return {}
        metrics = []
        for item in list(payload.get("metrics", []))[:4]:
            label = str(item.get("label", "")).strip()
            unit = str(item.get("unit", "")).strip()
            metrics.append(
                {
                    "label": label,
                    "a": self._format_compare_value(item.get("a"), unit),
                    "b": self._format_compare_value(item.get("b"), unit),
                }
            )
        return {
            "ok": True,
            "summary": str(payload.get("summary", "")).strip(),
            "a": str(payload.get("a", {}).get("name", "")).strip(),
            "b": str(payload.get("b", {}).get("name", "")).strip(),
            "metrics": metrics,
        }

    def _format_compare_value(self, value: Any, unit: str) -> str:
        number = self._safe_float(value)
        if number is None:
            return str(value or "\u672a\u77e5")
        if unit == "km":
            return f"{number:,.0f} km"
        if unit == "\u9897":
            return f"{number:.0f} \u9897"
        if unit == "\u5929":
            return f"{number:.0f} \u5929"
        if unit == "\u00b0C":
            return f"{number:.0f}\u00b0C"
        if unit == "\u5730\u7403=1":
            return f"{number:.3g}"
        return f"{number:g}"

    def _build_follow_ups(
        self,
        query: str,
        intent: str,
        focus_entity: str,
        focus_card: dict[str, Any],
        compare_entities: list[str],
    ) -> list[str]:
        focus = focus_entity or str(focus_card.get("name", "")).strip() or "\u8fd9\u4e2a\u5929\u4f53"
        category = str(focus_card.get("category", "")).lower()
        candidates: list[str] = []

        if intent == "compare" and len(compare_entities) >= 2:
            a, b = compare_entities[:2]
            candidates.extend(
                [
                    f"{a} \u548c {b} \u5728\u5f62\u6210\u8fc7\u7a0b\u4e0a\u6709\u4ec0\u4e48\u4e0d\u540c\uff1f",
                    f"\u5982\u679c\u7528\u89c2\u6d4b\u4efb\u52a1\u7814\u7a76 {a} \u548c {b}\uff0c\u91cd\u70b9\u4f1a\u5206\u522b\u653e\u5728\u54ea\u91cc\uff1f",
                    f"{a} \u548c {b} \u5bf9\u7406\u89e3\u592a\u9633\u7cfb\u6f14\u5316\u6709\u4ec0\u4e48\u4ef7\u503c\uff1f",
                ]
            )
        elif "planet" in category or focus in PLANET_NAMES:
            candidates.extend(
                [
                    f"{focus} \u6700\u503c\u5f97\u7ee7\u7eed\u4e86\u89e3\u7684\u7ed3\u6784\u7279\u5f81\u662f\u4ec0\u4e48\uff1f",
                    f"{focus} \u548c\u5730\u7403\u76f8\u6bd4\u6700\u5927\u7684\u5dee\u5f02\u5728\u54ea\u91cc\uff1f",
                    f"\u5982\u679c\u4ece\u63a2\u6d4b\u4efb\u52a1\u89d2\u5ea6\u770b\uff0c\u7814\u7a76 {focus} \u6700\u96be\u7684\u5730\u65b9\u662f\u4ec0\u4e48\uff1f",
                ]
            )
        elif focus in SMALL_BODY_NAMES or "moon" in category or "small" in category:
            candidates.extend(
                [
                    f"{focus} \u5728\u592a\u9633\u7cfb\u6f14\u5316\u7814\u7a76\u4e2d\u626e\u6f14\u4ec0\u4e48\u89d2\u8272\uff1f",
                    f"\u5173\u4e8e {focus}\uff0c\u76ee\u524d\u8fd8\u6709\u54ea\u4e9b\u5173\u952e\u672a\u77e5\u95ee\u9898\uff1f",
                    f"\u5982\u679c\u7ee7\u7eed\u8ffd\u95ee {focus}\uff0c\u6700\u503c\u5f97\u770b\u7684\u89c2\u6d4b\u8bc1\u636e\u662f\u4ec0\u4e48\uff1f",
                ]
            )
        elif focus in DEEP_SPACE_NAMES or any(token in focus for token in ("\u9ed1\u6d1e", "\u661f\u7cfb", "\u661f\u4e91")):
            candidates.extend(
                [
                    f"{focus} \u662f\u901a\u8fc7\u4ec0\u4e48\u8bc1\u636e\u88ab\u786e\u8ba4\u6216\u7814\u7a76\u7684\uff1f",
                    f"{focus} \u548c\u5468\u56f4\u73af\u5883\u4e4b\u95f4\u6700\u91cd\u8981\u7684\u76f8\u4e92\u4f5c\u7528\u662f\u4ec0\u4e48\uff1f",
                    f"\u5f53\u524d\u5173\u4e8e {focus} \u7684\u524d\u6cbf\u7814\u7a76\u95ee\u9898\u6709\u54ea\u4e9b\uff1f",
                ]
            )
        else:
            candidates.extend(
                [
                    f"\u5982\u679c\u7ee7\u7eed\u8ffd\u95ee {focus}\uff0c\u6700\u503c\u5f97\u5148\u4e86\u89e3\u54ea\u4e00\u90e8\u5206\uff1f",
                    f"{focus} \u548c\u5176\u4ed6\u76f8\u8fd1\u5929\u4f53\u76f8\u6bd4\u6709\u4ec0\u4e48\u7279\u522b\u4e4b\u5904\uff1f",
                    f"\u6709\u54ea\u4e9b\u89c2\u6d4b\u4efb\u52a1\u6216\u6570\u636e\u80fd\u5e2e\u52a9\u7406\u89e3 {focus}\uff1f",
                ]
            )

        if "\u4e3a\u4ec0\u4e48" not in query and focus != "\u8fd9\u4e2a\u5929\u4f53":
            candidates.insert(0, f"\u4e3a\u4ec0\u4e48 {focus} \u4f1a\u5448\u73b0\u51fa\u73b0\u5728\u8fd9\u6837\u7684\u6027\u8d28\uff1f")

        deduped: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            text = str(item).strip()
            if text and text not in seen:
                seen.add(text)
                deduped.append(text)
            if len(deduped) >= 4:
                break
        return deduped

    def _build_headline(self, query: str, intent: str, focus_entity: str, compare_payload: dict[str, Any]) -> str:
        if compare_payload.get("ok"):
            return f"{compare_payload.get('a')} \u4e0e {compare_payload.get('b')} \u7684\u6838\u5fc3\u5dee\u5f02\u6881\u7406"
        focus = focus_entity or query
        if intent == "spatial":
            return f"\u56f4\u7ed5 {focus} \u7684\u4e09\u7ef4\u4e0e\u8f68\u9053\u63a2\u7d22"
        if intent == "relation":
            return f"\u56f4\u7ed5 {focus} \u7684\u5173\u7cfb\u7f51\u7edc\u4e0e\u77e5\u8bc6\u7ebf\u7d22"
        if intent == "visual":
            return f"\u56f4\u7ed5 {focus} \u7684\u56fe\u50cf\u4e0e\u89c2\u6d4b\u7ebf\u7d22"
        return f"\u56f4\u7ed5 {focus} \u7684\u5ef6\u5c55\u63a2\u7d22\u7ed3\u679c"

    def _build_note(
        self,
        focus_entity: str,
        image_count: int,
        graph_payload: dict[str, Any],
        model_payload: dict[str, Any],
        compare_payload: dict[str, Any],
    ) -> str:
        parts = [f"\u5df2\u4e3a\u201c{focus_entity}\u201d\u51c6\u5907\u5ef6\u5c55\u63a2\u7d22\u7ed3\u679c"]
        if image_count:
            parts.append(f"{image_count} \u5f20\u76f8\u5173\u56fe\u50cf")
        nodes = int(graph_payload.get("rendered_nodes", 0) or 0)
        links = int(graph_payload.get("rendered_links", 0) or 0)
        if nodes:
            parts.append(f"{nodes} \u4e2a\u56fe\u8c31\u8282\u70b9 / {links} \u6761\u5173\u7cfb")
        if model_payload.get("ok"):
            parts.append("1 \u4e2a\u53ef\u76f4\u63a5\u8fdb\u5165\u7684 3D \u6a21\u578b")
        if compare_payload.get("ok"):
            parts.append("1 \u7ec4\u5b9e\u4f53\u5bf9\u6bd4")
        return "\uff0c".join(parts) + "\u3002"

    def _trim_text(self, text: str, limit: int) -> str:
        raw = str(text or "").strip()
        if len(raw) <= limit:
            return raw
        return raw[: max(0, limit - 1)].rstrip() + "\u2026"

    def _safe_float(self, value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
