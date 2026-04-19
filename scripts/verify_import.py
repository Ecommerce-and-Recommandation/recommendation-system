import asyncio
import sys
import os
sys.path.append(os.getcwd())

from sqlalchemy import text
from app.database import async_session

async def verify():
    async with async_session() as db:
        r = await db.execute(text("SELECT count(*) FROM products"))
        print(f"Total products in DB: {r.scalar()}")
        
        r2 = await db.execute(text("SELECT category, count(*) FROM products GROUP BY category ORDER BY count DESC"))
        print("Category distribution:")
        for row in r2.fetchall():
            print(f"  {row[0]}: {row[1]}")

if __name__ == "__main__":
    asyncio.run(verify())
