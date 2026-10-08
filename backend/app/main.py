import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    account,
    auth,
    billing,
    conversations,
    dashboard,
    health,
    instagram,
    knowledge,
    products,
    teach,
    webhooks,
)
from app.core.config import get_settings
from app.core.monitoring import setup_monitoring
from app.core.queue import ArqQueue, InlineQueue

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_monitoring("api")
    app.state.http = httpx.AsyncClient(timeout=20)
    redis = None
    if settings.queue_backend == "inline":
        from app.worker import FUNCTIONS

        app.state.queue = InlineQueue(FUNCTIONS, {"http": app.state.http})
    else:
        redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        app.state.queue = ArqQueue(redis)
    yield
    await app.state.http.aclose()
    if redis is not None:
        await redis.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.2.0",
        lifespan=lifespan,
        # Keep interactive docs off the public internet in production.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(webhooks.router)
    api_prefix = "/api/v1"
    for module in (
        auth,
        account,
        instagram,
        knowledge,
        products,
        teach,
        conversations,
        dashboard,
        billing,
    ):
        app.include_router(module.router, prefix=api_prefix)
    return app


app = create_app()
