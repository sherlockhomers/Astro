from __future__ import annotations

import hashlib
import time
from collections import OrderedDict, deque
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import settings
from app.services.data_service import DataService

CN_SOLAR = "\u592a\u9633"
CN_MERCURY = "\u6c34\u661f"
CN_VENUS = "\u91d1\u661f"
CN_EARTH = "\u5730\u7403"
CN_MOON = "\u6708\u7403"
CN_MARS = "\u706b\u661f"
CN_JUPITER = "\u6728\u661f"
CN_SATURN = "\u571f\u661f"
CN_URANUS = "\u5929\u738b\u661f"
CN_NEPTUNE = "\u6d77\u738b\u661f"
CN_PLUTO = "\u51a5\u738b\u661f"
CN_SOLAR_CATEGORY = "\u592a\u9633\u4e0e\u592a\u9633\u7cfb"

SOLAR_SYSTEM_FACTS: dict[str, dict[str, Any]] = {
    CN_SOLAR: {
        "diameter_km": 1392700.0,
        "distance_from_earth_km": 149600000.0,
        "mass_earth": 332946.0,
        "surface_temp_c": 5505.0,
        "moon_count": 0.0,
        "orbital_period_days": 0.0,
        "category": CN_SOLAR_CATEGORY,
    },
    CN_MERCURY: {
        "diameter_km": 4879.0,
        "distance_from_earth_km": 91691000.0,
        "mass_earth": 0.055,
        "surface_temp_c": 167.0,
        "moon_count": 0.0,
        "orbital_period_days": 88.0,
        "category": CN_SOLAR_CATEGORY,
    },
    CN_VENUS: {
        "diameter_km": 12104.0,
        "distance_from_earth_km": 41400000.0,
        "mass_earth": 0.815,
        "surface_temp_c": 464.0,
        "moon_count": 0.0,
        "orbital_period_days": 225.0,
        "category": CN_SOLAR_CATEGORY,
    },
    CN_EARTH: {
        "diameter_km": 12742.0,
        "distance_from_earth_km": 0.0,
        "mass_earth": 1.0,
        "surface_temp_c": 15.0,
        "moon_count": 1.0,
        "orbital_period_days": 365.25,
        "category": CN_SOLAR_CATEGORY,
    },
    CN_MOON: {
        "diameter_km": 3474.0,
        "distance_from_earth_km": 384400.0,
        "mass_earth": 0.0123,
        "surface_temp_c": -20.0,
        "moon_count": 0.0,
        "orbital_period_days": 27.3,
        "category": CN_SOLAR_CATEGORY,
    },
    CN_MARS: {
        "diameter_km": 6779.0,
        "distance_from_earth_km": 78300000.0,
        "mass_earth": 0.107,
        "surface_temp_c": -63.0,
        "moon_count": 2.0,
        "orbital_period_days": 687.0,
        "category": CN_SOLAR_CATEGORY,
    },
    CN_JUPITER: {
        "diameter_km": 139820.0,
        "distance_from_earth_km": 628730000.0,
        "mass_earth": 317.8,
        "surface_temp_c": -145.0,
        "moon_count": 95.0,
        "orbital_period_days": 4333.0,
        "category": CN_SOLAR_CATEGORY,
    },
    CN_SATURN: {
        "diameter_km": 116460.0,
        "distance_from_earth_km": 1275000000.0,
        "mass_earth": 95.2,
        "surface_temp_c": -178.0,
        "moon_count": 146.0,
        "orbital_period_days": 10759.0,
        "category": CN_SOLAR_CATEGORY,
    },
    CN_URANUS: {
        "diameter_km": 50724.0,
        "distance_from_earth_km": 2723950000.0,
        "mass_earth": 14.5,
        "surface_temp_c": -224.0,
        "moon_count": 28.0,
        "orbital_period_days": 30685.0,
        "category": CN_SOLAR_CATEGORY,
    },
    CN_NEPTUNE: {
        "diameter_km": 49244.0,
        "distance_from_earth_km": 4351400000.0,
        "mass_earth": 17.1,
        "surface_temp_c": -218.0,
        "moon_count": 16.0,
        "orbital_period_days": 60190.0,
        "category": CN_SOLAR_CATEGORY,
    },
    CN_PLUTO: {
        "diameter_km": 2376.0,
        "distance_from_earth_km": 5869000000.0,
        "mass_earth": 0.0022,
        "surface_temp_c": -229.0,
        "moon_count": 5.0,
        "orbital_period_days": 90560.0,
        "category": CN_SOLAR_CATEGORY,
    },
}

SOLAR_SYSTEM_ALIAS: dict[str, str] = {
    "sun": CN_SOLAR,
    "mercury": CN_MERCURY,
    "venus": CN_VENUS,
    "earth": CN_EARTH,
    "moon": CN_MOON,
    "mars": CN_MARS,
    "jupiter": CN_JUPITER,
    "saturn": CN_SATURN,
    "uranus": CN_URANUS,
    "neptune": CN_NEPTUNE,
    "pluto": CN_PLUTO,
    "sol": CN_SOLAR,
    "terra": CN_EARTH,
    "luna": CN_MOON,
}

