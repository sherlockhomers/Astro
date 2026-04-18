# 给前端调用 astro_tools 的一组接口。用 Pydantic 模型约束入参，拿算完的结果返回。
# 没有身份门槛——这些都是幂等的无副作用计算，匿名用户也能用。

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.astro_tools_service import (
    convert_coord,
    moon_phase,
    planet_visibility,
    tool_catalog,
)

router = APIRouter(prefix="/api/v1/astro-tools", tags=["astro-tools"])


class MoonPhaseQuery(BaseModel):
    date: str | None = Field(default=None, description="YYYY-MM-DD，留空就是现在")


class PlanetVisibilityQuery(BaseModel):
    planet: str = Field(..., description="行星中英文名，如 'mars' / '木星'")
    city: str | None = Field(default=None, description="城市中文名；不给就默认北京")
    latitude: float | None = None
    longitude: float | None = None
    datetime_iso: str | None = Field(default=None, description="ISO 8601 时间；留空表示现在")


class CoordConvertQuery(BaseModel):
    ra: float = Field(..., description="赤经或黄经，度")
    dec: float = Field(..., description="赤纬或黄纬，度")
    from_frame: str = Field(default="equatorial")
    to_frame: str = Field(default="ecliptic")


def _parse_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


@router.get("/catalog")
def catalog() -> dict[str, Any]:
    return {"tools": tool_catalog()}


@router.post("/moon-phase")
def api_moon_phase(payload: MoonPhaseQuery | None = None) -> dict[str, Any]:
    dt = _parse_datetime(payload.date) if payload else None
    result = moon_phase(dt)
    return {
        "ok": True,
        "date": result.date,
        "phase_name": result.phase_name,
        "illumination": result.illumination,
        "age_days": result.age_days,
        "synodic_fraction": result.synodic_fraction,
        "summary": f"{result.date} 是 {result.phase_name}，亮度约 {int(result.illumination * 100)}%，月龄 {result.age_days} 天。",
    }


@router.post("/planet-visibility")
def api_planet_visibility(payload: PlanetVisibilityQuery) -> dict[str, Any]:
    dt = _parse_datetime(payload.datetime_iso)
    result = planet_visibility(
        name=payload.planet,
        dt=dt,
        latitude=payload.latitude,
        longitude=payload.longitude,
        city=payload.city,
    )
    if result is None:
        raise HTTPException(status_code=400, detail="行星名不认识，支持：水星/金星/火星/木星/土星/天王星/海王星")
    return {
        "ok": True,
        "planet_zh": result.planet_zh,
        "planet_en": result.planet_en,
        "date": result.date,
        "location": result.location_label,
        "latitude": result.latitude,
        "longitude": result.longitude,
        "altitude_deg": result.altitude_deg,
        "azimuth_deg": result.azimuth_deg,
        "azimuth_label": result.azimuth_label,
        "distance_au": result.distance_au,
        "visible_now": result.visible_now,
        "advice": result.advice,
        "summary": (
            f"{result.date} 在 {result.location_label}，{result.planet_zh}"
            f"位于{result.azimuth_label}方向，地平高度 {result.altitude_deg}°，"
            f"距离 {result.distance_au} AU。{result.advice}"
        ),
    }


@router.post("/coord-convert")
def api_coord_convert(payload: CoordConvertQuery) -> dict[str, Any]:
    result = convert_coord(
        ra_deg=payload.ra,
        dec_deg=payload.dec,
        from_frame=payload.from_frame,
        to_frame=payload.to_frame,
    )
    return {
        "ok": True,
        "input": {"ra": result.ra_in, "dec": result.dec_in, "frame": result.from_frame},
        "output": {"ra": result.ra_out, "dec": result.dec_out, "frame": result.to_frame},
        "summary": (
            f"{result.from_frame} ({result.ra_in}°, {result.dec_in}°) → "
            f"{result.to_frame} ({result.ra_out}°, {result.dec_out}°)"
        ),
    }
