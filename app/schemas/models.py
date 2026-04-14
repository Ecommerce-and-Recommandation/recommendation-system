"""Pydantic schemas for API requests & responses."""

from pydantic import BaseModel, Field


# ── Purchase Prediction ──────────────────────────────────


class CustomerFeatures(BaseModel):
    """Raw behavioural features for a single customer."""

    recency: float = Field(..., description="Days since last purchase")
    frequency: float = Field(..., description="Number of unique orders")
    monetary: float = Field(..., description="Total spend (£)")
    avg_order_value: float = Field(..., description="Average order value")
    avg_items_per_order: float = Field(..., description="Average items per order")
    total_unique_products: float = Field(..., description="Distinct products purchased")
    avg_days_between_orders: float = Field(0, description="Average gap between orders")
    cancellation_rate: float = Field(0, description="Fraction of cancelled orders")
    days_since_first_purchase: float = Field(..., description="Customer age in days")
    is_weekend_shopper: float = Field(0, description="Weekend order ratio")
    favorite_hour: float = Field(12, description="Most frequent purchase hour")
    country: str = Field("United Kingdom", description="Customer country")


class PredictionResponse(BaseModel):
    will_purchase: bool
    probability: float
    segment_id: int
    segment_name: str
    show_promotion: bool
    promotion_message: str | None = None


# ── Product Recommendation ───────────────────────────────


class RecommendationItem(BaseModel):
    rank: int
    stock_code: str
    description: str
    price: float
    similarity: float


class RecommendationResponse(BaseModel):
    source_product: str
    recommendations: list[RecommendationItem]


# ── Customer Segmentation ───────────────────────────────


class SegmentInfo(BaseModel):
    segment_id: int
    segment_name: str
    rfm_scores: dict[str, float]


class ClusterOverview(BaseModel):
    segment_id: int
    segment_name: str
    count: int
    percentage: float


class SegmentOverviewResponse(BaseModel):
    total_customers: int
    n_clusters: int
    silhouette_score: float
    clusters: list[ClusterOverview]


# ── Model Info ───────────────────────────────────────────


class ModelMetrics(BaseModel):
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    roc_auc: float


class ModelInfoResponse(BaseModel):
    model_type: str
    version: str
    n_features: int
    metrics: ModelMetrics
    cv_f1_mean: float
    cv_f1_std: float
    segmentation: dict
    knn: dict
