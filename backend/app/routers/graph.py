from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.deps import ServiceContainer, get_services
from app.schemas import (
    BuildGraphRequest, BuildGraphResponse, CypherQueryRequest, CypherQueryResponse,
    GraphExportCypherRequest, GraphExportCypherResponse, GraphMultiPathQueryResponse,
    GraphPathQueryResponse, GraphPathResponse, GraphRAGQueryRequest, GraphRAGQueryResponse,
)

router = APIRouter(prefix="/api/v1", tags=["graph"])


@router.post("/graphrag/query", response_model=GraphRAGQueryResponse)
def graphrag_query(payload: GraphRAGQueryRequest, svc: ServiceContainer = Depends(get_services)) -> GraphRAGQueryResponse:
    return GraphRAGQueryResponse(**svc.graphrag.query(payload.question))


@router.post("/graph/build", response_model=BuildGraphResponse)
def build_graph(payload: BuildGraphRequest, svc: ServiceContainer = Depends(get_services)) -> BuildGraphResponse:
    try:
        accepted, message, task_id = svc.graph.build_graph(payload.csv_root, payload.categories, payload.write_neo4j)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BuildGraphResponse(accepted=accepted, message=message, task_id=task_id)


@router.post("/graph/export-cypher", response_model=GraphExportCypherResponse)
def graph_export_cypher(payload: GraphExportCypherRequest, svc: ServiceContainer = Depends(get_services)) -> GraphExportCypherResponse:
    ok, node_count, relation_count, message = svc.graph.export_cypher(payload.output_path)
    return GraphExportCypherResponse(ok=ok, output_path=payload.output_path, node_count=node_count, relation_count=relation_count, message=message)


@router.get("/graph/status")
def graph_status(svc: ServiceContainer = Depends(get_services)) -> dict:
    return svc.graph.status()


@router.get("/graph/schema-summary")
def graph_schema_summary(svc: ServiceContainer = Depends(get_services)) -> dict:
    return svc.graph.graph_schema_summary()


@router.get("/graph/paths", response_model=GraphPathResponse)
def graph_paths(top_k: int = 20, svc: ServiceContainer = Depends(get_services)) -> GraphPathResponse:
    return GraphPathResponse(items=svc.graph.preview_paths(top_k=top_k))


@router.get("/graph/path", response_model=GraphPathQueryResponse)
def graph_path_between(source: str, target: str, max_hops: int = 4, svc: ServiceContainer = Depends(get_services)) -> GraphPathQueryResponse:
    path = svc.graph.find_path(source, target, max_hops=max_hops)
    if not path:
        return GraphPathQueryResponse(found=False, path=[], message="Path not found")
    return GraphPathQueryResponse(found=True, path=path, message="ok")


@router.get("/graph/multi-path", response_model=GraphMultiPathQueryResponse)
def graph_multi_path_between(source: str, target: str, max_hops: int = 4, max_paths: int = 6, svc: ServiceContainer = Depends(get_services)) -> GraphMultiPathQueryResponse:
    paths = svc.graph.find_paths(source, target, max_hops=max_hops, max_paths=max_paths)
    if not paths:
        return GraphMultiPathQueryResponse(found=False, paths=[], message="Path not found")
    return GraphMultiPathQueryResponse(found=True, paths=paths, message="ok")


@router.post("/graph/cypher", response_model=CypherQueryResponse)
def graph_cypher(payload: CypherQueryRequest, svc: ServiceContainer = Depends(get_services)) -> CypherQueryResponse:
    ok, records, message = svc.graph.run_cypher(payload.query, payload.params)
    return CypherQueryResponse(ok=ok, records=records, message=message)
