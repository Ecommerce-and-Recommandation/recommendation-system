import asyncio
import sys
import os
sys.path.append(os.getcwd())

from sqlalchemy import select, text
from app.database import async_session
from app.db_models import User
from app.services.auth import hash_password

async def create_admin():
    async with async_session() as db:
        try:
            await db.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE;"))
            await db.commit()
            print("Added is_admin column to users table.")
        except Exception as e:
            # It might already exist, rollback the failed transaction state
            await db.rollback()
            print(f"Column is_admin likely already exists: {e}")

        admin_email = "admin@shop.com"
        result = await db.execute(select(User).where(User.email == admin_email))
        admin = result.scalar_one_or_none()
        
        if admin:
            admin.is_admin = True
            print("Admin user updated.")
        else:
            admin = User(
                email=admin_email,
                name="System Admin",
                password_hash=hash_password("admin"),
                is_admin=True
            )
            db.add(admin)
            print("Admin user created (admin@shop.com / admin).")
            
        await db.commit()

if __name__ == "__main__":
    asyncio.run(create_admin())
