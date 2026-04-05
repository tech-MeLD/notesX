import socket

import asyncpg
from fastapi import Request

from app.core.config import settings


async def create_pool() -> asyncpg.Pool:
    try:
        return await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
            command_timeout=30,
        )
    except socket.gaierror as error:
        raise RuntimeError(
            "Unable to resolve the database host from DATABASE_URL. "
            "If you are using Supabase, prefer the session pooler connection string from Dashboard > Connect, "
            "especially on Windows or IPv4-only environments."
        ) from error


def get_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.db_pool
