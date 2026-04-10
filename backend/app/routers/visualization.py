from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import ServiceContainer, get_services

router = APIRouter(prefix="/api/v1/visualization", tags=["visualization"])


@router.get("/graph")
def visualization_graph(max_nodes: int = 220, max_links: int = 900, svc: ServiceContainer = Depends(get_services)) -> dict:
    return svc.graph.visualization_graph(max_nodes=max_nodes, max_links=max_links)


@router.get("/subgraph")
def visualization_subgraph(
    query: str, max_nodes: int = 600, max_links: int = 4000,
    max_hops: int = 1, include_related: bool = False,
    svc: ServiceContainer = Depends(get_services),
) -> dict:
    return svc.graph.visualization_subgraph(
        query=query, max_nodes=max_nodes, max_links=max_links,
        max_hops=max_hops, include_related=include_related,
    )


@router.get("/compare")
def visualization_compare(name_a: str, name_b: str, svc: ServiceContainer = Depends(get_services)) -> dict:
    return svc.graph.compare_entities(name_a, name_b)


@router.get("/timeline")
def visualization_timeline(limit: int = 200, svc: ServiceContainer = Depends(get_services)) -> dict:
    return {"items": svc.graph.timeline(limit=limit)}


@router.get("/starfield")
def visualization_starfield(limit: int = 800, svc: ServiceContainer = Depends(get_services)) -> dict:
    return {"items": svc.graph.starfield_points(limit=limit)}


@router.get("/model3d")
def visualization_model3d(query: str, svc: ServiceContainer = Depends(get_services)) -> dict:
    return svc.model3d.search(query)
