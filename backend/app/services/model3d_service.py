from __future__ import annotations

from typing import Any

from app.services.data_service import DataService


ZH_BLACK_HOLE = "\u9ed1\u6d1e"
ZH_EARTH = "\u5730\u7403"
ZH_MOON = "\u6708\u7403"
ZH_JUPITER = "\u6728\u661f"
ZH_SATURN = "\u571f\u661f"
ZH_MARS = "\u706b\u661f"
ZH_SUN = "\u592a\u9633"
ZH_VENUS = "\u91d1\u661f"
ZH_MERCURY = "\u6c34\u661f"
ZH_NEPTUNE = "\u6d77\u738b\u661f"
ZH_URANUS = "\u5929\u738b\u661f"
ZH_PLUTO = "\u51a5\u738b\u661f"
ZH_ASTEROID = "\u5c0f\u884c\u661f"
ZH_COMET = "\u5f57\u661f"
ZH_NEBULA = "\u661f\u4e91"
ZH_GALAXY = "\u661f\u7cfb"
ZH_MILKY_WAY = "\u94f6\u6cb3\u7cfb"
ZH_CERES = "\u8c37\u795e\u661f"


class Model3DService:
    def __init__(self, data_service: DataService) -> None:
        self._data_service = data_service

    def search(self, query: str) -> dict[str, Any]:
        q = str(query or "").strip()
        if not q:
            return {"ok": False, "message": "query cannot be empty"}

        # Built-in presets first, so common objects always resolve.
        preset = self._resolve_builtin_preset(q)
        if preset is not None:
            model = self._build_model_payload(name=preset["name"], category=preset["category"], raw={})
            return {
                "ok": True,
                "entity": {"name": preset["name"], "category": preset["category"]},
                "model": model,
            }

        entity = self._data_service.find_best_entity_for_question(q)
        if entity is None:
            q_lc = q.lower()
            for e in self._data_service.export_entities():
                name = str(e.get("name", "")).strip()
                if name and q_lc in name.lower():
                    entity = e
                    break

        if entity is None:
            return {"ok": False, "message": "entity not found"}

        name = str(entity.get("name", "")).strip()
        category = str(entity.get("category", "")).lower()
        raw = entity.get("raw", {}) if isinstance(entity.get("raw", {}), dict) else {}
        model = self._build_model_payload(name=name, category=category, raw=raw)
        return {"ok": True, "entity": {"name": name, "category": category}, "model": model}

    def _build_model_payload(self, name: str, category: str, raw: dict[str, Any]) -> dict[str, Any]:
        kind = "sphere"
        color = "#77b7ff"
        ring = False
        emissive = "#000000"
        size = 1.0
        preset = "generic"

        n = name.lower()
        if "saturn" in n or ZH_SATURN in name:
            ring = True
            color = "#d9c38a"
            size = 1.22
            preset = "saturn"
        elif "jupiter" in n or ZH_JUPITER in name:
            color = "#d39a63"
            size = 1.45
            preset = "jupiter"
        elif "mars" in n or ZH_MARS in name:
            color = "#cc6646"
            preset = "mars"
        elif "neptune" in n or ZH_NEPTUNE in name:
            color = "#4f7dff"
            preset = "neptune"
        elif "uranus" in n or ZH_URANUS in name:
            color = "#8ed9d8"
            preset = "uranus"
        elif "venus" in n or ZH_VENUS in name:
            color = "#d2b483"
            preset = "venus"
        elif "mercury" in n or ZH_MERCURY in name:
            color = "#a9a39a"
            preset = "mercury"
        elif "moon" in n or ZH_MOON in name:
            color = "#c8c8c8"
            preset = "moon"
        elif "earth" in n or ZH_EARTH in name:
            color = "#5aa7ff"
            preset = "earth"
        elif "sun" in n or ZH_SUN in name:
            color = "#ffd36a"
            emissive = "#aa6f00"
            size = 1.62
            preset = "sun"
        elif "pluto" in n or ZH_PLUTO in name:
            color = "#cab6a1"
            preset = "pluto"
        elif "ceres" in n or ZH_CERES in name:
            color = "#b4b0ab"
            preset = "asteroid"
        elif "comet" in n or ZH_COMET in name:
            color = "#d5d7df"
            preset = "comet"
        elif "asteroid" in n or ZH_ASTEROID in name:
            color = "#b5aea3"
            preset = "asteroid"

        if "black_hole" in category or "black hole" in n or ZH_BLACK_HOLE in name:
            kind = "blackhole"
            color = "#0f0f17"
            emissive = "#000000"
            ring = True
            size = 1.52
            preset = "blackhole"
        elif "nebula" in category or ZH_NEBULA in name:
            kind = "nebula"
            color = "#8a66ff"
            emissive = "#1f0f3f"
            size = 1.8
            preset = "nebula"
        elif "galax" in category or ZH_GALAXY in name:
            kind = "galaxy"
            color = "#8fd3ff"
            emissive = "#12324a"
            size = 2.0
            preset = "galaxy"

        radius_hint = self._safe_number(raw.get("radius")) or self._safe_number(raw.get("radius (r)"))
        if radius_hint is not None and preset == "generic":
            size = max(0.85, min(2.0, 0.85 + radius_hint / 2.5))

        return {
            "kind": kind,
            "preset": preset,
            "color": color,
            "emissive": emissive,
            "ring": ring,
            "size": round(size, 3),
            "note": "3D preset generated from entity type and attributes",
        }

    def _resolve_builtin_preset(self, query: str) -> dict[str, str] | None:
        q = str(query or "").strip().lower()
        if not q:
            return None
        mapping: list[tuple[list[str], dict[str, str]]] = [
            ([ZH_BLACK_HOLE.lower(), "black hole", "blackhole"], {"name": ZH_BLACK_HOLE, "category": "black_hole"}),
            ([ZH_EARTH.lower(), "earth"], {"name": ZH_EARTH, "category": "planet"}),
            ([ZH_MOON.lower(), "moon", "luna"], {"name": ZH_MOON, "category": "moon"}),
            ([ZH_JUPITER.lower(), "jupiter"], {"name": ZH_JUPITER, "category": "planet"}),
            ([ZH_SATURN.lower(), "saturn"], {"name": ZH_SATURN, "category": "planet"}),
            ([ZH_MARS.lower(), "mars"], {"name": ZH_MARS, "category": "planet"}),
            ([ZH_SUN.lower(), "sun", "sol"], {"name": ZH_SUN, "category": "star"}),
            ([ZH_VENUS.lower(), "venus"], {"name": ZH_VENUS, "category": "planet"}),
            ([ZH_MERCURY.lower(), "mercury"], {"name": ZH_MERCURY, "category": "planet"}),
            ([ZH_NEPTUNE.lower(), "neptune"], {"name": ZH_NEPTUNE, "category": "planet"}),
            ([ZH_URANUS.lower(), "uranus"], {"name": ZH_URANUS, "category": "planet"}),
            ([ZH_PLUTO.lower(), "pluto"], {"name": ZH_PLUTO, "category": "dwarf_planet"}),
            ([ZH_ASTEROID.lower(), "asteroid"], {"name": ZH_ASTEROID, "category": "small_body"}),
            ([ZH_COMET.lower(), "comet"], {"name": ZH_COMET, "category": "small_body"}),
            ([ZH_CERES.lower(), "ceres"], {"name": ZH_CERES, "category": "dwarf_planet"}),
            ([ZH_NEBULA.lower(), "nebula"], {"name": ZH_NEBULA, "category": "nebula"}),
            ([ZH_GALAXY.lower(), ZH_MILKY_WAY.lower(), "galaxy"], {"name": ZH_MILKY_WAY, "category": "galaxy"}),
        ]
        for aliases, payload in mapping:
            for key in aliases:
                if key and key in q:
                    return payload
        return None

    def _safe_number(self, value: Any) -> float | None:
        if value in (None, ""):
            return None
        text = str(value).strip().lower()
        buf: list[str] = []
        dot_used = False
        for ch in text:
            if ch.isdigit():
                buf.append(ch)
                continue
            if ch == "." and not dot_used:
                buf.append(ch)
                dot_used = True
                continue
            if buf:
                break
        if not buf:
            return None
        try:
            return float("".join(buf))
        except ValueError:
            return None
