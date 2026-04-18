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


@router.get("/recommend-path")
def user_recommend_path(
    user: dict = Depends(require_user),
    svc: ServiceContainer = Depends(get_services),
) -> dict:
    # 「你的下一站」：根据用户收藏和历史问答，在知识图谱上做随机游走，推荐下一步要看的东西。
    # 比静态模板聪明得多，用户每天会看到不一样的推荐。
    overview = svc.user.build_overview(user["user_id"])
    seeds: list[str] = []
    for item in overview.get("recent_explorations", [])[:4]:
        topic = str(item.get("topic", "")).strip()
        if topic and topic not in seeds:
            seeds.append(topic)
    for fav in overview.get("favorites", [])[:4]:
        title = str(fav.get("title", "")).strip()
        if title and title not in seeds:
            seeds.append(title)

    walk_results = svc.graph.recommend_by_walk(seeds, walks_per_seed=14, steps=3, top_k=8) if seeds else []

    cards: list[dict] = []
    for entry in walk_results:
        name = entry["name"]
        seed = entry["seed"]
        rel = entry["relation"] or "相关"
        cards.append({
            "name": name,
            "seed": seed,
            "relation": rel,
            "score": entry["hits"],
            "query": f"{name}是什么？",
            "reason": f"因为你关注了「{seed}」，和它通过「{rel}」相关",
            "path": "/app/qa",
        })

    # 首次用户或者图谱还没准备好，给几个通用入口别让卡片空着
    if not cards:
        cards = [
            {"name": "木星", "seed": "", "relation": "", "score": 0,
             "query": "木星为什么有这么多卫星？", "reason": "从气态巨行星入门", "path": "/app/qa"},
            {"name": "黑洞", "seed": "", "relation": "", "score": 0,
             "query": "黑洞为什么连光都逃不出来？", "reason": "挑战极端物理", "path": "/app/qa"},
            {"name": "土星", "seed": "", "relation": "", "score": 0,
             "query": "土星", "reason": "3D 视角看一看", "path": "/app/starfield"},
        ]

    return {
        "ok": True,
        "seeds": seeds,
        "cards": cards,
        "total": len(cards),
    }
