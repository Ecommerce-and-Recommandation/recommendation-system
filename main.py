"""FastAPI Backend – E-commerce ML Models

Serves 3 interconnected ML models:
- Random Forest: Purchase behavior prediction
- K-Means + PCA: Customer segmentation
- KNN: Product recommendation (content-based filtering)

Plus: Auth, Products, Cart, Behavior tracking
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routers import prediction, recommendation, segmentation
from app.routers import auth, products, cart, behavior
from app.services.model_loader import model_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load ML models + init DB on startup, cleanup on shutdown."""
    model_store.load_all()
    await init_db()
    yield
    model_store.unload_all()


app = FastAPI(
    title="E-commerce ML API",
    description="Gợi ý sản phẩm, phân khúc khách hàng, dự đoán hành vi mua hàng",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Shop APIs ────────────────────────────────────────────
app.include_router(auth.router, prefix="/api", tags=["Auth"])
app.include_router(products.router, prefix="/api", tags=["Products"])
app.include_router(cart.router, prefix="/api", tags=["Cart"])
app.include_router(behavior.router, prefix="/api", tags=["Behavior Tracking"])

# ── Admin / ML APIs ─────────────────────────────────────
app.include_router(prediction.router, prefix="/api", tags=["Purchase Prediction"])
app.include_router(recommendation.router, prefix="/api", tags=["Product Recommendation"])
app.include_router(segmentation.router, prefix="/api", tags=["Customer Segmentation"])


@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "models_loaded": model_store.is_loaded,
        "models": list(model_store.models.keys()) if model_store.is_loaded else [],
    }
