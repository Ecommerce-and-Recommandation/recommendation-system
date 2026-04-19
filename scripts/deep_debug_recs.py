import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta
sys.path.append(os.getcwd())

from sqlalchemy import select, func, text
from app.database import async_session
from app.db_models import User, BehaviorEvent, CartItem, Product
from app.services.behavior_engine import get_recommendation_sources
from app.services.predictor import recommend_products
from app.services.model_loader import model_store

async def deep_debug_recs(email="demo@shop.com"):
    # CRITICAL: Load models
    model_store.load_all()
    
    async with async_session() as db:
        # Get user
        res = await db.execute(select(User).where(User.email == email))
        user = res.scalar_one_or_none()
        if not user:
            print(f"User {email} not found")
            return
        
        print(f"=== DEBUGGING RECOMMENDATIONS FOR USER ID: {user.id} ===")
        
        # 1. Check Cart
        res_cart = await db.execute(select(CartItem).where(CartItem.user_id == user.id))
        cart_items = res_cart.scalars().all()
        print(f"\nCart Items ({len(cart_items)}):")
        for ci in cart_items:
            p = await db.get(Product, ci.product_id)
            print(f"  - {p.stock_code if p else 'N/A'}: {p.name if p else 'N/A'} (Cat: {p.category if p else 'N/A'})")

        # 2. Get Sources from behavior_engine
        sources = await get_recommendation_sources(user.id, db)
        print(f"\nRecommendation Sources ({len(sources)}):")
        for s in sources:
            print(f"  - [{s['source']}] Stock: {s['stock_code']}, Weight: {s['weight']}")

        # 3. Simulate and Inspect Blending
        scored = {}
        source_codes = {s["stock_code"] for s in sources}
        
        print("\nTop 5 KNN results per source:")
        for src in sources:
            knn_res = recommend_products(src["stock_code"], top_k=20)
            if not knn_res:
                print(f"  [{src['source']}] {src['stock_code']} -> NO KNN RESULTS")
                continue
            
            print(f"  [{src['source']}] {src['stock_code']}:")
            for rec in knn_res["recommendations"][:5]:
                code = rec["stock_code"]
                similarity = rec["similarity"]
                weighted = similarity * src["weight"]
                print(f"    -> {code}: Similarity {similarity}, Weighted {weighted:.4f}")
                
                if code in source_codes:
                    continue
                
                if code not in scored or weighted > scored[code]["score"]:
                    scored[code] = {
                        "score": weighted,
                        "raw": similarity,
                        "src": src["source"]
                    }

        # 4. Final Blended result
        ranked = sorted(scored.items(), key=lambda x: x[1]["score"], reverse=True)
        print(f"\nFinal Blended Ranking (Top 10):")
        for i, (code, data) in enumerate(ranked[:10]):
            # Try to find in DB
            res_p = await db.execute(select(Product).where(Product.stock_code == code))
            p = res_p.scalar_one_or_none()
            p_info = f"{p.name} ({p.category})" if p else "NOT IN DB"
            print(f"  {i+1}. {code}: {data['score']:.4f} (Raw: {data['raw']}, From: {data['src']}) -> {p_info}")

if __name__ == "__main__":
    asyncio.run(deep_debug_recs())
