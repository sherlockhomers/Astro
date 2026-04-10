from __future__ import annotations

import json

from fastapi import APIRouter, Depends

from app.deps import ServiceContainer, get_services, require_user
from app.schemas import MutationStatusResponse, QAHistoryResponse, UserFavoriteCreateRequest, UserOverviewResponse

router = APIRouter(prefix="/api/v1/user", tags=["user"])


@router.get("/history", response_model=QAHistoryResponse)
def user_history(
    limit: int = 50, offset: int = 0,
    user: dict = Depends(require_user),
    svc: ServiceContainer = Depends(get_services),
) -> QAHistoryResponse:
    history = svc.user.list_history(user["user_id"], limit=limit, offset=offset)
    items = []
    for row in history["items"]:
        try:
            citations = json.loads(row.get("citations_json", "[]"))
        except json.JSONDecodeError:
            citations = []
        items.append({
            "id": row["id"], "session_id": row["session_id"],
            "question": row["question"], "answer": row["answer"],
            "citations": citations, "created_at": row["created_at"],
        })
    return QAHistoryResponse(
        items=items, limit=int(history["limit"]), offset=int(history["offset"]),
        total=int(history["total"]), has_more=bool(history["has_more"]),
    )


@router.get("/overview", response_model=UserOverviewResponse)
def user_overview(
    user: dict = Depends(require_user),
    svc: ServiceContainer = Depends(get_services),
) -> UserOverviewResponse:
    return UserOverviewResponse(**svc.user.build_overview(user["user_id"]))


@router.post("/favorites", response_model=MutationStatusResponse)
def user_favorite_create(
    payload: UserFavoriteCreateRequest,
    user: dict = Depends(require_user),
    svc: ServiceContainer = Depends(get_services),
) -> MutationStatusResponse:
    ok, message, row_id = svc.user.save_favorite(
        user_id=user["user_id"], title=payload.title,
        category=payload.category, image_url=payload.image_url,
        source_query=payload.source_query,
    )
    return MutationStatusResponse(ok=ok, message=message, id=row_id)


@router.delete("/favorites/{favorite_id}", response_model=MutationStatusResponse)
def user_favorite_delete(
    favorite_id: int,
    user: dict = Depends(require_user),
    svc: ServiceContainer = Depends(get_services),
) -> MutationStatusResponse:
    ok, message = svc.user.delete_favorite(user["user_id"], favorite_id)
    return MutationStatusResponse(ok=ok, message=message, id=favorite_id if ok else None)


@router.delete("/history/{history_id}", response_model=MutationStatusResponse)
def user_history_delete(
    history_id: int,
    user: dict = Depends(require_user),
    svc: ServiceContainer = Depends(get_services),
) -> MutationStatusResponse:
    ok, message = svc.user.delete_history(user["user_id"], history_id)
    return MutationStatusResponse(ok=ok, message=message, id=history_id if ok else None)
