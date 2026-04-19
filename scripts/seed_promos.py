import asyncio
import sys
import os
sys.path.append(os.getcwd())

from sqlalchemy import select
from app.database import async_session
from app.db_models import Promotion

async def seed_promos():
    async with async_session() as db:
        promos = [
            Promotion(code="GIAM10P", discount_type="PERCENTAGE", discount_value=10, min_order_amount=50.0),
            Promotion(code="GIAM20TRUC", discount_type="FIXED_AMOUNT", discount_value=20, min_order_amount=80.0),
            Promotion(code="NEWBIE50", discount_type="PERCENTAGE", discount_value=50, min_order_amount=0.0, target_audience="NEW_USER"),
        ]
        count = 0
        for p in promos:
            res = await db.execute(select(Promotion).where(Promotion.code == p.code))
            if not res.scalar_one_or_none():
                db.add(p)
                count += 1
        
        await db.commit()
        print(f"Seeded {count} promotions.")

if __name__ == "__main__":
    asyncio.run(seed_promos())
