import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

DATABASE_URL = "postgresql+asyncpg://postgres:123456@localhost:5432/ecommerce_ml"

async def clear_db():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        print("Starting DB cleanup...")
        
        # Xóa các bảng phụ thuộc trước (Foreign Key constraints)
        tables_to_clear = [
            "order_items",
            "promotion_usages",
            "orders",
            "cart_items",
            "behavior_events",
            "refresh_tokens",
            "promotions",
            "products"
        ]
        
        for table in tables_to_clear:
            print(f"Clearing table {table}...")
            await conn.execute(text(f"DELETE FROM {table};"))
        
        print("Removing users (except Admin)...")
        # Giữ lại admin (demo@shop.com) và các admin khác nếu có
        await conn.execute(text("DELETE FROM users WHERE is_admin = False;"))
        
        # Reset ID auto-increment (optional, but clean)
        for table in tables_to_clear + ["users"]:
            try:
                await conn.execute(text(f"ALTER SEQUENCE {table}_id_seq RESTART WITH 1;"))
            except Exception:
                pass # Skip if sequence doesn't exist
                
        print("Cleanup complete! Only Admin accounts remain.")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(clear_db())
