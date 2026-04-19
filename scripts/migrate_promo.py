import asyncio
import sys
import os
sys.path.append(os.getcwd())

from sqlalchemy import text
from app.database import engine

async def migrate():
    async with engine.begin() as conn:
        try:
            await conn.execute(text("ALTER TABLE promotions ADD COLUMN valid_until TIMESTAMP WITH TIME ZONE;"))
            print("Added valid_until")
        except Exception as e:
            print("valid_until might already exist:", e)
            
        try:
            await conn.execute(text("ALTER TABLE promotions ADD COLUMN target_audience VARCHAR(50) DEFAULT 'ALL';"))
            print("Added target_audience")
        except Exception as e:
            print("target_audience might already exist:", e)

if __name__ == "__main__":
    asyncio.run(migrate())
