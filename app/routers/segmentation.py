"""Customer segmentation router."""

from fastapi import APIRouter

from app.schemas.models import (
    CustomerFeatures,
    SegmentInfo,
    SegmentOverviewResponse,
)
from app.services.predictor import get_segment_for_customer, get_segments_overview

router = APIRouter()


@router.post("/segment/customer", response_model=SegmentInfo)
async def segment_customer(features: CustomerFeatures):
    """Determine which segment a customer belongs to based on RFM features."""
    return get_segment_for_customer(features)


@router.get("/segments/overview", response_model=SegmentOverviewResponse)
async def segments_overview():
    """Return an overview of all customer segments and their distribution."""
    return get_segments_overview()
