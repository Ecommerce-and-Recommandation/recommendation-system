"""Purchase prediction router."""

from fastapi import APIRouter, HTTPException

from app.schemas.models import (
    CustomerFeatures,
    ModelInfoResponse,
    PredictionResponse,
)
from app.services.predictor import get_model_info, predict_purchase

router = APIRouter()


@router.post("/predict/purchase", response_model=PredictionResponse)
async def predict(features: CustomerFeatures):
    """Predict whether a customer will return to purchase within 30 days."""
    try:
        result = predict_purchase(features)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/info", response_model=ModelInfoResponse)
async def models_info():
    """Return metrics and metadata for all loaded models."""
    return get_model_info()
