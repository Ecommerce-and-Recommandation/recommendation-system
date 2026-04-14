"""Product recommendation router."""

from fastapi import APIRouter, HTTPException, Query

from app.schemas.models import RecommendationResponse
from app.services.predictor import recommend_products

router = APIRouter()


@router.get("/recommend/{stock_code}", response_model=RecommendationResponse)
async def recommend(stock_code: str, top_k: int = Query(10, ge=1, le=20)):
    """Return top-K similar products for a given StockCode."""
    result = recommend_products(stock_code, top_k)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Product '{stock_code}' not found")
    return result
