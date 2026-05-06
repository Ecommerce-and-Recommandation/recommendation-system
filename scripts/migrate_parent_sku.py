import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

DATABASE_URL = "postgresql+asyncpg://postgres:123456@localhost:5432/ecommerce_ml"

async def migrate_parent_sku():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        print("Adding parent_sku column...")
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS parent_sku VARCHAR(50);"))
        
        print("Extracting parent_sku from stock_code...")
        # If stock_code is like 90214V, extract 90214
        await conn.execute(text("UPDATE products SET parent_sku = SUBSTRING(stock_code FROM '^[0-9]+') WHERE stock_code ~ '^[0-9]+[A-Za-z]+$';"))
        
        # For all other cases (e.g., pure numbers or special codes like POST), parent_sku = stock_code
        await conn.execute(text("UPDATE products SET parent_sku = stock_code WHERE parent_sku IS NULL;"))
        
        # Add index
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_products_parent_sku ON products (parent_sku);"))
        
        print("Migration complete!")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(migrate_parent_sku())
