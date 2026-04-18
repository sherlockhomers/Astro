from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends

from app.deps import ServiceContainer, get_services

router = APIRouter(prefix="/api/v1/landing", tags=["landing"])


@router.get("/apod")
def landing_apod(svc: ServiceContainer = Depends(get_services)) -> dict:
    return svc.landing.get_apod()


@router.get("/news")
def landing_news(limit: int = 6, svc: ServiceContainer = Depends(get_services)) -> dict:
    return {"items": svc.landing.get_news(limit=limit), "updated_at": datetime.utcnow().isoformat()}


@router.get("/science-cards")
def landing_science_cards(limit: int = 8, svc: ServiceContainer = Depends(get_services)) -> dict:
    return {"items": svc.landing.get_science_cards(limit=limit)}


@router.get("/frontier")
def landing_frontier(per_topic: int = 36, svc: ServiceContainer = Depends(get_services)) -> dict:
    return svc.landing.get_frontier(per_topic=per_topic)
