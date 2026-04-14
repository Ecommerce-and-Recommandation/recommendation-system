"""Behavior tracking + ML-powered recommendations router."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.db_models import BehaviorEvent, Product, User
from app.services.auth import get_current_user
from app.services.behavior_engine import compute_rfm_from_behavior, get_most_interacted_product
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
        db.add(BehaviorEvent(
            user_id=user.id,
            event_type=evt.event_type,
            product_id=evt.product_id,
            duration_seconds=evt.duration_seconds,
            metadata_json=evt.metadata,
        ))
        saved += 1
    await db.commit()
    return {"saved": saved}


@router.get("/behavior/recommendations")
async def get_recommendations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """ML-powered: find most-interacted product → KNN → similar products."""
    stock_code = await get_most_interacted_product(user.id, db)
    if stock_code is None:
        # Fallback: return popular products
        result = await db.execute(
            select(Product)
            .where(Product.in_stock.is_(True))
            .order_by(Product.purchase_count.desc())
            .limit(10)
        )
        products = result.scalars().all()
        return {
            "source": "popular",
            "source_product": None,
            "recommendations": [
                {
                    "id": p.id,
                    "stock_code": p.stock_code,
                    "name": p.name,
                    "price": p.price,
                    "image_url": p.image_url,
                    "category": p.category,
                    "similarity": 0,
                }
                for p in products
            ],
        }

    # Use KNN model
    knn_result = recommend_products(stock_code, top_k=10)
    if knn_result is None:
        return {"source": "popular", "source_product": stock_code, "recommendations": []}

    # Enrich with DB product info
    enriched = []
    for rec in knn_result["recommendations"]:
        result = await db.execute(
            select(Product).where(Product.stock_code == rec["stock_code"])
        )
        p = result.scalar_one_or_none()
        enriched.append({
            "id": p.id if p else 0,
            "stock_code": rec["stock_code"],
            "name": p.name if p else rec["stock_code"],
            "price": p.price if p else 0,
            "image_url": p.image_url if p else "",
            "category": p.category if p else "",
            "similarity": rec["similarity"],
        })

    return {
        "source": "knn",
        "source_product": stock_code,
        "recommendations": enriched,
    }


@router.get("/behavior/profile")
async def get_behavior_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compute RFM features from behavior → RF predict + K-Means segment."""
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
