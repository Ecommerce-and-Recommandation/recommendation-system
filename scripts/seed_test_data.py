import asyncio
import random
import sys
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

# Add current directory to path
sys.path.append(os.getcwd())

from app.database import async_session
from app.db_models import User, Product, Order, OrderItem
from app.services.auth import hash_password

USERS_TO_CREATE = 5
ORDERS_PER_USER = (3, 8) # Từ 3 đến 8 đơn hàng mỗi user

async def seed_data():
    async with async_session() as session:
        # Lấy danh sách sản phẩm
        result = await session.execute(select(Product))
        products = result.scalars().all()
        if not products:
            print("Không tìm thấy sản phẩm nào! Vui lòng chạy full_import.py trước.")
            return

        credentials = []

        print("Creating Users and Orders...")
        for i in range(1, USERS_TO_CREATE + 1):
            email = f"testuser{i}@shop.com"
            raw_password = f"password{i}123"
            
            user = User(
                email=email,
                password_hash=hash_password(raw_password),
                name=f"Test User {i}",
                phone=f"091234567{i}",
                address=f"So {i} Duong Test, TP Thu Duc, HCM",
                country="Vietnam",
                is_admin=False
            )
            session.add(user)
            await session.flush() # Để lấy id user
            
            credentials.append({
                "email": email,
                "password": raw_password,
                "name": user.name
            })

            # Random số lượng đơn hàng cho user này
            num_orders = random.randint(ORDERS_PER_USER[0], ORDERS_PER_USER[1])
            for _ in range(num_orders):
                num_items = random.randint(1, 5) # 1-5 loại sản phẩm trong đơn
                order_products = random.sample(products, num_items)
                
                # Tính tổng tiền
                total_amount = sum(p.price * random.randint(1, 3) for p in order_products)
                
                order = Order(
                    user_id=user.id,
                    total_amount=round(total_amount, 2),
                    discount_amount=0.0,
                    status="COMPLETED",
                    shipping_address=user.address,
                    phone=user.phone,
                    # Ngày mua random trong 30 ngày đổ lại
                    created_at=datetime.now(timezone.utc) - timedelta(days=random.randint(0, 30))
                )
                session.add(order)
                await session.flush()
                
                for p in order_products:
                    qty = random.randint(1, 3)
                    order_item = OrderItem(
                        order_id=order.id,
                        product_id=p.id,
                        quantity=qty,
                        price_at_time=p.price
                    )
                    session.add(order_item)
                    
                    # Update purchase_count cho sản phẩm
                    p.purchase_count += qty
                    
        await session.commit()
        print(f"Success: Created {USERS_TO_CREATE} users and related orders.")

        # Viết credentials ra file ngoài thư mục gốc
        out_path = Path(os.getcwd()).parent / "test_accounts.md"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("# Tài Khoản Test (Seed Data)\n\n")
            f.write("Dùng các tài khoản này để đăng nhập và test AI Promotion.\n\n")
            f.write("| Name | Email | Password |\n")
            f.write("| --- | --- | --- |\n")
            for cred in credentials:
                f.write(f"| {cred['name']} | {cred['email']} | {cred['password']} |\n")
        
        print(f"Credentials saved to: {out_path}")

if __name__ == "__main__":
    asyncio.run(seed_data())