# 内置真实天文坐标（赤经 RA 小时:分:秒, 赤纬 Dec 度:分:秒）
# 用于 starfield_points 渲染时提供可验证的天文坐标数据
# RA 范围 0-24h, Dec 范围 -90 到 +90 度
BUILTIN_STARFIELD_CATALOG: dict[str, tuple[float, float]] = {
    # 太阳系行星（简化坐标，真实场景需用星历表计算）
    CN_SOLAR: (0.0, 0.0),
    CN_MERCURY: (4.5, 21.0),
    CN_VENUS: (8.2, 15.0),
    CN_EARTH: (14.0, -6.0),
    CN_MOON: (14.1, -5.8),
    CN_MARS: (16.8, -23.0),
    CN_JUPITER: (10.5, 7.0),
    CN_SATURN: (22.1, -12.0),
    CN_URANUS: (3.2, 17.0),
    CN_NEPTUNE: (23.9, -3.0),
    CN_PLUTO: (19.5, -22.0),
    # 亮星（真实 IAU 命名坐标，数据来源：SIMBAD/Astronomical Constants）
    "Sirius": (6.752, -16.716),
    "Canopus": (6.399, -52.696),
    "Alpha Centauri": (14.660, -60.835),
    "Arcturus": (14.261, 19.182),
    "Vega": (18.616, 38.784),
    "Capella": (5.278, 45.998),
    "Rigel": (5.242, -8.202),
    "Betelgeuse": (5.920, 7.407),
    "Altair": (19.846, 8.868),
    "Aldebaran": (4.599, 16.509),
    "Antares": (16.490, -26.432),
    "Spica": (13.420, -11.161),
    "Pollux": (7.755, 28.026),
    "Fomalhaut": (22.961, -29.622),
    "Deneb": (20.690, 45.280),
    "Regulus": (10.139, 11.967),
    "Procyon": (7.655, 5.225),
    "Achernar": (1.629, -57.237),
    "Hadar": (14.064, -60.373),
    "Acrux": (12.443, -63.099),
    "Mimosa": (12.795, -59.689),
    "Diphda": (0.726, -17.987),
    "Alioth": (12.900, 55.960),
    "Avior": (8.376, -52.674),
    "Alkaid": (13.792, 49.313),
    "Dubhe": (11.062, 61.751),
    "Shaula": (17.560, -37.104),
    "Bellatrix": (5.419, 6.350),
    "Mirzam": (6.377, -17.957),
    "Alnilam": (5.603, -1.202),
    "Saiph": (5.796, -9.670),
    "Alnair": (22.139, -46.961),
    "Menkent": (14.106, -36.370),
    "Atria": (16.813, -69.027),
    "Kaus Australis": (18.402, -34.384),
    "Alpheratz": (0.140, 29.091),
    # 深空天体（著名星云/星系）
    "M31": (0.712, 41.277),
    "M42": (5.588, -5.391),
    "M45": (3.791, 24.117),
    "M51": (13.498, 47.195),
    "M81": (9.926, 69.066),
    "M87": (12.514, 12.390),
    "M104": (12.667, -11.623),
    "NGC 224": (0.712, 41.277),
    "NGC 1977": (5.588, -4.900),
    "NGC 869": (2.322, 57.132),
    "NGC 884": (2.343, 57.151),
}

ASTRO_TIMELINE_EVENTS: list[dict[str, Any]] = [
    {
        "year": 1543,
        "name": "哥白尼日心说出版",
        "category": "天文学史",
        "event_type": "theory",
        "importance": 10,
        "description": "《天体运行论》发表，现代天文学的核心转折点之一。",
    },
    {
        "year": 1609,
        "name": "伽利略开始望远镜观天",
        "category": "观测技术",
        "event_type": "observation",
        "importance": 9,
        "description": "望远镜被系统用于天文观测，直接推动月面、木星卫星等发现。",
    },
    {
        "year": 1687,
        "name": "牛顿《自然哲学的数学原理》出版",
        "category": "天体力学",
        "event_type": "theory",
        "importance": 9,
        "description": "万有引力和经典力学体系确立，为轨道与天体运动解释提供统一框架。",
    },
    {
        "year": 1915,
        "name": "广义相对论提出",
        "category": "相对论天体物理",
        "event_type": "theory",
        "importance": 10,
        "description": "爱因斯坦建立广义相对论，为黑洞、引力透镜和宇宙学奠定理论基础。",
    },
    {
        "year": 1929,
        "name": "哈勃发现宇宙膨胀",
        "category": "宇宙学",
        "event_type": "discovery",
        "importance": 10,
        "description": "星系退行速度与距离相关，现代宇宙学进入观测时代。",
    },
    {
        "year": 1965,
        "name": "宇宙微波背景辐射被发现",
        "category": "宇宙学",
        "event_type": "discovery",
        "importance": 10,
        "description": "大爆炸宇宙学获得关键观测证据。",
    },
    {
        "year": 1990,
        "name": "哈勃空间望远镜升空",
        "category": "空间望远镜",
        "event_type": "mission",
        "importance": 9,
        "description": "高分辨率空间观测极大改变了公众和科学界对宇宙的认知。",
    },
    {
        "year": 1995,
        "name": "首颗类太阳恒星系外行星确认",
        "category": "系外行星",
        "event_type": "discovery",
        "importance": 10,
        "description": "51 Pegasi b 的确认开启系外行星观测时代。",
    },
    {
        "year": 2015,
        "name": "LIGO 首次直接探测到引力波",
        "category": "引力波天文学",
        "event_type": "discovery",
        "importance": 10,
        "description": "双黑洞并合信号被探测到，打开全新的观测窗口。",
    },
    {
        "year": 2019,
        "name": "首张黑洞照片公布",
        "category": "黑洞观测",
        "event_type": "imaging",
        "importance": 10,
        "description": "事件视界望远镜发布 M87* 影像，黑洞研究进入可视化时代。",
    },
    {
        "year": 2022,
        "name": "JWST 发布首批科学图像",
        "category": "空间望远镜",
        "event_type": "mission",
        "importance": 10,
        "description": "詹姆斯·韦布空间望远镜开始提供高质量红外观测数据。",
    },
]


