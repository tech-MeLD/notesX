import asyncpg
from fastapi import Request

from app.core.config import settings


async def create_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        command_timeout=30,
    )


def get_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.db_pool
