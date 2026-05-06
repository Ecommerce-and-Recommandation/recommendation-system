import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

DATABASE_URL = "postgresql+asyncpg://postgres:123456@localhost:5432/ecommerce_ml"

async def migrate():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        print("Migrating users table...")
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(20);"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS address VARCHAR(255);"))
        print("Migrating orders table...")
        await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS shipping_address VARCHAR(255);"))
        await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS phone VARCHAR(20);"))
        print("Migration complete!")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(migrate())
