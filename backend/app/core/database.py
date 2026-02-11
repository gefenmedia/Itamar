from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

engine = create_async_engine(settings.database_url, echo=False, pool_size=5, max_overflow=10)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Create all tables. For production, use Alembic migrations instead."""
    async with engine.begin() as conn:
        await conn.execute(
            __import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS vector")
        )
        await conn.execute(
            __import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        )
        await conn.run_sync(Base.metadata.create_all)
