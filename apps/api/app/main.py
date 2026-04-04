from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.api.routes.rss import router as rss_router
from app.core.config import settings
from app.db.pool import create_pool
from app.services.scheduler import create_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await create_pool()
    app.state.db_pool = pool

    scheduler = None
    if settings.rss_scheduler_enabled:
        scheduler = create_scheduler(pool)
        scheduler.start()
        app.state.scheduler = scheduler

    try:
        yield
    finally:
        if scheduler:
            scheduler.shutdown(wait=False)
        await pool.close()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(rss_router, prefix=settings.api_prefix)
