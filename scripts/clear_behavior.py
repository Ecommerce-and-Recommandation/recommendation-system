"""Script to clear all behavior events and reset user profiles."""
import asyncio
import sys
import os

# Add the current directory to sys.path to import app modules
sys.path.append(os.getcwd())

from sqlalchemy import text
from app.database import async_session

async def clear_behavior():
    print("--- Cleaning behavior_events table...")
    async with async_session() as db:
        try:
            # Using TRUNCATE with RESTART IDENTITY to reset the auto-increment counters
            # CASCADE ensures any dependent records (if any) are handled
            await db.execute(text("TRUNCATE TABLE behavior_events RESTART IDENTITY CASCADE"))
            await db.commit()
            print("--- Successfully cleared all behavior events.")
            print("--- Your recommendation engine is now a clean slate.")
        except Exception as e:
            await db.rollback()
            print(f"!!! Error clearing table: {e}")

if __name__ == "__main__":
    asyncio.run(clear_behavior())
