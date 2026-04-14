"""Seed database with demo user + top 100 products from product_lookup.csv."""

import asyncio
import csv
import re
from pathlib import Path

from app.database import Base, engine, async_session
from app.db_models import Product, User
from app.services.auth import hash_password

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

# ── Category auto-detection from product descriptions ────

CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("Candles & Lighting", ["candle", "t-light", "tlight", "lantern", "lamp", "light holder", "tea light"]),
    ("Kitchen & Dining", ["mug", "cup", "plate", "bowl", "jug", "coaster", "napkin", "cutlery", "spoon", "fork", "kitchen", "apron", "oven", "baking", "cake"]),
    ("Bags & Wrapping", ["bag", "gift bag", "wrap", "ribbon", "tissue", "box set"]),
    ("Stationery", ["pen", "pencil", "notebook", "card", "postcard", "memo", "journal", "sticky", "eraser", "pad"]),
    ("Home Decor", ["frame", "mirror", "clock", "wall", "sign", "hook", "door", "plaque", "bunting", "garland", "star", "heart", "angel", "decoration"]),
    ("Storage & Tins", ["tin", "storage", "jar", "container", "box", "basket", "tray"]),
    ("Garden", ["garden", "plant", "flower", "pot", "planter", "watering", "seed"]),
    ("Toys & Games", ["toy", "game", "puzzle", "doll", "teddy", "bear", "rocket", "dinosaur", "robot"]),
    ("Christmas", ["christmas", "xmas", "snowman", "santa", "reindeer", "advent"]),
    ("Vintage & Retro", ["vintage", "retro", "shabby", "chic", "antique"]),
]


def detect_category(description: str) -> str:
    desc_lower = description.lower()
    for category, keywords in CATEGORY_RULES:
        if any(kw in desc_lower for kw in keywords):
            return category
    return "Other"


def clean_name(raw: str) -> str:
    """Convert 'INFLATABLE POLITICAL GLOBE' → 'Inflatable Political Globe'."""
    words = raw.strip().split()
    return " ".join(w.capitalize() if w.isupper() or len(w) > 1 else w for w in words)


async def seed():
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        # ── Demo user ────────────────────────────
        existing = await session.execute(
            __import__("sqlalchemy").select(User).where(User.email == "demo@shop.com")
        )
        if existing.scalar_one_or_none() is None:
            session.add(User(
                email="demo@shop.com",
                password_hash=hash_password("demo1234"),
                name="Demo User",
                country="United Kingdom",
            ))
            print("[OK] Created demo user: demo@shop.com / demo1234")
        else:
            print("[INFO] Demo user already exists")

        # ── Products ─────────────────────────────
        csv_path = DATA_DIR / "product_lookup.csv"
        if not csv_path.exists():
            print(f"[ERROR] {csv_path} not found!")
            return

        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            products = list(reader)

        # Sort by purchase_count descending → take top 100
        products.sort(key=lambda r: int(r["purchase_count"]), reverse=True)
        top = products[:100]

        inserted = 0
        for i, row in enumerate(top):
            stock_code = row["StockCode"]
            existing_product = await session.execute(
                __import__("sqlalchemy").select(Product).where(Product.stock_code == stock_code)
            )
            if existing_product.scalar_one_or_none() is not None:
                continue

            raw_desc = row["description"].strip()
            category = detect_category(raw_desc)
            price = round(float(row["avg_price"]), 2)
            if price <= 0:
                price = 1.99

            session.add(Product(
                stock_code=stock_code,
                name=clean_name(raw_desc),
                description=f"High quality {clean_name(raw_desc).lower()} – perfect for gifts or home use.",
                price=price,
                image_url=f"https://picsum.photos/seed/{stock_code}/400/400",
                category=category,
                in_stock=True,
                purchase_count=int(row["purchase_count"]),
                num_customers=int(row["num_customers"]),
            ))
            inserted += 1

        await session.commit()
        print(f"[OK] Seeded {inserted} products (top 100 by purchase_count)")


if __name__ == "__main__":
    asyncio.run(seed())
