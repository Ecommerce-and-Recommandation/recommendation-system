import asyncio
import sys
import os
sys.path.append(os.getcwd())

from sqlalchemy import select
from app.database import async_session
from app.db_models import Product

# Expanded Category Rules
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

async def patch_categories():
    print("--- Starting Category Patch ---")
    async with async_session() as db:
        result = await db.execute(select(Product))
        products = result.scalars().all()
        
        updated = 0
        distribution = {}
        
        for p in products:
            new_cat = detect_category(p.description) # descriptions usually contain the raw text padded
            # Wait, the description we saved earlier was:
            # "High quality {clean_name(raw_desc).lower()} – perfect for gifts or home use."
            # So the description contains the raw text inside it. 
            # Or we can just use the product 'name'.
            combined_text = p.name.lower()
            
            # Recalculate
            new_cat_from_name = "Other"
            for category, keywords in CATEGORY_RULES:
                if any(kw in combined_text for kw in keywords):
                    new_cat_from_name = category
                    break

            if p.category != new_cat_from_name:
                p.category = new_cat_from_name
                updated += 1
                
            distribution[new_cat_from_name] = distribution.get(new_cat_from_name, 0) + 1

        print(f"--- Updating {updated} products... ---")
        await db.commit()
        
        print("\n=== New Category Distribution ===")
        for k, v in sorted(distribution.items(), key=lambda item: item[1], reverse=True):
            print(f"{k}: {v}")

if __name__ == "__main__":
    asyncio.run(patch_categories())
