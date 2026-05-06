import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

DATABASE_URL = "postgresql+asyncpg://postgres:123456@localhost:5432/ecommerce_ml"

async def fix():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        await conn.execute(text("SELECT setval('users_id_seq', (SELECT MAX(id) FROM users));"))
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(fix())
