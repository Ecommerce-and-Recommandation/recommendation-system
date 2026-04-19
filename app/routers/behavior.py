"""Behavior tracking + ML-powered recommendations router."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.db_models import BehaviorEvent, Product, User
from app.services.auth import get_current_user
from app.services.behavior_engine import compute_rfm_from_behavior, get_recommendation_sources
from app.services.predictor import predict_purchase, recommend_products
from app.schemas.models import CustomerFeatures

router = APIRouter()


class TrackEvent(BaseModel):
    event_type: str  # view, add_to_cart, remove_from_cart, search, click_recommendation
    product_id: int | None = None
    duration_seconds: float | None = None
    metadata: dict | None = None


class TrackBatchRequest(BaseModel):
    events: list[TrackEvent]


@router.post("/behavior/track")
async def track_events(
    body: TrackBatchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Batch-save behavior events from the frontend tracker."""
    saved = 0
    for evt in body.events:
        # Sanitize: product_id=0 or negative → NULL (no FK violation)
        pid = evt.product_id if evt.product_id and evt.product_id > 0 else None
        db.add(BehaviorEvent(
            user_id=user.id,
            event_type=evt.event_type,
            product_id=pid,
            duration_seconds=evt.duration_seconds,
            metadata_json=evt.metadata,
        ))
        saved += 1
    await db.commit()
    return {"saved": saved}


@router.get("/behavior/recommendations")
async def get_recommendations(
    current_product_id: int | None = Query(None, description="Product currently being viewed"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Multi-source ML recommendations.

    Gathers recommendation sources from:
    1. Currently viewed product
    2. Products viewed >5 seconds
    3. Top 5 recent cart items
    4. Search history matches

    For each source, runs KNN → collects similar products → blends & deduplicates.
    """
    sources = await get_recommendation_sources(user.id, db, current_product_id)

    if not sources:
        # Fallback: popular products
        result = await db.execute(
            select(Product)
            .where(Product.in_stock.is_(True))
            .order_by(Product.purchase_count.desc())
            .limit(10)
        )
        products = result.scalars().all()
        return {
            "source": "popular",
            "source_products": [],
            "recommendations": [_product_to_rec(p, 0) for p in products],
        }

    # ── Run KNN for each source, blend results (ROUND ROBIN DIVERSITY) ──────────
    source_codes = {s["stock_code"] for s in sources}
    all_source_candidates = []

    for src in sources:
        # Get enough candidates to ensure some non-duplicates
        knn_result = recommend_products(src["stock_code"], top_k=30)
        if knn_result is None:
            continue

        candidates = []
        for rec in knn_result["recommendations"]:
            code = rec["stock_code"]
            # Don't recommend source products themselves
            if code in source_codes:
                continue

            candidates.append({
                "stock_code": code,
                "score": rec["similarity"] * src["weight"],
                "raw_similarity": rec["similarity"],
                "from_source": src["source"],
                "src_weight": src["weight"]
            })
            
        if candidates:
            # Sort candidates internally by absolute score
            candidates.sort(key=lambda x: x["score"], reverse=True)
            all_source_candidates.append(candidates)

    # Sort the source "queues" by their original weight, so recent/current views pick first
    all_source_candidates.sort(key=lambda q: q[0]["src_weight"] if q else 0, reverse=True)

    ranked = []
    seen = set()
    idx = 0
    
    # Interleave 1 from source A, 1 from B, 1 from C...
    while True:
        added_in_round = False
        for queue in all_source_candidates:
            # Find the next unseen item in this queue
            local_idx = idx
            while local_idx < len(queue):
                item = queue[local_idx]
                if item["stock_code"] not in seen:
                    ranked.append(item)
                    seen.add(item["stock_code"])
                    added_in_round = True
                    break # Move to next queue
                local_idx += 1
                
        idx += 1
        if not added_in_round or len(ranked) >= 40:
            break

    # Enrich with DB product info — ONLY include products that exist in our DB
    enriched = []
    for item in ranked:
        if len(enriched) >= 20:
            break
        result = await db.execute(
            select(Product).where(Product.stock_code == item["stock_code"])
        )
        p = result.scalar_one_or_none()
        if p:
            enriched.append({
                "id": p.id,
                "stock_code": p.stock_code,
                "name": p.name,
                "price": p.price,
                "image_url": p.image_url,
                "category": p.category,
                "similarity": item["raw_similarity"],
                "source": item["from_source"],
            })
        # Skip products not in DB (KNN knows 4499 but we only have 100)

    return {
        "source": "multi_knn",
        "source_products": [
            {"stock_code": s["stock_code"], "weight": s["weight"], "from": s["source"]}
            for s in sources
        ],
        "recommendations": enriched,
    }


@router.get("/behavior/profile")
async def get_behavior_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compute RFM features from behavior -> RF predict + K-Means segment."""
    rfm = await compute_rfm_from_behavior(user.id, db)
    features = CustomerFeatures(**rfm)

    try:
        prediction = predict_purchase(features)
    except Exception:
        prediction = {"will_purchase": False, "probability": 0, "segment_id": 0, "segment_name": "Unknown", "show_promotion": False, "promotion_message": None}

    return {
        "rfm_features": rfm,
        "prediction": prediction,
    }


def _product_to_rec(p: Product, similarity: float) -> dict:
    return {
        "id": p.id,
        "stock_code": p.stock_code,
        "name": p.name,
        "price": p.price,
        "image_url": p.image_url,
        "category": p.category,
        "similarity": similarity,
        "source": "popular",
    }
