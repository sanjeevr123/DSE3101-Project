"""
HDB Resale Price Prediction - RPI-Normalized XGBoost Model
Prediction logic mirrors the notebook's predict_price() exactly.
"""

import numpy as np
import pandas as pd
import pickle
import os
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error
import xgboost as xgb

# ── Paths ────────────────────────────────────────────────────────────────────
DATA_PATH     = os.environ.get("HDB_DATA_PATH", "data/raw/HDB_full_resale_info.csv.gz")
RPI_PATH      = os.environ.get("RPI_DATA_PATH", "data/raw/HousingAndDevelopmentBoardHDBResalePriceIndex1Q2009100Quarterly.csv")
MODEL_DIR     = os.environ.get("MODEL_DIR", "models")
MODEL_PATH    = os.path.join(MODEL_DIR, "hybrid_model.pkl")

CURRENT_RPI     = 203.6
LISTING_PREMIUM = 1.10

COLS_TO_DROP = ["address", "block", "street_name", "RPI", "resale_price"]


# ── Training ─────────────────────────────────────────────────────────────────

def train_and_save(data_path: str = DATA_PATH, rpi_path: str = RPI_PATH, model_path: str = MODEL_PATH):
    print("Loading data …")
    raw = pd.read_csv(data_path)



    print("Merging RPI …")
    rpi_df   = pd.read_csv(rpi_path)
    rpi_long = rpi_df.melt(id_vars="DataSeries", var_name="quarter_str", value_name="RPI")
    rpi_long = rpi_long[rpi_long["DataSeries"] == "HDB Resale Price Index"].copy()
    rpi_long["sold_year"] = rpi_long["quarter_str"].str[:4].astype(int)
    rpi_annual = rpi_long.groupby("sold_year")["RPI"].mean().reset_index()
    raw = raw.merge(rpi_annual, on="sold_year", how="left")
    raw["RPI"] = raw["RPI"].fillna(CURRENT_RPI)
    print(f"After merging RPI: {raw.shape}")

    df = raw.copy()
    df["flat_age_at_sale"] = df["sold_year"] - df["lease_commence_date"]
    df["log_price_norm"]   = np.log(df["resale_price"] / (df["floor_area_sqm"] * df["RPI"]))
    df = df.drop(columns=[c for c in COLS_TO_DROP if c in df.columns])

    cat_cols = df.select_dtypes(include=["object", "str"]).columns.tolist()
    encoders = {}
    for col in cat_cols:
        le = LabelEncoder()
        df[col] = le.fit_transform(df[col].astype(str))
        encoders[col] = le

    tree_features = [c for c in df.columns if c != "log_price_norm"]

    X_train, X_test, y_train, y_test = train_test_split(
        df[tree_features], df["log_price_norm"], test_size=0.2, random_state=42
    )
    y_test_actual = np.exp(y_test) * X_test["floor_area_sqm"] * CURRENT_RPI

    print("Training XGBoost …")
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
    xgb_model.fit(X_train, y_train, sample_weight=sample_weights)

    preds_log    = xgb_model.predict(X_test)
    preds_dollar = np.exp(preds_log) * X_test["floor_area_sqm"] * CURRENT_RPI

    mae  = mean_absolute_error(y_test_actual, preds_dollar)
    mape = mean_absolute_percentage_error(y_test_actual, preds_dollar) * 100
    print(f"  MAE : ${mae:,.2f}")
    print(f"  MAPE: {mape:.2f}%")

    # Store the raw dataframe (before encoding) for live inference filtering
    # Keep only columns needed for defaults to reduce pkl size
    raw_slim = raw[[
        "town", "flat_type", "sold_year",
        "lease_commence_date", "storey_range", "flat_model",
        "max_floor_lvl", "storey_mid", "storey_category",
        "is_mature_estate", "eldercare_count_1km", "clinic_count_1km",
        "hospital_count_1km", "communityclub_count_1km", "park_count_1km",
    ]].copy()

    os.makedirs(MODEL_DIR, exist_ok=True)
    bundle = dict(
        xgb_model=xgb_model,
        encoders=encoders,
        tree_features=tree_features,
        cat_cols=cat_cols,
        raw_slim=raw_slim,
        global_medians=X_train.median().to_dict(),
    )
    with open(model_path, "wb") as f:
        pickle.dump(bundle, f)
    print(f"Model saved → {model_path}")

    return {"mae": mae, "mape": mape}


# ── Inference ────────────────────────────────────────────────────────────────

class HDBPredictor:

    def __init__(self, model_path: str = MODEL_PATH):
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Model not found at {model_path}. Run train_and_save() first."
            )
        with open(model_path, "rb") as f:
            self._bundle = pickle.load(f)

    def predict(
        self,
        town: str,
        flat_type: str,
        floor_area_sqm: float,
        sold_year: int,
        sold_month: int = 1,
        listing_premium: float = LISTING_PREMIUM,
    ) -> dict:
        """
        Mirrors notebook predict_price() exactly:
          1. Filter to town + flat_type + sold_year >= 2022
          2. Fallback to town + flat_type (all years)
          3. Fallback to town only
        """
        b = self._bundle
        hdb = b["raw_slim"]

        # Mirror notebook filtering exactly
        town_data = hdb[(hdb["town"] == town) &
                        (hdb["flat_type"] == flat_type) &
                        (hdb["sold_year"] >= 2022)]
        if town_data.empty:
            town_data = hdb[(hdb["town"] == town) & (hdb["flat_type"] == flat_type)]
        if town_data.empty:
            town_data = hdb[hdb["town"] == town]
        if town_data.empty:
            town_data = hdb

        lc_date   = int(town_data["lease_commence_date"].median())
        flat_age  = sold_year - lc_date
        remaining = 99 - flat_age

        row = {
            "town":                    town,
            "flat_type":               flat_type,
            "storey_range":            town_data["storey_range"].mode()[0],
            "floor_area_sqm":          floor_area_sqm,
            "flat_model":              town_data["flat_model"].mode()[0],
            "lease_commence_date":     lc_date,
            "remaining_lease":         remaining,
            "sold_year":               sold_year,
            "max_floor_lvl":           float(town_data["max_floor_lvl"].median()),
            "storey_mid":              float(town_data["storey_mid"].median()),
            "storey_category":         town_data["storey_category"].mode()[0],
            "is_mature_estate":        int(town_data["is_mature_estate"].mode()[0]),
            "flat_age_at_sale":        flat_age,
            "eldercare_count_1km":     float(town_data["eldercare_count_1km"].median()),
            "clinic_count_1km":        float(town_data["clinic_count_1km"].median()),
            "hospital_count_1km":      float(town_data["hospital_count_1km"].median()),
            "communityclub_count_1km": float(town_data["communityclub_count_1km"].median()),
            "park_count_1km":          float(town_data["park_count_1km"].median()),
        }

        for col in b["tree_features"]:
            if col not in row:
                row[col] = b["global_medians"].get(col, 0)

        df_in = pd.DataFrame([row])[b["tree_features"]]

        for col in b["cat_cols"]:
            if col not in df_in.columns:
                continue
            le = b["encoders"][col]
            val = str(df_in.at[0, col])
            if val in le.classes_:
                df_in[col] = le.transform([val])
            else:
                df_in[col] = le.transform([le.classes_[0]])

        log_pred         = b["xgb_model"].predict(df_in)[0]
        transacted_price = float(np.exp(log_pred) * floor_area_sqm * CURRENT_RPI)
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