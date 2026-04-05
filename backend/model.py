import joblib
import numpy as np
import pandas as pd

# Load all artifacts from pkl
_artifacts = joblib.load("data/raw/hdb_model_artifacts.pkl")
_xgb_model = _artifacts["xgb_model"]
_hdb_df = _artifacts["hdb_df"]
_X_train = _artifacts["X_train"]
_encoders = _artifacts["encoders"]
_TREE_FEATURES = _artifacts["TREE_FEATURES"]
_categorical_cols = _artifacts["categorical_cols"]
CURRENT_RPI = _artifacts["CURRENT_RPI"]

TOWN_PREMIUM = {
    'MARINE PARADE': 1.17, 'QUEENSTOWN': 1.15, 'CLEMENTI': 1.11,
    'BUKIT MERAH': 1.10, 'BUKIT PANJANG': 1.10, 'HOUGANG': 1.09,
    'BEDOK': 1.08, 'KALLANG/WHAMPOA': 1.08, 'JURONG EAST': 1.07,
    'BUKIT BATOK': 1.07, 'CENTRAL AREA': 1.07, 'TAMPINES': 1.07,
    'JURONG WEST': 1.06, 'CHOA CHU KANG': 1.06, 'SERANGOON': 1.06,
    'TOA PAYOH': 1.06, 'PASIR RIS': 1.05, 'ANG MO KIO': 1.05,
    'WOODLANDS': 1.05, 'SENGKANG': 1.05, 'YISHUN': 1.05,
    'BISHAN': 1.04, 'PUNGGOL': 1.04, 'BUKIT TIMAH': 1.03,
    'GEYLANG': 1.03, 'SEMBAWANG': 1.02,
}
DEFAULT_PREMIUM = 1.07

FLAT_TYPE_ADJUSTMENT = {
    '2 ROOM': 1.035, '3 ROOM': 1.014, 'EXECUTIVE': 1.008,
    '4 ROOM': 0.998, '5 ROOM': 0.993, 'MULTI-GENERATION': 1.000,
}


class HDBPredictor:
    def predict(self, town, flat_type, floor_area_sqm, sold_year, sold_month,
                listing_premium=1.0, remaining_lease=None):

        town_data = _hdb_df[
            (_hdb_df['town'] == town) &
            (_hdb_df['flat_type'] == flat_type) &
            (_hdb_df['sold_year'] >= 2022)
        ]
        if town_data.empty:
            town_data = _hdb_df[(_hdb_df['town'] == town) & (_hdb_df['flat_type'] == flat_type)]
        if town_data.empty:
            town_data = _hdb_df[_hdb_df['town'] == town]

        if remaining_lease is None:
            remaining_lease = int(town_data['remaining_lease'].median())

        flat_age = 99 - remaining_lease
        lease_commence_date = sold_year - flat_age

        input_dict = {
            'town': town,
            'flat_type': flat_type,
            'storey_range': town_data['storey_range'].mode()[0],
            'floor_area_sqm': floor_area_sqm,
            'flat_model': town_data['flat_model'].mode()[0],
            'lease_commence_date': lease_commence_date,
            'remaining_lease': remaining_lease,
            'sold_year': sold_year,
            'storey_mid': town_data['storey_mid'].median(),
            'storey_category': town_data['storey_category'].mode()[0],
            'region': town_data['region'].mode()[0],
            'is_mature_estate': int(town_data['is_mature_estate'].mode()[0]),
            'nearest_mrt_distance_m': town_data['nearest_mrt_distance_m'].median(),
            'nearest_clinic_distance_m': town_data['nearest_clinic_distance_m'].median(),
            'nearest_park_distance_m': town_data['nearest_park_distance_m'].median(),
            'nearest_community_club_distance_m': town_data['nearest_community_club_distance_m'].median(),
            'nearest_hawker_distance_m': town_data['nearest_hawker_distance_m'].median(),
            'num_mrt_within_1000m': town_data['num_mrt_within_1000m'].median(),
            'num_clinic_within_1000m': town_data['num_clinic_within_1000m'].median(),
            'num_park_within_1000m': town_data['num_park_within_1000m'].median(),
            'num_community_club_within_1000m': town_data['num_community_club_within_1000m'].median(),
            'num_amenities_within_1000m': town_data['num_amenities_within_1000m'].median(),
            'flat_age_at_sale': flat_age,
        }

        for col in _TREE_FEATURES:
            if col not in input_dict:
                input_dict[col] = _X_train[col].median()

        input_df = pd.DataFrame([input_dict])[_TREE_FEATURES]

        for col in _categorical_cols:
            if col in input_df.columns:
                try:
                    input_df[col] = _encoders[col].transform(input_df[col].astype(str))
                except ValueError:
                    input_df[col] = _X_train[col].mode()[0]

        log_pred = _xgb_model.predict(input_df)[0]
        transacted = np.exp(log_pred) * floor_area_sqm * CURRENT_RPI
        town_premium = TOWN_PREMIUM.get(town, DEFAULT_PREMIUM)
        flat_adj = FLAT_TYPE_ADJUSTMENT.get(flat_type, 1.0)
        asking_price = transacted * town_premium * flat_adj

        # Compute town median for reference
        recent = _hdb_df[
            (_hdb_df['town'] == town) &
            (_hdb_df['flat_type'] == flat_type) &
            (_hdb_df['sold_year'] >= 2023)
        ]
        if recent.empty:
            recent = _hdb_df[(_hdb_df['town'] == town) & (_hdb_df['flat_type'] == flat_type)]
        median_town = int(recent['resale_price'].median()) if not recent.empty else int(asking_price)

        return {
            "transacted_price": float(transacted),
            "asking_price": float(asking_price),
            "median_town": median_town,
        }