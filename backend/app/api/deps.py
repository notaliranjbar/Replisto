from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import get_db
from app.core.queue import Queue
from app.core.security import TokenError, decode_token
from app.models import Shop, User
from app.services.instagram import InstagramClient
from app.services.llm import LLMClient

_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_signed_in_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        user_id = decode_token(credentials.credentials, "access")
    except TokenError:
        raise unauthorized from None

    user = await db.scalar(select(User).where(User.id == user_id).options(selectinload(User.shop)))
    if user is None or not user.is_active:
        raise unauthorized
    return user


# Signed in, email possibly not verified yet: only for what the "verify your email" screen needs.
SignedInUser = Annotated[User, Depends(get_signed_in_user)]


async def get_optional_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User | None:
    """The signed-in user if a valid token came with the request; otherwise a guest (None)."""
    if credentials is None:
        return None
    try:
        user_id = decode_token(credentials.credentials, "access")
    except TokenError:
        return None
    user = await db.get(User, user_id)
    return user if user is not None and user.is_active else None


OptionalUser = Annotated[User | None, Depends(get_optional_user)]


async def get_current_user(user: SignedInUser) -> User:
    if get_settings().require_verified_email and user.email_verified_at is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Please confirm your email first, using the link we sent you"
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_shop(user: CurrentUser) -> Shop:
    return user.shop


CurrentShop = Annotated[Shop, Depends(get_current_shop)]


def get_queue(request: Request) -> Queue:
    return request.app.state.queue


def get_instagram_client(request: Request) -> InstagramClient:
    return InstagramClient(request.app.state.http)


JobQueue = Annotated[Queue, Depends(get_queue)]
Instagram = Annotated[InstagramClient, Depends(get_instagram_client)]


def get_http(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


HttpClient = Annotated[httpx.AsyncClient, Depends(get_http)]


def get_llm(http: HttpClient) -> LLMClient:
    return LLMClient(http)


LLM = Annotated[LLMClient, Depends(get_llm)]
