import asyncio
import sys
import os
sys.path.append(os.getcwd())

from sqlalchemy import text
from app.database import async_session

async def sample_other():
    async with async_session() as db:
        r = await db.execute(text("SELECT name FROM products WHERE category = 'Other' LIMIT 100"))
        names = [row[0] for row in r.fetchall()]
        print("\n".join(names))

if __name__ == "__main__":
    asyncio.run(sample_other())
