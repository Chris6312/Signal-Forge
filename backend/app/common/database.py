import logging
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.common.config import settings

logger = logging.getLogger(__name__)

_async_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

# NullPool: every AsyncSessionLocal() opens a fresh asyncpg connection bound to
# the *current* running event loop and closes it on exit.  This makes the engine
# safe across worker threads that each own their own event loop — no connection
# is ever shared across loops.
engine = create_async_engine(_async_url, poolclass=NullPool, echo=False)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def init_db():
    from app.common.models.base import Base
    import app.common.models.watchlist  # noqa
    import app.common.models.position   # noqa
    import app.common.models.order      # noqa
    import app.common.models.ledger     # noqa
    import app.common.models.audit      # noqa

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables verified/created")


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
