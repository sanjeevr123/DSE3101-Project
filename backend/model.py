"""
HDB Resale Price Prediction - Hybrid Linear + XGBoost Model
Handles model training, persistence, and inference.
"""

import numpy as np
import pandas as pd
import pickle
import os
from math import radians, sin, cos, sqrt, atan2
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error
import xgboost as xgb

# ── Paths ────────────────────────────────────────────────────────────────────
DATA_PATH   = os.environ.get("HDB_DATA_PATH", "data/raw/HDB_full_resale_info.csv.gz")
MODEL_DIR   = os.environ.get("MODEL_DIR", "models")
MODEL_PATH  = os.path.join(MODEL_DIR, "hybrid_model.pkl")

# ── Feature definitions ──────────────────────────────────────────────────────
LINEAR_FEATURES = ["months_since_start", "floor_area_sqm", "remaining_lease"]

COLS_TO_DROP = ["address", "block", "street_name", "sold_year_month", "year", "month"]

COUNT_COLS_SUFFIX = "_count_1km"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fill_counts(df: pd.DataFrame) -> pd.DataFrame:
    count_cols = [c for c in df.columns if COUNT_COLS_SUFFIX in c]
    df[count_cols] = df[count_cols].fillna(0)
    return df


def _engineer_features(df: pd.DataFrame, min_year: int) -> pd.DataFrame:
    df = df.copy()
    df[["year", "month", "day"]] = (
        df["sold_year_month"].str.split("-", expand=True).astype(int)
    )
    df["months_since_start"] = (df["year"] - min_year) * 12 + df["month"]
    df["flat_age_at_sale"]   = df["sold_year"] - df["lease_commence_date"]
    df["log_price"]          = np.log(df["resale_price"])
    return df


# ── Training ─────────────────────────────────────────────────────────────────

def train_and_save(data_path: str = DATA_PATH, model_path: str = MODEL_PATH):
    """
    Load data, train the hybrid model, persist everything needed for inference.
    Returns a dict with evaluation metrics.
    """
    print("Loading data …")
    raw = pd.read_csv(data_path)
    raw = raw[raw["sold_year"] > 2010].copy()

    raw = _fill_counts(raw)

    min_year = raw["sold_year_month"].str[:4].astype(int).min()

    df = _engineer_features(raw, min_year)

    # Drop high-cardinality / redundant columns
    df = df.drop(columns=[c for c in COLS_TO_DROP if c in df.columns])

    # Encode categoricals + persist encoders
    cat_cols = df.select_dtypes(include=["object", "str"]).columns.tolist()
    encoders: dict[str, LabelEncoder] = {}
    for col in cat_cols:
        le = LabelEncoder()
        df[col] = le.fit_transform(df[col].astype(str))
        encoders[col] = le

    tree_features = [c for c in df.columns if c not in ["resale_price", "log_price"]]

    X_train, X_test, y_train_log, y_test_log = train_test_split(
        df[tree_features], df["log_price"], test_size=0.2, random_state=42
    )
    y_test_actual = np.exp(y_test_log)

    # ── Linear base ──────────────────────────────────────────────────────────
    print("Training linear base …")
    linear_model = LinearRegression()
    linear_model.fit(X_train[LINEAR_FEATURES], y_train_log)

    train_base_preds = linear_model.predict(X_train[LINEAR_FEATURES])
    train_residuals  = y_train_log - train_base_preds

    # ── XGBoost on residuals ─────────────────────────────────────────────────
    print("Training XGBoost on residuals …")
    sample_weights = np.where(X_train["sold_year"] >= 2022, 2.0, 1.0)

    xgb_model = xgb.XGBRegressor(
        n_estimators=2000,
        learning_rate=0.03,
        max_depth=8,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=-1,
    )
    xgb_model.fit(X_train[tree_features], train_residuals, sample_weight=sample_weights)

    # ── Evaluate ─────────────────────────────────────────────────────────────
    test_base = linear_model.predict(X_test[LINEAR_FEATURES])
    test_resid = xgb_model.predict(X_test[tree_features])
    preds = np.exp(test_base + test_resid)

    mae  = mean_absolute_error(y_test_actual, preds)
    mape = mean_absolute_percentage_error(y_test_actual, preds) * 100
    print(f"  MAE : ${mae:,.2f}")
    print(f"  MAPE: {mape:.2f}%")

    # ── Persist ──────────────────────────────────────────────────────────────
    os.makedirs(MODEL_DIR, exist_ok=True)
    bundle = dict(
        linear_model=linear_model,
        xgb_model=xgb_model,
        encoders=encoders,
        tree_features=tree_features,
        cat_cols=cat_cols,
        min_year=min_year,
        # store medians/modes per town for fast defaults at inference time
        town_defaults=_compute_town_defaults(raw),
        global_medians=df[tree_features].median().to_dict(),
    )
    with open(model_path, "wb") as f:
        pickle.dump(bundle, f)
    print(f"Model saved → {model_path}")

    return {"mae": mae, "mape": mape}


