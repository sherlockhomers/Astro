# 天文快讯服务。目前聚合两个源：
# 1) NASA NeoWs —— 今天和明天的潜在危险近地小行星
# 2) GCN Circulars —— 伽马射线暴和高能瞬变源警报
#
# 设计原则：
# - 所有外部请求带超时，任何一个源挂了都不影响其他源
# - 结果有缓存（10 分钟），别把用户点一下就打爆 NASA 的接口
# - 输出的 severity 字段前端用来决定 banner 颜色
#
# 以后要加源（比如 Transient Name Server），在 _fetch_xxx 下面新写一个函数塞进 collect 即可。

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger("astrograph")


@dataclass
class SpaceEvent:
    id: str
    title: str
    summary: str
    source: str              # NeoWs / GCN / ...
    severity: str            # info / notable / alert
    happens_at: str          # ISO 日期或人类可读字符串
    url: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class SpaceEventsService:
    _CACHE_TTL_SECONDS = 10 * 60

    def __init__(self) -> None:
        self._lock = Lock()
        self._cache: list[SpaceEvent] = []
        self._cache_at: float = 0

    def get_events(self, limit: int = 6) -> dict[str, Any]:
        with self._lock:
            if self._cache and (time.time() - self._cache_at) < self._CACHE_TTL_SECONDS:
                events = self._cache
            else:
                events = self._collect()
                self._cache = events
                self._cache_at = time.time()

        top = events[: max(1, min(int(limit), 20))]
        return {
            "updated_at": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
            "count": len(top),
            "events": [self._serialize(e) for e in top],
        }

    def _serialize(self, e: SpaceEvent) -> dict[str, Any]:
        return {
            "id": e.id,
            "title": e.title,
            "summary": e.summary,
            "source": e.source,
            "severity": e.severity,
            "happens_at": e.happens_at,
            "url": e.url,
            "extra": e.extra,
        }

    def _collect(self) -> list[SpaceEvent]:
        events: list[SpaceEvent] = []
        # 各个源独立 try/except —— 一个挂了不能影响整体
        try:
            events.extend(self._fetch_neo_hazards())
        except Exception as exc:
            logger.warning("space_events: NeoWs 拉取失败: %s", exc)
        try:
            events.extend(self._fetch_gcn_circulars())
        except Exception as exc:
            logger.warning("space_events: GCN 拉取失败: %s", exc)

        # 按严重程度 + 时间排，严重的放前面
        severity_order = {"alert": 0, "notable": 1, "info": 2}
        events.sort(key=lambda e: (severity_order.get(e.severity, 3), e.happens_at))
        return events

    # ---- NeoWs: 近地小行星 ---------------------------------------------------

    def _fetch_neo_hazards(self) -> list[SpaceEvent]:
        api_key = str(getattr(settings, "mcp_nasa_api_key", "") or "DEMO_KEY")
        if api_key.upper() in {"NASA-KEY-REQUIRED", ""}:
            api_key = "DEMO_KEY"

        today = datetime.utcnow().date()
        end = today + timedelta(days=1)
        url = "https://api.nasa.gov/neo/rest/v1/feed"
        params = {
            "start_date": today.isoformat(),
            "end_date": end.isoformat(),
            "api_key": api_key,
        }

        try:
            resp = httpx.get(url, params=params, timeout=5.0)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.info("NeoWs 暂不可用: %s", exc)
            return []

        events: list[SpaceEvent] = []
        feed = data.get("near_earth_objects", {}) or {}
        for day_key, items in feed.items():
            for obj in items:
                name = str(obj.get("name", "")).strip("()").strip()
                hazardous = bool(obj.get("is_potentially_hazardous_asteroid", False))
                approach_list = obj.get("close_approach_data") or []
                if not approach_list:
                    continue
                approach = approach_list[0]
                miss_km = 0.0
                try:
                    miss_km = float(approach.get("miss_distance", {}).get("kilometers", 0) or 0)
                except (TypeError, ValueError):
                    miss_km = 0.0
                diameter = obj.get("estimated_diameter", {}).get("meters", {})
                d_min = float(diameter.get("estimated_diameter_min") or 0)
                d_max = float(diameter.get("estimated_diameter_max") or 0)

                severity = "alert" if hazardous else ("notable" if miss_km < 5_000_000 else "info")
                approach_time = str(approach.get("close_approach_date_full") or approach.get("close_approach_date") or day_key)

                summary = (
                    f"直径约 {d_min:.0f}~{d_max:.0f} 米，"
                    f"以 {float(approach.get('relative_velocity', {}).get('kilometers_per_second', 0) or 0):.1f} km/s 速度飞过地球，"
                    f"最近距离约 {miss_km / 10000:.0f} 万公里。"
                )

                events.append(SpaceEvent(
                    id=f"neo-{obj.get('id', name)}",
                    title=f"{'⚠ 潜在危险小行星 ' if hazardous else ''}{name}{'' if hazardous else ' 今日掠过'}",
                    summary=summary,
                    source="NeoWs",
                    severity=severity,
                    happens_at=approach_time,
                    url=str(obj.get("nasa_jpl_url") or ""),
                    extra={"miss_km": miss_km, "hazardous": hazardous},
                ))

        # 保留最显眼的几条。按危险优先、距离递增
        events.sort(key=lambda e: (0 if e.severity == "alert" else 1, float(e.extra.get("miss_km", 1e12))))
        return events[:4]

    # ---- GCN: 高能瞬变源警报 -------------------------------------------------

    def _fetch_gcn_circulars(self) -> list[SpaceEvent]:
        # GCN 公开的 JSON 端点。Circulars 是专家发布的通告，多为伽马射线暴 / 引力波对应体
        url = "https://gcn.nasa.gov/circulars/archive.json"
        try:
            resp = httpx.get(url, params={"limit": 10}, timeout=5.0, headers={"User-Agent": "AstroVista/0.2"})
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            logger.info("GCN Circulars 暂不可用: %s", exc)
            return []

        items = payload.get("circulars") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            return []

        events: list[SpaceEvent] = []
        for item in items[:6]:
            try:
                circ_id = str(item.get("circularId") or item.get("id") or "")
                subject = str(item.get("subject") or "").strip()
                if not circ_id or not subject:
                    continue
                body = str(item.get("body") or "")[:260]
                created = item.get("createdOn") or item.get("date") or ""
                events.append(SpaceEvent(
                    id=f"gcn-{circ_id}",
                    title=f"[GCN #{circ_id}] {subject}",
                    summary=body + ("..." if len(body) == 260 else ""),
                    source="GCN",
                    severity="notable",
                    happens_at=str(created),
                    url=f"https://gcn.nasa.gov/circulars/{circ_id}",
                ))
            except Exception:
                continue
        return events
