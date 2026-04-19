"""Full import script: Truncate current products and import all 4499 items from CSV."""
import asyncio
import csv
import sys
import os
from pathlib import Path
from sqlalchemy import text, select

# Add current directory to path
sys.path.append(os.getcwd())

from app.database import Base, engine, async_session
from app.db_models import Product

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("Candles & Lighting", ["candle", "t-light", "tlight", "lantern", "lamp", "light holder", "tea light"]),
    ("Kitchen & Dining", ["mug", "cup", "plate", "bowl", "jug", "coaster", "napkin", "cutlery", "spoon", "fork", "kitchen", "apron", "oven", "baking", "cake", "glass"]),
    ("Bags, Purses & Wallets", ["purse", "wallet", "handbag", "tote", "shopping bag", "clutch", "pouch", "bag"]),
    ("Gifts & Celebration", ["birthday", "party", "balloon", "wrap", "gift", "celebration", "inflatable", "confetti", "bunting", "garland", "ribbon", "card"]),
    ("Stationery", ["pen", "pencil", "notebook", "postcard", "memo", "journal", "sticky", "eraser", "pad", "envelope", "postal", "album", "photo", "sticker", "tape", "scissor", "glue", "ruler", "measure", "folder", "organizer", "address book", "to do list", "rubber", "writing", "set"]),
    ("Home Decor", ["frame", "mirror", "clock", "wall", "sign", "hook", "door", "plaque", "star", "heart", "angel", "decoration", "cushion", "cover"]),
    ("Storage & Tins", ["tin", "storage", "jar", "container", "box", "basket", "tray"]),
    ("Garden", ["garden", "plant", "flower", "pot", "planter", "watering", "seed"]),
    ("Toys & Games", ["toy", "game", "puzzle", "doll", "teddy", "bear", "rocket", "dinosaur", "robot", "bingo"]),
    ("Christmas", ["christmas", "xmas", "snowman", "santa", "reindeer", "advent", "tree"]),
    ("Vintage & Retro", ["vintage", "retro", "shabby", "chic", "antique"]),
    ("Wellness & Fragrance", ["incense", "fragrance", "scent", "oil burner", "aromatherapy", "potpourri", "lavender", "jasmine", "vanilla", "opium", "sandalwood"]),
    ("Travel & Accessories", ["passport", "luggage", "travel", "tag", "sky", "first class", "airline", "airport", "map", "globe", "umbrella", "parasol"]),
]

def detect_category(description: str) -> str:
    desc_lower = description.lower()
    for category, keywords in CATEGORY_RULES:
        if any(kw in desc_lower for kw in keywords):
            return category
    return "Other"

def clean_name(raw: str) -> str:
    words = raw.strip().split()
    return " ".join(w.capitalize() if w.isupper() or len(w) > 1 else w for w in words)

async def full_import():
    print("--- Starting Full Dataset Import ---")
    
    csv_path = DATA_DIR / "product_lookup.csv"
    if not csv_path.exists():
        print(f"!!! Error: {csv_path} not found!")
        return

    async with async_session() as session:
        # 1. Truncate products (CASCADE handles behavior_events if they still exist)
        print("--- Truncating existing products...")
        await session.execute(text("TRUNCATE TABLE products RESTART IDENTITY CASCADE"))
        await session.commit()

        # 2. Read CSV
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            raw_products = list(reader)

        print(f"--- Found {len(raw_products)} products in CSV. Starting bulk insert...")

        # 3. Batch insert
        batch_size = 500
        total_inserted = 0
        
        for i in range(0, len(raw_products), batch_size):
            batch = raw_products[i:i+batch_size]
            db_batch = []
            
            for row in batch:
                raw_desc = row["description"].strip()
                category = detect_category(raw_desc)
                price = round(float(row["avg_price"]), 2)
                if price <= 0:
                    price = 1.99
                
                stock_code = row["StockCode"]
                db_batch.append(Product(
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
            
            session.add_all(db_batch)
            await session.commit()
            total_inserted += len(db_batch)
            print(f"--- Inserted {total_inserted}/{len(raw_products)} products...")

    print(f"--- SUCCESS: Imported {total_inserted} products.")

if __name__ == "__main__":
    asyncio.run(full_import())
