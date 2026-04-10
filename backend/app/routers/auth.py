from __future__ import annotations

import logging

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response

from app.config import settings
from app.deps import ServiceContainer, client_context, get_services, require_user
from app.schemas import AuthResponse, RegisterRequest, LoginRequest, UpdateProfileRequest, UserProfileResponse

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
logger = logging.getLogger("astrograph")


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=bool(settings.auth_cookie_secure),
        samesite=settings.auth_cookie_samesite,
        max_age=int(settings.auth_refresh_token_days) * 24 * 60 * 60,
        path="/",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.auth_cookie_name,
        path="/",
        samesite=settings.auth_cookie_samesite,
    )


@router.post("/register", response_model=AuthResponse)
def auth_register(
    payload: RegisterRequest,
    svc: ServiceContainer = Depends(get_services),
) -> AuthResponse:
    try:
        ok, message = svc.user.register(payload.username, payload.password)
        return AuthResponse(ok=ok, message=message)
    except Exception as exc:
        logger.error("Register failed: %s", exc)
        return AuthResponse(ok=False, message="注册失败，请稍后重试")


@router.post("/login", response_model=AuthResponse)
def auth_login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    svc: ServiceContainer = Depends(get_services),
) -> AuthResponse:
    try:
        user_agent, ip_address = client_context(request)
        ok, message, user_id, username, access_token, refresh_token, expires_in = svc.user.login(
            payload.username,
            payload.password,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        if ok and refresh_token:
            _set_refresh_cookie(response, refresh_token)
        return AuthResponse(
            ok=ok,
            message=message,
            token=access_token,
            access_token=access_token,
            token_type="Bearer",
            expires_in=expires_in,
            user_id=user_id,
            username=username,
        )
    except Exception as exc:
        logger.error("Login failed: %s", exc)
        _clear_refresh_cookie(response)
        return AuthResponse(ok=False, message="登录失败，请稍后重试")


@router.post("/refresh", response_model=AuthResponse)
def auth_refresh(
    request: Request,
    response: Response,
    svc: ServiceContainer = Depends(get_services),
    refresh_token: str | None = Cookie(default=None, alias=settings.auth_cookie_name),
) -> AuthResponse:
    try:
        user_agent, ip_address = client_context(request)
        ok, message, payload = svc.user.refresh_session(
            refresh_token or "",
            user_agent=user_agent,
            ip_address=ip_address,
        )
        if not ok or payload is None:
            _clear_refresh_cookie(response)
            return AuthResponse(ok=False, message=message)
        _set_refresh_cookie(response, payload["refresh_token"])
        return AuthResponse(
            ok=True,
            message=message,
            token=payload["access_token"],
            access_token=payload["access_token"],
            token_type="Bearer",
            expires_in=payload["expires_in"],
            user_id=payload["user_id"],
            username=payload["username"],
        )
    except Exception as exc:
        logger.error("Refresh failed: %s", exc)
        _clear_refresh_cookie(response)
        return AuthResponse(ok=False, message="会话刷新失败")


@router.post("/logout")
def auth_logout(
    response: Response,
    svc: ServiceContainer = Depends(get_services),
    refresh_token: str | None = Cookie(default=None, alias=settings.auth_cookie_name),
) -> dict:
    try:
        if refresh_token:
            svc.user.revoke_refresh_token(refresh_token)
    finally:
        _clear_refresh_cookie(response)
    return {"ok": True, "message": "已退出登录"}


@router.get("/me", response_model=UserProfileResponse)
def auth_me(
    user: dict = Depends(require_user),
    svc: ServiceContainer = Depends(get_services),
) -> UserProfileResponse:
    profile = svc.user.get_profile(user["user_id"])
    return UserProfileResponse(
        ok=True,
        user_id=user["user_id"],
        username=user["username"],
        created_at=profile["created_at"] if profile else None,
    )


@router.patch("/profile", response_model=UserProfileResponse)
def auth_update_profile(
    payload: UpdateProfileRequest,
    user: dict = Depends(require_user),
    svc: ServiceContainer = Depends(get_services),
) -> UserProfileResponse:
    ok, message = svc.user.update_username(user["user_id"], payload.username)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    profile = svc.user.get_profile(user["user_id"])
    if profile is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserProfileResponse(
        ok=True,
        user_id=profile["user_id"],
        username=profile["username"],
        created_at=profile["created_at"],
    )