class GraphService:
    def __init__(self, data_service: DataService) -> None:
        self._data_service = data_service
        self._graph_ready = False
        self._last_build_task_id: str | None = None
        self._last_build_at: str | None = None
        self._nodes_count = 0
        self._relations_count = 0
        self._relations: list[dict[str, str]] = []
        self._viz_cache: dict[tuple[int, int, int], dict[str, Any]] = {}
        self._subgraph_cache: OrderedDict[tuple[int, str, int, int, int, int], dict[str, Any]] = OrderedDict()
        # 邻接表缓存：避免每次 find_path 重新构建
        self._adjacency: dict[str, list[tuple[str, str]]] | None = None
        # 实体名解析缓存：避免每次 _resolve_entity_name 重新遍历
        self._resolve_cache: dict[str, str] = {}
        self._data_revision_cache: int = -1

    def build_graph(
        self, csv_root: str, categories: list[str], write_neo4j: bool = False
    ) -> tuple[bool, str, str]:
        task_id = f"graph-build-{uuid4().hex[:8]}"
        self._last_build_task_id = task_id
        self._last_build_at = datetime.utcnow().isoformat()

        load_result = self._data_service.load_data_source(csv_root, categories)
        entities, relations = self._recompute_graph()

        message = (
            f"图谱构建完成（内存图）：nodes={len(entities)}, relations={len(relations)}。"
            f" 数据源：{load_result['source_root']}"
        )
        if write_neo4j:
            ok, neo4j_msg = self._write_to_neo4j(entities, relations)
            message = f"{message} Neo4j写入：{'成功' if ok else '失败'}，{neo4j_msg}"
        return True, message, task_id

    def rebuild_from_loaded_entities(self, write_neo4j: bool = False) -> tuple[bool, str, str]:
        """
        Rebuild graph from currently loaded entities only.
        Useful for dynamic fact upsert without reloading csv/xlsx source.
        """
        task_id = f"graph-refresh-{uuid4().hex[:8]}"
        self._last_build_task_id = task_id
        self._last_build_at = datetime.utcnow().isoformat()
        entities, relations = self._recompute_graph()
        message = f"图谱已按当前实体刷新：nodes={len(entities)}, relations={len(relations)}"
        if write_neo4j:
            ok, neo4j_msg = self._write_to_neo4j(entities, relations)
            message = f"{message} Neo4j写入：{'成功' if ok else '失败'}，{neo4j_msg}"
        return True, message, task_id

    def status(self) -> dict[str, Any]:
        return {
            "graph_ready": self._graph_ready,
            "last_build_task_id": self._last_build_task_id,
            "last_build_at": self._last_build_at,
            "nodes_count": self._nodes_count,
            "relations_count": self._relations_count,
        }

    def preview_paths(self, top_k: int = 20) -> list[dict[str, str]]:
        return self._relations[:top_k]

    def find_path(self, source_name: str, target_name: str, max_hops: int = 3) -> list[dict[str, str]]:
        source = self._resolve_entity_name(source_name)
        target = self._resolve_entity_name(target_name)
        if not source or not target or source == target:
            return []

        adjacency = self._build_adjacency()

        queue: deque[tuple[str, list[dict[str, str]]]] = deque()
        queue.append((source, []))
        visited = {source}

        while queue:
            node, path = queue.popleft()
            if len(path) >= max_hops:
                continue
            for nxt, rel_type in adjacency.get(node, []):
                if nxt in visited:
                    continue
                step = {"from": node, "rel": rel_type, "to": nxt}
                next_path = path + [step]
                if nxt == target:
                    return next_path
                visited.add(nxt)
                queue.append((nxt, next_path))
        return self._fallback_solar_path(source, target)

    def find_paths(
        self,
        source_name: str,
        target_name: str,
        max_hops: int = 4,
        max_paths: int = 5,
    ) -> list[list[dict[str, str]]]:
        source = self._resolve_entity_name(source_name)
        target = self._resolve_entity_name(target_name)
        max_hops = max(1, min(int(max_hops), 7))
        max_paths = max(1, min(int(max_paths), 12))
        if not source or not target or source == target:
            return []

        adjacency = self._build_adjacency()

        def collect_paths(allow_reverse_related: bool) -> list[list[dict[str, str]]]:
            queue: deque[tuple[str, list[dict[str, str]], set[str]]] = deque()
            queue.append((source, [], {source}))
            paths: list[list[dict[str, str]]] = []
            seen_signatures: set[tuple[str, ...]] = set()

            while queue and len(paths) < max_paths:
                node, path, visited = queue.popleft()
                if len(path) >= max_hops:
                    continue
                for nxt, rel_type in adjacency.get(node, []):
                    if not allow_reverse_related and rel_type == "REVERSE_RELATED_TO":
                        continue
                    if nxt in visited:
                        continue
                    step = {"from": node, "rel": rel_type, "to": nxt}
                    next_path = path + [step]
                    if nxt == target:
                        signature = tuple([source] + [s["to"] for s in next_path])
                        if signature not in seen_signatures:
                            seen_signatures.add(signature)
                            paths.append(next_path)
                        if len(paths) >= max_paths:
                            break
                        continue
                    next_visited = set(visited)
                    next_visited.add(nxt)
                    queue.append((nxt, next_path, next_visited))
            return paths

        paths = collect_paths(allow_reverse_related=False)
        if not paths:
            paths = collect_paths(allow_reverse_related=True)

        if paths:
            relation_priority = {
                "ORBITS": 0,
                "ORBITS_WITHIN": 0,
                "LOCATED_IN": 1,
                "INSTANCE_OF": 1,
                "DISCOVERED_VIA": 1,
                "OPERATED_BY": 1,
                "SIMILAR_TO": 2,
                "RELATED_TO": 3,
                "REVERSE_RELATED_TO": 5,
            }

            def score(path: list[dict[str, str]]) -> tuple[int, int, str]:
                rel_score = sum(relation_priority.get(str(s.get("rel", "")), 4) for s in path)
                signature = "->".join([x["from"] for x in path] + [path[-1]["to"]]) if path else ""
                return (len(path), rel_score, signature)

            paths.sort(key=score)
            return paths[:max_paths]

        fallback = self._fallback_solar_path(source, target)
        return [fallback] if fallback else []

    def visualization_graph(self, max_nodes: int = 220, max_links: int = 900) -> dict[str, Any]:
        max_nodes = max(80, min(int(max_nodes), 2200))
        max_links = max(200, min(int(max_links), 15000))
        cache_key = (int(self._data_service.revision), max_nodes, max_links)
        hit = self._viz_cache.get(cache_key)
        if hit is not None:
            return hit

        entity_map: dict[str, dict[str, Any]] = {}
        for e in self._collect_graph_entities():
            name = str(e.get("name", "")).strip()
            if not name:
                continue
            old = entity_map.get(name)
            if old is None:
                entity_map[name] = e
                continue
            old_desc = len(str(old.get("description", "")))
            new_desc = len(str(e.get("description", "")))
            old_raw = len((old.get("raw") or {}).keys()) if isinstance(old.get("raw"), dict) else 0
            new_raw = len((e.get("raw") or {}).keys()) if isinstance(e.get("raw"), dict) else 0
            if (new_raw, new_desc) > (old_raw, old_desc):
                entity_map[name] = e

        degree: dict[str, int] = {}
        for rel in self._relations:
            src = str(rel.get("from", "")).strip()
            dst = str(rel.get("to", "")).strip()
            if src:
                degree[src] = degree.get(src, 0) + 1
            if dst:
                degree[dst] = degree.get(dst, 0) + 1

        ranked_entities = sorted(
            entity_map.values(),
            key=lambda e: (
                degree.get(str(e.get("name", "")).strip(), 0),
                len(str(e.get("description", ""))),
            ),
            reverse=True,
        )
        entities = ranked_entities[:max_nodes]
        nodes = [
            {
                "id": e["name"],
                "name": e["name"],
                "category": e.get("category", "unknown"),
                "value": max(1, min(degree.get(str(e.get("name", "")).strip(), 0), 20)),
            }
            for e in entities
            if e.get("name")
        ]
        node_names = {n["name"] for n in nodes}
        links: list[dict[str, str]] = []
        seen_links: set[tuple[str, str, str]] = set()
        for rel in self._relations:
            if rel["from"] in node_names and rel["to"] in node_names:
                key = (str(rel["from"]), str(rel["to"]), str(rel["rel"]))
                if key in seen_links:
                    continue
                seen_links.add(key)
                links.append({"source": rel["from"], "target": rel["to"], "name": rel["rel"]})
                if len(links) >= max_links:
                    break
        categories = sorted({n["category"] for n in nodes})
        payload = {
            "nodes": nodes,
            "links": links,
            "categories": categories,
            "total_nodes": self._nodes_count,
            "total_links": self._relations_count,
            "rendered_nodes": len(nodes),
            "rendered_links": len(links),
        }
        self._viz_cache[cache_key] = payload
        return payload

    def visualization_subgraph(
        self,
        query: str,
        max_nodes: int = 600,
        max_links: int = 4000,
        max_hops: int = 1,
        include_related: bool = False,
    ) -> dict[str, Any]:
        query = str(query or "").strip()
        max_nodes = max(80, min(int(max_nodes), 2200))
        max_links = max(200, min(int(max_links), 15000))
        max_hops = max(1, min(int(max_hops), 3))
        cache_key = (
            int(self._data_service.revision),
            query.lower(),
            int(max_nodes),
            int(max_links),
            int(max_hops),
            1 if include_related else 0,
        )
        cached = self._subgraph_cache.get(cache_key)
        if cached is not None:
            self._subgraph_cache.move_to_end(cache_key)
            return cached
        if not query:
            payload = self.visualization_graph(max_nodes=max_nodes, max_links=max_links)
            payload["focus"] = ""
            payload["seed_nodes"] = []
            return payload

        entities = self._collect_graph_entities()
        entity_map = {
            str(e.get("name", "")).strip(): e
            for e in entities
            if str(e.get("name", "")).strip()
        }
        names = list(entity_map.keys())
        lower_map = {n.lower(): n for n in names}

        seeds: list[str] = []
        resolved = self._resolve_entity_name(query)
        if resolved and resolved in entity_map:
            seeds.append(resolved)
        ql = query.lower()
        if not seeds:
            exact = lower_map.get(ql)
            if exact:
                seeds.append(exact)
        if not seeds:
            contains = [n for n in names if ql in n.lower() or n.lower() in ql]
            contains.sort(key=lambda n: (0 if n.lower().startswith(ql) else 1, abs(len(n) - len(query))))
            seeds.extend(contains[:6])
        # Keep subgraph focus tight: default to one best-matching seed entity.
        seeds = [s for s in seeds if s in entity_map][:1]
        if not seeds:
            return {
                "nodes": [],
                "links": [],
                "categories": [],
                "total_nodes": self._nodes_count,
                "total_links": self._relations_count,
                "rendered_nodes": 0,
                "rendered_links": 0,
                "focus": query,
                "seed_nodes": [],
            }

        strong_rel = {
            "ORBITS",
            "ORBITS_WITHIN",
            "LOCATED_IN",
            "INSTANCE_OF",
            "DISCOVERED_VIA",
            "OPERATED_BY",
            "SIMILAR_TO",
            "ORBIT_TYPE",
            "REVERSE_ORBITS",
            "REVERSE_ORBITS_WITHIN",
            "REVERSE_LOCATED_IN",
            "REVERSE_INSTANCE_OF",
            "REVERSE_DISCOVERED_VIA",
            "REVERSE_OPERATED_BY",
            "REVERSE_SIMILAR_TO",
            "REVERSE_ORBIT_TYPE",
        }
        weak_rel = {"RELATED_TO", "REVERSE_RELATED_TO"}
        allowed_rel = set(strong_rel)
        if include_related:
            allowed_rel.update(weak_rel)

        relation_priority = {
            "ORBITS": 0,
            "ORBITS_WITHIN": 0,
            "LOCATED_IN": 1,
            "INSTANCE_OF": 1,
            "DISCOVERED_VIA": 1,
            "OPERATED_BY": 1,
            "SIMILAR_TO": 2,
            "ORBIT_TYPE": 2,
            "RELATED_TO": 4,
            "REVERSE_RELATED_TO": 5,
        }

        seed_set = set(seeds)
        selected_nodes: set[str] = set(seeds)
        selected_links: list[dict[str, str]] = []
        seen_link_keys: set[tuple[str, str, str]] = set()

        def add_link(src: str, rel_name: str, dst: str) -> None:
            key = (src, rel_name, dst)
            if key in seen_link_keys:
                return
            if src not in entity_map and self._builtin_entity(src) is None:
                return
            if dst not in entity_map and self._builtin_entity(dst) is None:
                return
            seen_link_keys.add(key)
            selected_links.append({"source": src, "target": dst, "name": rel_name})
            selected_nodes.add(src)
            selected_nodes.add(dst)

        # 1-hop around seed entity (exact neighborhood).
        first_hop_nodes: set[str] = set()
        candidate_relations = []
        for rel in self._relations:
            src = str(rel.get("from", "")).strip()
            dst = str(rel.get("to", "")).strip()
            rel_name = str(rel.get("rel", "")).strip()
            if rel_name not in allowed_rel:
                continue
            if src in seed_set or dst in seed_set:
                score = relation_priority.get(rel_name, 9)
                candidate_relations.append((score, rel_name, src, dst))

        candidate_relations.sort(key=lambda x: (x[0], x[2], x[3]))
        for _, rel_name, src, dst in candidate_relations:
            if len(selected_links) >= max_links or len(selected_nodes) >= max_nodes:
                break
            add_link(src, rel_name, dst)
            if src not in seed_set:
                first_hop_nodes.add(src)
            if dst not in seed_set:
                first_hop_nodes.add(dst)

        # If strict strong-relation mode yields no neighborhood, fall back to weak
        # RELATED_TO edges around seed to avoid returning isolated single nodes.
        if not include_related and not selected_links:
            weak_candidates = []
            for rel in self._relations:
                src = str(rel.get("from", "")).strip()
                dst = str(rel.get("to", "")).strip()
                rel_name = str(rel.get("rel", "")).strip()
                if rel_name not in weak_rel:
                    continue
                if src in seed_set or dst in seed_set:
                    other = dst if src in seed_set else src
                    lexical = 0 if query.lower() in other.lower() else 1
                    weak_candidates.append((lexical, other, rel_name, src, dst))

            weak_candidates.sort(key=lambda x: (x[0], x[1]))
            weak_limit = min(max_links, 600)
            for _, _, rel_name, src, dst in weak_candidates:
                if len(selected_links) >= weak_limit or len(selected_nodes) >= max_nodes:
                    break
                add_link(src, rel_name, dst)
                if src not in seed_set:
                    first_hop_nodes.add(src)
                if dst not in seed_set:
                    first_hop_nodes.add(dst)

        # Optional 2-hop expansion from the first neighborhood, still relation-filtered.
        if max_hops >= 2 and first_hop_nodes and len(selected_links) < max_links and len(selected_nodes) < max_nodes:
            second_candidates = []
            first_set = set(first_hop_nodes)
            for rel in self._relations:
                src = str(rel.get("from", "")).strip()
                dst = str(rel.get("to", "")).strip()
                rel_name = str(rel.get("rel", "")).strip()
                if rel_name not in allowed_rel:
                    continue
                if src in first_set or dst in first_set:
                    if src in seed_set or dst in seed_set:
                        continue
                    score = relation_priority.get(rel_name, 9)
                    second_candidates.append((score, rel_name, src, dst))
            second_candidates.sort(key=lambda x: (x[0], x[2], x[3]))
            for _, rel_name, src, dst in second_candidates:
                if len(selected_links) >= max_links or len(selected_nodes) >= max_nodes:
                    break
                add_link(src, rel_name, dst)

        ranked_names = sorted(
            list(selected_nodes),
            key=lambda n: (
                0 if n in seed_set else 1,
                0 if query.lower() in n.lower() else 1,
                n,
            ),
        )[:max_nodes]
        selected = set(ranked_names)
        selected_links = [l for l in selected_links if l["source"] in selected and l["target"] in selected][:max_links]

        nodes: list[dict[str, Any]] = []
        for name in ranked_names:
            e = entity_map.get(name) or self._builtin_entity(name)
            if not e:
                continue
            nodes.append(
                {
                    "id": name,
                    "name": name,
                    "category": str(e.get("category", "unknown") or "unknown"),
                    "value": max(
                        2 if name in seed_set else 1,
                        min(
                            sum(
                                1
                                for link in selected_links
                                if link["source"] == name or link["target"] == name
                            ),
                            20,
                        ),
                    ),
                    "is_seed": name in seed_set,
                }
            )

        categories = sorted({str(n.get("category", "unknown")) for n in nodes})
        payload = {
            "nodes": nodes,
            "links": selected_links,
            "categories": categories,
            "total_nodes": self._nodes_count,
            "total_links": self._relations_count,
            "rendered_nodes": len(nodes),
            "rendered_links": len(selected_links),
            "focus": query,
            "seed_nodes": seeds,
        }
        self._subgraph_cache_put(cache_key, payload)
        return payload

    def _subgraph_cache_put(self, cache_key: tuple[int, str, int, int, int, int], payload: dict[str, Any]) -> None:
        self._subgraph_cache[cache_key] = payload
        self._subgraph_cache.move_to_end(cache_key)
        while len(self._subgraph_cache) > 64:
            self._subgraph_cache.popitem(last=False)

    def compare_entities(self, name_a: str, name_b: str) -> dict[str, Any]:
        entity_map = {e["name"]: e for e in self._collect_graph_entities() if e.get("name")}
        resolved_a = self._resolve_entity_name(name_a)
        resolved_b = self._resolve_entity_name(name_b)
        a = entity_map.get(resolved_a) or self._builtin_entity(resolved_a)
        b = entity_map.get(resolved_b) or self._builtin_entity(resolved_b)
        if a is None or b is None:
            return {"ok": False, "message": "未找到可比较的实体，请先确认名称是否存在于当前知识库。"}

        metric_defs = [
            ("diameter_km", "直径", "km"),
            ("distance_from_earth_km", "距地距离", "km"),
            ("mass_earth", "质量", "地球=1"),
            ("surface_temp_c", "表面温度", "°C"),
            ("moon_count", "卫星数量", "颗"),
            ("orbital_period_days", "公转周期", "天"),
        ]
        metrics: list[dict[str, Any]] = []
        for key, label, unit in metric_defs:
            metrics.append(
                {
                    "key": key,
                    "label": label,
                    "unit": unit,
                    "a": self._entity_metric(a, key),
                    "b": self._entity_metric(b, key),
                }
            )

        summary: list[str] = []
        diameter = next((m for m in metrics if m["key"] == "diameter_km"), None)
        distance = next((m for m in metrics if m["key"] == "distance_from_earth_km"), None)
        moon_count = next((m for m in metrics if m["key"] == "moon_count"), None)
        if diameter and isinstance(diameter["a"], (int, float)) and isinstance(diameter["b"], (int, float)):
            if float(diameter["a"]) > float(diameter["b"]):
                summary.append(f"{a['name']} 的体量更大")
            elif float(diameter["b"]) > float(diameter["a"]):
                summary.append(f"{b['name']} 的体量更大")
        if distance and isinstance(distance["a"], (int, float)) and isinstance(distance["b"], (int, float)):
            if float(distance["a"]) < float(distance["b"]):
                summary.append(f"{a['name']} 离地球更近")
            elif float(distance["b"]) < float(distance["a"]):
                summary.append(f"{b['name']} 离地球更近")
        if moon_count and isinstance(moon_count["a"], (int, float)) and isinstance(moon_count["b"], (int, float)):
            if float(moon_count["a"]) != float(moon_count["b"]):
                leader = a["name"] if float(moon_count["a"]) > float(moon_count["b"]) else b["name"]
                summary.append(f"{leader} 的天然卫星系统更丰富")

        return {
            "ok": True,
            "a": {"name": a["name"], **{m["key"]: m["a"] for m in metrics}},
            "b": {"name": b["name"], **{m["key"]: m["b"] for m in metrics}},
            "metrics": metrics,
            "summary": "；".join(summary),
        }

    def _build_adjacency(self) -> dict[str, list[tuple[str, str]]]:
        if self._adjacency is not None:
            return self._adjacency
        adjacency: dict[str, list[tuple[str, str]]] = {}
        for rel in self._relations:
            src = rel["from"]
            dst = rel["to"]
            rtype = rel["rel"]
            adjacency.setdefault(src, []).append((dst, rtype))
            adjacency.setdefault(dst, []).append((src, f"REVERSE_{rtype}"))
        self._adjacency = adjacency
        return adjacency

    def _resolve_entity_name(self, name: str) -> str:
        raw = str(name or "").strip()
        if not raw:
            return ""
        # 数据变更时清除缓存
        if self._data_revision_cache != self._data_service.revision:
            self._resolve_cache.clear()
            self._data_revision_cache = self._data_service.revision
        cache_key = raw.lower()
        if cache_key in self._resolve_cache:
            return self._resolve_cache[cache_key]

        alias = dict(SOLAR_SYSTEM_ALIAS)
        for zh_name in SOLAR_SYSTEM_FACTS:
            alias[zh_name.lower()] = zh_name

        entity_names = [
            str(e.get("name", "")).strip()
            for e in self._collect_graph_entities()
            if str(e.get("name", "")).strip()
        ]
        lower_map = {n.lower(): n for n in entity_names}

        result = raw
        direct = lower_map.get(raw.lower())
        if direct:
            result = direct
        else:
            mapped = alias.get(raw.lower(), "")
            if mapped:
                mapped_hit = lower_map.get(mapped.lower())
                if mapped_hit:
                    result = mapped_hit
                else:
                    result = mapped
            else:
                candidates = [n for n in entity_names if raw.lower() in n.lower() or n.lower() in raw.lower()]
                if len(candidates) == 1:
                    result = candidates[0]
                else:
                    result = alias.get(raw.lower(), raw)

        self._resolve_cache[cache_key] = result
        return result

    def _builtin_entity(self, name: str) -> dict[str, Any] | None:
        key = str(name or "").strip()
        if not key:
            return None
        canonical = SOLAR_SYSTEM_ALIAS.get(key.lower(), key)
        facts = SOLAR_SYSTEM_FACTS.get(canonical)
        if not facts:
            return None
        return {
            "id": f"builtin::{canonical}",
            "name": canonical,
            "description": f"{canonical} 的内置天文基础事实。",
            "category": facts.get("category", CN_SOLAR_CATEGORY),
            "raw": {
                "diameter_km": facts.get("diameter_km"),
                "distance_from_earth_km": facts.get("distance_from_earth_km"),
                "mass_earth": facts.get("mass_earth"),
                "surface_temp_c": facts.get("surface_temp_c"),
                "moon_count": facts.get("moon_count"),
                "orbital_period_days": facts.get("orbital_period_days"),
                "builtin": True,
            },
        }

    def _entity_metric(self, entity: dict[str, Any], key: str) -> float | None:
        raw = entity.get("raw") if isinstance(entity.get("raw"), dict) else {}
        value = raw.get(key)
        try:
            if value not in (None, ""):
                return float(value)
        except (TypeError, ValueError):
            pass

        fallback = self._builtin_entity(str(entity.get("name", "")))
        if fallback and fallback is not entity:
            raw = fallback.get("raw") if isinstance(fallback.get("raw"), dict) else {}
            try:
                if raw.get(key) not in (None, ""):
                    return float(raw.get(key))
            except (TypeError, ValueError):
                return None
        return None

    def _extract_ra_dec(self, entity: dict[str, Any]) -> tuple[float, float, float] | None:
        raw = entity.get("raw") if isinstance(entity.get("raw"), dict) else {}
        if not raw:
            raw = {}

        # 1. 优先从实体 raw 字段中提取（CSV/Excel 中若有 RA/Dec 列则直接使用）
        ra = self._pick_numeric_value(raw, [
            "ra", "ra_deg", "ra_hours", "right_ascension", "right ascension", "ra_hms",
            "ascension", "α", "赤经", "ra_j2000",
        ])
        dec = self._pick_numeric_value(raw, [
            "dec", "dec_deg", "declination", "decl", "dec_arcsec", "δ", "赤纬", "dec_j2000",
        ])
        if ra is not None and dec is not None:
            pass  # 已有有效坐标，继续处理
        else:
            # 2. 从内置星表查找（太阳系行星和亮星有真实天文坐标）
            name = str(entity.get("name", "")).strip()
            catalog_entry = self._lookup_builtin_catalog(name)
            if catalog_entry is not None:
                ra, dec = catalog_entry
            else:
                return None

        import math

        # RA 可以是 0-24 小时制，也可以是 0-360 度制
        # 如果 RA > 360，说明已经是度；如果 0-24 之间，需要乘以15转度
        ra_val = float(ra) if ra is not None else 0.0
        dec_val = float(dec) if dec is not None else 0.0
        if ra_val > 360.0:
            ra_val = ra_val % 360.0
        elif ra_val <= 24.0:
            # 小时制转度（1h = 15度）
            ra_val = (ra_val % 24.0) * 15.0

        ra_rad = math.radians(ra_val % 360.0)
        dec_rad = math.radians(max(-90.0, min(90.0, dec_val)))
        radius = 1.0
        distance_pc = self._pick_numeric_value(raw, [
            "distance_pc", "distance_ly", "distance", "dist_pc", "dist_ly",
            "parallax_mas", "parallax", "距离", "距离光年", "parsec",
        ])
        if distance_pc not in (None, 0):
            # parallax (mas) 优先：距离(pc) = 1000 / parallax(mas)
            if self._pick_numeric_value(raw, ["parallax_mas", "parallax"]) not in (None, 0):
                parallax = self._pick_numeric_value(raw, ["parallax_mas", "parallax"])
                if parallax and parallax > 0:
                    distance_pc = 1000.0 / parallax
            radius = max(0.35, min(1.0, 120.0 / max(float(distance_pc), 1.0)))
        x = radius * math.cos(dec_rad) * math.cos(ra_rad)
        y = radius * math.cos(dec_rad) * math.sin(ra_rad)
        z = radius * math.sin(dec_rad)
        return (x, y, z)

    def _lookup_builtin_catalog(self, name: str) -> tuple[float, float] | None:
        """查询内置星表，返回 (RA_hours, Dec_deg) 或 None"""
        name_lower = name.lower().strip()
        # 直接匹配
        if name in BUILTIN_STARFIELD_CATALOG:
            return BUILTIN_STARFIELD_CATALOG[name]
        # 小写匹配（处理大小写差异）
        for key, val in BUILTIN_STARFIELD_CATALOG.items():
            if key.lower() == name_lower:
                return val
        # 别名匹配（太阳系行星别名）
        alias_map = dict(SOLAR_SYSTEM_ALIAS)
        alias_map.update({v.lower(): v for k, v in SOLAR_SYSTEM_ALIAS.items()})
        resolved = alias_map.get(name_lower, name)
        if resolved in BUILTIN_STARFIELD_CATALOG:
            return BUILTIN_STARFIELD_CATALOG[resolved]
        return None

    def _pick_numeric_value(self, raw: dict[str, Any], keys: list[str]) -> float | None:
        normalized = {self._normalize_key(str(k)): v for k, v in raw.items()}
        for key in keys:
            value = normalized.get(self._normalize_key(key))
            if value in (None, ""):
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _normalize_key(value: str) -> str:
        return "".join(ch for ch in str(value or "").lower() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")

    def _fallback_solar_path(self, source: str, target: str) -> list[dict[str, str]]:
        src = SOLAR_SYSTEM_ALIAS.get(str(source).lower(), source)
        dst = SOLAR_SYSTEM_ALIAS.get(str(target).lower(), target)
        src_known = src in SOLAR_SYSTEM_FACTS
        dst_known = dst in SOLAR_SYSTEM_FACTS
        if not (src_known and dst_known) or src == dst:
            return []
        if src == CN_SOLAR:
            return [{"from": CN_SOLAR, "rel": "ORBITS_WITHIN", "to": dst}]
        if dst == CN_SOLAR:
            return [{"from": src, "rel": "ORBITS", "to": CN_SOLAR}]
        return [
            {"from": src, "rel": "ORBITS", "to": CN_SOLAR},
            {"from": CN_SOLAR, "rel": "ORBITS_WITHIN", "to": dst},
        ]

    def timeline(self, limit: int = 200) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for entity in self._collect_graph_entities():
            raw = entity.get("raw", {}) if isinstance(entity.get("raw"), dict) else {}
            year = raw.get("discovery_year")
            if year in (None, "", "null"):
                continue
            try:
                year_int = int(float(year))
            except (TypeError, ValueError):
                continue
            items.append(
                {
                    "year": year_int,
                    "name": entity.get("name", ""),
                    "category": entity.get("category", ""),
                    "event_type": "entity_discovery",
                    "importance": 6,
                    "description": str(entity.get("description", "")).strip()[:180]
                    or str(raw.get("description", "")).strip()[:180]
                    or f"{entity.get('name', '')} 被记录为图谱中的发现事件。",
                }
            )

        items.extend(dict(event) for event in ASTRO_TIMELINE_EVENTS)

        deduped: dict[tuple[int, str], dict[str, Any]] = {}
        for item in items:
            key = (int(item.get("year", 0) or 0), str(item.get("name", "")).strip())
            current = deduped.get(key)
            if current is None or int(item.get("importance", 0) or 0) > int(current.get("importance", 0) or 0):
                deduped[key] = item

        merged = sorted(
            deduped.values(),
            key=lambda x: (int(x.get("year", 0) or 0), int(x.get("importance", 0) or 0), str(x.get("name", ""))),
        )
        return merged[:limit]

    def starfield_points(self, limit: int = 800) -> list[dict[str, Any]]:
        points: list[dict[str, Any]] = []
        for entity in self._collect_graph_entities()[:limit]:
            name = str(entity.get("name", "")).strip()
            if not name:
                continue
            coords = self._extract_ra_dec(entity)
            if coords is not None:
                x, y, z = coords
                coord_source = "ra_dec"
            else:
                digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
                x = (int(digest[0:6], 16) / 0xFFFFFF) * 2 - 1
                y = (int(digest[6:12], 16) / 0xFFFFFF) * 2 - 1
                z = (int(digest[12:18], 16) / 0xFFFFFF) * 2 - 1
                coord_source = "hash_fallback"
            points.append(
                {
                    "name": name,
                    "category": entity.get("category", "unknown"),
                    "x": round(x * 100, 3),
                    "y": round(y * 100, 3),
                    "z": round(z * 100, 3),
                    "coord_source": coord_source,
                }
            )
        return points

    def _collect_entities(self) -> list[dict[str, Any]]:
        return self._data_service.export_entities()

    def _collect_graph_entities(self) -> list[dict[str, Any]]:
        # Exclude image catalog and text chunks from graph rendering/path exploration.
        entities: list[dict[str, Any]] = []
        for e in self._data_service.export_entities():
            source_file = str(e.get("source_file", "")).strip().lower()
            if source_file == "images_catalog.csv":
                continue
            raw = e.get("raw") if isinstance(e.get("raw"), dict) else {}
            if bool(raw.get("text_corpus")):
                continue
            category = str(e.get("category", "")).strip().lower()
            if category.startswith("hq_astro_kb"):
                continue
            name = str(e.get("name", "")).strip()
            if not name:
                continue
            entities.append(e)
        return entities

    def _recompute_graph(self) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        entities = self._collect_graph_entities()
        relations = self._extract_relations(entities)
        self._nodes_count = len(entities)
        self._relations_count = len(relations)
        self._relations = relations
        self._graph_ready = len(entities) > 0
        self._viz_cache.clear()
        # 图重组时清除邻接表和解析缓存，下次使用时自动重建
        self._adjacency = None
        self._resolve_cache.clear()
        self._data_revision_cache = self._data_service.revision
        return entities, relations

    def _extract_relations(self, entities: list[dict[str, Any]]) -> list[dict[str, str]]:
        relation_set: set[tuple[str, str, str]] = set()
        entity_names = [str(e.get("name", "")).strip() for e in entities if str(e.get("name", "")).strip()]
        entity_names_lc = {n.lower(): n for n in entity_names}
        # 预构建 token 集合：O(n) 一次，避免内层循环重复创建
        entity_tokens_lc: set[str] = set(entity_names_lc.keys())

        def norm_key(key: str) -> str:
            return "".join(ch for ch in key.lower() if ch.isalnum())

        def pick(raw: dict[str, Any], candidate_keys: list[str]) -> str:
            normalized = {norm_key(str(k)): v for k, v in raw.items()}
            for key in candidate_keys:
                value = normalized.get(norm_key(key))
                if value not in (None, ""):
                    return str(value).strip()
            return ""

        for entity in entities:
            src_name = str(entity.get("name", "")).strip()
            if not src_name:
                continue
            raw = entity.get("raw", {})
            description = (
                str(entity.get("description", "")).strip()
                or str(pick(raw, ["description", "desc", "summary", "body", "content", "text", "正文", "内容", "描述"]))
            )

            # Generic relation candidates.
            host_galaxy = pick(raw, ["host galaxy", "所属星系"])
            if host_galaxy:
                relation_set.add((src_name, "LOCATED_IN", host_galaxy))

            operator = pick(raw, ["operator", "operating agency", "运营方", "机构"])
            if operator:
                relation_set.add((src_name, "OPERATED_BY", operator))

            orbit_type = pick(raw, ["orbit type", "轨道类型"])
            if orbit_type:
                relation_set.add((src_name, "ORBIT_TYPE", orbit_type))

            discovery_method = pick(raw, ["discovery method", "发现方式", "discovery_method"])
            if discovery_method:
                relation_set.add((src_name, "DISCOVERED_VIA", discovery_method))

            obj_type = pick(
                raw,
                ["type", "type/category", "morphological type", "spectral type", "category", "分类", "类别"],
            )
            if obj_type:
                relation_set.add((src_name, "INSTANCE_OF", obj_type))

            # Exoplanet-specific relation extraction (for dynamic facts and xlsx fields).
            host_star = pick(raw, ["host star", "hostname", "host_star", "宿主恒星", "恒星"])
            if host_star:
                relation_set.add((src_name, "ORBITS", host_star))

            similar_to = pick(raw, ["similar to", "similar_to", "对比对象", "比较对象", "comparison_target"])
            if similar_to:
                relation_set.add((src_name, "SIMILAR_TO", similar_to))

            # Weak text mention relation — O(1) 集合查找替代 O(n) 遍历。
            # 仅对长度 ≥ 3 的实体名做检测，避免噪声。
            mention_text = " ".join(
                [
                    description,
                    pick(raw, ["major stars", "examples", "mission", "fun facts", "5 fun facts", "正文", "内容", "描述"]),
                ]
            ).lower()
            for name_lc, canonical in entity_names_lc.items():
                if canonical == src_name:
                    continue
                # 短名是噪声，且会导致误匹配；仅检测 ≥ 3 字符实体
                if len(name_lc) >= 3 and name_lc in mention_text:
                    relation_set.add((src_name, "RELATED_TO", canonical))

        relations = [{"from": f, "rel": r, "to": t} for f, r, t in relation_set]
        relations.sort(key=lambda x: (x["from"], x["rel"], x["to"]))
        return relations

    def _write_to_neo4j(
        self, entities: list[dict[str, Any]], relations: list[dict[str, str]]
    ) -> tuple[bool, str]:
        if not settings.neo4j_enabled:
            return False, "未启用 NEO4J_ENABLED。"

        try:
            from neo4j import GraphDatabase

            driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
            )
            with driver.session() as session:
                session.run("CREATE CONSTRAINT entity_name IF NOT EXISTS FOR (n:Entity) REQUIRE n.name IS UNIQUE")
                for entity in entities:
                    session.run(
                        """
                        MERGE (n:Entity {name: $name})
                        SET n.id = $id, n.category = $category, n.description = $description
                        """,
                        name=entity.get("name", ""),
                        id=entity.get("id", ""),
                        category=entity.get("category", ""),
                        description=entity.get("description", ""),
                    )
                for rel in relations:
                    session.run(
                        """
                        MERGE (a:Entity {name: $from_name})
                        MERGE (b:Entity {name: $to_name})
                        MERGE (a)-[r:RELATED {type: $rel_type}]->(b)
                        """,
                        from_name=rel["from"],
                        to_name=rel["to"],
                        rel_type=rel["rel"],
                    )
            driver.close()
            return True, f"写入实体 {len(entities)}，关系 {len(relations)}"
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"

    def run_cypher(self, query: str, params: dict[str, Any]) -> tuple[bool, list[dict[str, Any]], str]:
        if not settings.neo4j_enabled:
            return False, [], "未启用 NEO4J_ENABLED。"
        if not query.strip().lower().startswith("match"):
            return False, [], "仅允许以 MATCH 开头的只读查询。"

        try:
            from neo4j import GraphDatabase

            driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
            )
            with driver.session() as session:
                result = session.run(query, params)
                records = [dict(r) for r in result]
            driver.close()
            return True, records, "ok"
        except Exception as exc:  # noqa: BLE001
            return False, [], f"{type(exc).__name__}: {exc}"

    def export_cypher(self, output_path: str) -> tuple[bool, int, int, str]:
        entities = self._collect_graph_entities()
        relations = self._relations
        if not entities:
            return False, 0, 0, "当前没有已加载实体，请先执行数据加载或构图。"

        lines: list[str] = []
        lines.append("// Auto-generated by AstroGraph")
        lines.append("CREATE CONSTRAINT entity_name IF NOT EXISTS FOR (n:Entity) REQUIRE n.name IS UNIQUE;")
        lines.append("")

        for entity in entities:
            name = self._escape_cypher_value(entity.get("name", ""))
            eid = self._escape_cypher_value(entity.get("id", ""))
            category = self._escape_cypher_value(entity.get("category", "unknown"))
            description = self._escape_cypher_value(entity.get("description", ""))
            lines.append(
                "MERGE (n:Entity {name: '%s'}) "
                "SET n.id='%s', n.category='%s', n.description='%s';"
                % (name, eid, category, description)
            )

        lines.append("")
        for rel in relations:
            from_name = self._escape_cypher_value(rel["from"])
            to_name = self._escape_cypher_value(rel["to"])
            rel_type = self._escape_cypher_value(rel["rel"])
            lines.append(
                "MATCH (a:Entity {name: '%s'}), (b:Entity {name: '%s'}) "
                "MERGE (a)-[:RELATED {type: '%s'}]->(b);"
                % (from_name, to_name, rel_type)
            )

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("\n".join(lines), encoding="utf-8")
        return True, len(entities), len(relations), f"Cypher 已导出到 {output}"

    def graph_schema_summary(self) -> dict[str, Any]:
        entities = self._collect_graph_entities()
        category_count: dict[str, int] = {}
        rel_count: dict[str, int] = {}
        for e in entities:
            c = str(e.get("category", "unknown"))
            category_count[c] = category_count.get(c, 0) + 1
        for r in self._relations:
            t = str(r["rel"])
            rel_count[t] = rel_count.get(t, 0) + 1
        return {
            "entity_total": len(entities),
            "relation_total": len(self._relations),
            "categories": category_count,
            "relation_types": rel_count,
        }

    def _escape_cypher_value(self, value: object) -> str:
        """对 Cypher 字符串值进行完整转义，防止注入。"""
        raw = str(value or "")
        # 1. 转义反斜杠（必须在其他转义之前）
        escaped = raw.replace("\\", "\\\\")
        # 2. 转义换行、回车、Tab
        escaped = escaped.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        # 3. 转义单引号（最关键）
        escaped = escaped.replace("'", "\\'")
        # 4. 转义双引号（防止破坏双引号包裹的字符串）
        escaped = escaped.replace('"', '\\"')
        # 5. 转义反引号（防止破坏 `标识符`）
        escaped = escaped.replace("`", "\\`")
        return escaped

