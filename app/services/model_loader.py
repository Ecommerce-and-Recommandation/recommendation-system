"""Centralized model loading.

Loads all .joblib artifacts once at startup and exposes them via a singleton.
"""

import json
from pathlib import Path

import joblib


_MODELS_DIR = Path(__file__).resolve().parents[2] / "models"


class ModelStore:
    """Singleton holding every loaded artifact."""

    def __init__(self) -> None:
        self.models: dict = {}
        self.configs: dict = {}
        self.is_loaded = False

    # ── public ──────────────────────────────────────────────

    def load_all(self) -> None:
        if self.is_loaded:
            return

        d = _MODELS_DIR

        # Random Forest
        self.models["rf"] = joblib.load(d / "random_forest_model.joblib")
        self.models["scaler_rfm"] = joblib.load(d / "scaler_rfm.joblib")

        # K-Means + PCA
        self.models["kmeans"] = joblib.load(d / "kmeans_model.joblib")
        self.models["pca"] = joblib.load(d / "pca_transformer.joblib")
        self.models["scaler_seg"] = joblib.load(d / "scaler_segmentation.joblib")

        # KNN
        self.models["knn"] = joblib.load(d / "knn_model.joblib")
        self.models["tfidf"] = joblib.load(d / "tfidf_vectorizer.joblib")
        self.models["scaler_product"] = joblib.load(d / "scaler_product.joblib")
        self.models["product_matrix"] = joblib.load(d / "product_features_matrix.joblib")

        # Label encoder
        self.models["le_country"] = joblib.load(d / "label_encoder_country.joblib")

        # Config / metadata JSONs
        self.configs["rf"] = _load_json(d / "rf_model_metadata.json")
        self.configs["seg"] = _load_json(d / "segmentation_config.json")
        self.configs["knn"] = _load_json(d / "knn_config.json")
        self.configs["product_mappings"] = _load_json(d / "product_mappings.json")

        self.is_loaded = True
        print(f"✅ Loaded {len(self.models)} model artifacts from {d}")

    def unload_all(self) -> None:
        self.models.clear()
        self.configs.clear()
        self.is_loaded = False

    # convenience accessors
    @property
    def rf(self):
        return self.models["rf"]

    @property
    def kmeans(self):
        return self.models["kmeans"]

    @property
    def pca(self):
        return self.models["pca"]

    @property
    def knn(self):
        return self.models["knn"]


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# Global singleton – imported everywhere
model_store = ModelStore()
