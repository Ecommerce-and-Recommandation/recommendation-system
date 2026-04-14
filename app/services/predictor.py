"""Core prediction / recommendation logic.

Thin wrappers around the loaded sklearn artifacts so routers stay slim.
"""

import numpy as np
import pandas as pd
from scipy.sparse import hstack, csr_matrix

from app.services.model_loader import model_store
from app.schemas.models import CustomerFeatures

PROMOTION_THRESHOLD = 0.7

# Feature order must match training
RF_FEATURE_COLS: list[str] = []  # populated after models load


def _rf_feature_cols() -> list[str]:
    return model_store.configs["rf"]["feature_columns"]


# ── Segmentation helpers ────────────────────────────────


def _get_segment(rfm_values: np.ndarray) -> tuple[int, str]:
    """Run RFM values through PCA → K-Means and return (id, name)."""
    seg_features = model_store.configs["seg"]["rfm_features"]
    # rfm_values is already a 1-D array aligned to seg_features
    scaled = model_store.models["scaler_seg"].transform(rfm_values.reshape(1, -1))
    pca_result = model_store.pca.transform(scaled)
    segment_id = int(model_store.kmeans.predict(pca_result)[0])
    segment_name = model_store.configs["seg"]["segment_names"].get(
        str(segment_id), f"Cluster {segment_id}"
    )
    return segment_id, segment_name


# ── Purchase prediction ─────────────────────────────────


def predict_purchase(features: CustomerFeatures) -> dict:
    """Full pipeline: encode country → segment → RF predict."""
    le = model_store.models["le_country"]
    country_encoded = _safe_label_encode(le, features.country)

    # Build RFM array for segmentation (order must match seg config)
    seg_features = model_store.configs["seg"]["rfm_features"]
    feature_map = _features_to_dict(features, country_encoded)
    rfm_array = np.array([feature_map[f] for f in seg_features])
    segment_id, segment_name = _get_segment(rfm_array)

    # Build full RF feature vector
    rf_cols = _rf_feature_cols()
    feature_map["segment_id"] = segment_id
    feature_map["country_encoded"] = country_encoded

    X = np.array([[feature_map[col] for col in rf_cols]])
    prob = float(model_store.rf.predict_proba(X)[0][1])
    will_purchase = prob >= 0.5

    show_promo = prob >= PROMOTION_THRESHOLD
    promo_msg = None
    if show_promo:
        promo_msg = "🎁 Ưu đãi đặc biệt dành riêng cho bạn! Giảm 15% cho đơn hàng tiếp theo."

    return {
        "will_purchase": will_purchase,
        "probability": round(prob, 4),
        "segment_id": segment_id,
        "segment_name": segment_name,
        "show_promotion": show_promo,
        "promotion_message": promo_msg,
    }


# ── Product recommendation ──────────────────────────────


def recommend_products(stock_code: str, top_k: int = 10) -> dict | None:
    mappings = model_store.configs["product_mappings"]
    stock_to_idx = mappings["stock_to_idx"]
    idx_to_stock = mappings["idx_to_stock"]

    if stock_code not in stock_to_idx:
        return None

    idx = stock_to_idx[stock_code]
    matrix = model_store.models["product_matrix"]

    distances, indices = model_store.knn.kneighbors(
        matrix[int(idx)].reshape(1, -1),
        n_neighbors=top_k + 1,
    )

    results = []
    for rank, (dist, neighbor_idx) in enumerate(
        zip(distances[0], indices[0]), start=0
    ):
        if rank == 0:
            continue
        neighbor_stock = idx_to_stock[str(neighbor_idx)]
        results.append(
            {
                "rank": rank,
                "stock_code": neighbor_stock,
                "description": "",
                "price": 0.0,
                "similarity": round(float(1 - dist), 4),
            }
        )

    return {"source_product": stock_code, "recommendations": results}


# ── Segmentation overview ───────────────────────────────


def get_segment_for_customer(features: CustomerFeatures) -> dict:
    le = model_store.models["le_country"]
    country_encoded = _safe_label_encode(le, features.country)
    feature_map = _features_to_dict(features, country_encoded)

    seg_features = model_store.configs["seg"]["rfm_features"]
    rfm_array = np.array([feature_map[f] for f in seg_features])
    segment_id, segment_name = _get_segment(rfm_array)

    return {
        "segment_id": segment_id,
        "segment_name": segment_name,
        "rfm_scores": {f: feature_map[f] for f in seg_features},
    }


def get_segments_overview() -> dict:
    cfg = model_store.configs["seg"]
    counts = cfg["segment_counts"]
    total = sum(counts.values())

    clusters = []
    for sid_str, count in counts.items():
        clusters.append(
            {
                "segment_id": int(sid_str),
                "segment_name": cfg["segment_names"].get(sid_str, f"Cluster {sid_str}"),
                "count": count,
                "percentage": round(count / total * 100, 1),
            }
        )

    clusters.sort(key=lambda c: c["count"], reverse=True)
    return {
        "total_customers": total,
        "n_clusters": cfg["n_clusters"],
        "silhouette_score": cfg["silhouette_score"],
        "clusters": clusters,
    }


def get_model_info() -> dict:
    rf_cfg = model_store.configs["rf"]
    return {
        "model_type": rf_cfg["model_type"],
        "version": rf_cfg.get("version", "v1"),
        "n_features": rf_cfg["n_features"],
        "metrics": rf_cfg["metrics"],
        "cv_f1_mean": rf_cfg["cv_f1_mean"],
        "cv_f1_std": rf_cfg["cv_f1_std"],
        "segmentation": {
            "n_clusters": model_store.configs["seg"]["n_clusters"],
            "silhouette_score": model_store.configs["seg"]["silhouette_score"],
        },
        "knn": {
            "total_products": model_store.configs["knn"]["total_products"],
            "hit_rate": model_store.configs["knn"]["hit_rate"],
        },
    }


# ── helpers ─────────────────────────────────────────────


def _features_to_dict(f: CustomerFeatures, country_encoded: int) -> dict:
    return {
        "recency": f.recency,
        "frequency": f.frequency,
        "monetary": f.monetary,
        "avg_order_value": f.avg_order_value,
        "avg_items_per_order": f.avg_items_per_order,
        "total_unique_products": f.total_unique_products,
        "avg_days_between_orders": f.avg_days_between_orders,
        "cancellation_rate": f.cancellation_rate,
        "days_since_first_purchase": f.days_since_first_purchase,
        "is_weekend_shopper": f.is_weekend_shopper,
        "favorite_hour": f.favorite_hour,
        "country_encoded": country_encoded,
        "avg_unit_price": f.avg_order_value,  # proxy
    }


def _safe_label_encode(le, value: str) -> int:
    try:
        return int(le.transform([value])[0])
    except ValueError:
        return 0