def _compute_town_defaults(raw: pd.DataFrame) -> dict:
    """Pre-compute per-town mode/median values used at inference."""
    defaults = {}
    for town, grp in raw.groupby("town"):
        defaults[town] = {
            "storey_range":        grp["storey_range"].mode()[0],
            "flat_model":          grp["flat_model"].mode()[0],
            "lease_commence_date": int(grp["lease_commence_date"].median()),
            "storey_category":     grp["storey_category"].mode()[0] if "storey_category" in grp else "Mid",
            "region":              grp["region"].mode()[0] if "region" in grp else "Central",
            "is_mature_estate":    int(grp["is_mature_estate"].mode()[0]),
        }
    return defaults


# ── Inference ────────────────────────────────────────────────────────────────

class HDBPredictor:
    """Loads a persisted model bundle and exposes predict()."""

    def __init__(self, model_path: str = MODEL_PATH):
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Model not found at {model_path}. Run train_and_save() first."
            )
        with open(model_path, "rb") as f:
            self._bundle = pickle.load(f)

    # -- public ---------------------------------------------------------------

    def predict(
        self,
        town: str,
        flat_type: str,
        floor_area_sqm: float,
        sold_year: int,
        sold_month: int,
        listing_premium: float = 1.05,
    ) -> dict:
        """
        Returns:
            {
                "transacted_price": float,   # model's best estimate of actual sale price
                "asking_price":     float,   # transacted * listing_premium
            }
        """
        b = self._bundle

        # ── defaults for unknowns ────────────────────────────────────────────
        td = b["town_defaults"].get(town, b["town_defaults"][next(iter(b["town_defaults"]))])

        lc_date      = td["lease_commence_date"]
        flat_age     = sold_year - lc_date
        remaining    = 99 - flat_age
        months_since = (sold_year - b["min_year"]) * 12 + sold_month

        row = {
            "town":                 town,
            "flat_type":            flat_type,
            "storey_range":         td["storey_range"],
            "floor_area_sqm":       floor_area_sqm,
            "flat_model":           td["flat_model"],
            "lease_commence_date":  lc_date,
            "sold_year":            sold_year,
            "remaining_lease":      remaining,
            "flat_age_at_sale":     flat_age,
            "months_since_start":   months_since,
            "storey_category":      td["storey_category"],
            "region":               td["region"],
            "is_mature_estate":     td["is_mature_estate"],
        }

        # fill any remaining tree features from global medians
        for col in b["tree_features"]:
            if col not in row:
                row[col] = b["global_medians"].get(col, 0)

        df_in = pd.DataFrame([row])[b["tree_features"]]

        # ── encode categoricals ───────────────────────────────────────────────
        for col in b["cat_cols"]:
            if col not in df_in.columns:
                continue
            le: LabelEncoder = b["encoders"][col]
            val = str(df_in.at[0, col])
            if val in le.classes_:
                df_in[col] = le.transform([val])
            else:
                # unseen category → use most frequent from training
                df_in[col] = le.transform([le.classes_[0]])

        # ── predict ───────────────────────────────────────────────────────────
        base_log = b["linear_model"].predict(df_in[LINEAR_FEATURES])[0]
        resid    = b["xgb_model"].predict(df_in[b["tree_features"]])[0]
        transacted_price = float(np.exp(base_log + resid))
        asking_price     = round(transacted_price * listing_premium, 2)
        transacted_price = round(transacted_price, 2)

        return {
            "transacted_price": transacted_price,
            "asking_price":     asking_price,
        }


# ── CLI entry ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    metrics = train_and_save()
    print(metrics)
