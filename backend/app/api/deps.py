import hmac

from app.common.database import get_db
from app.common.config import settings
from fastapi import Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession


async def get_db_session() -> AsyncSession:
    async for session in get_db():
        yield session


async def require_admin(x_admin_token: str = Header(...)):
    if not hmac.compare_digest(x_admin_token, settings.ADMIN_API_TOKEN):
        raise HTTPException(status_code=403, detail="Invalid admin token")
