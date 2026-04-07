# =============================================================================
# hdb_predictor.py
# Loads trained HDB resale price model and exposes two prediction functions:
#   - predict_price_listing(): for PropertyGuru listing rows (full features)
#   - predict_price_user():    for user-facing estimator (minimal inputs)
# =============================================================================

import os
import joblib
import numpy as np
import pandas as pd

# =============================================================================
# 1. Load Model Artifacts
# =============================================================================
os.chdir('/workspaces/DSE3101-Project/data/raw')

artifacts        = joblib.load('hdb_model_artifacts_v2.pkl')
xgb_model        = artifacts['xgb_model']
hdb_df           = artifacts['hdb_df']
encoders         = artifacts['encoders']
TREE_FEATURES    = artifacts['TREE_FEATURES']
categorical_cols = artifacts['categorical_cols']
CURRENT_RPI      = artifacts['CURRENT_RPI']

# =============================================================================
# 2. Listing Premium Constants
# Converts model output (transacted price) → asking/listing price.
# Premiums vary by town and flat type based on observed market behaviour.
# =============================================================================
TOWN_PREMIUM = {
    'MARINE PARADE': 1.17, 'QUEENSTOWN': 1.15, 'CLEMENTI': 1.11,
    'BUKIT MERAH':   1.10, 'BUKIT PANJANG': 1.10, 'HOUGANG': 1.09,
    'BEDOK':         1.08, 'KALLANG/WHAMPOA': 1.08, 'JURONG EAST': 1.07,
    'BUKIT BATOK':   1.07, 'CENTRAL AREA': 1.07, 'TAMPINES': 1.07,
    'JURONG WEST':   1.06, 'CHOA CHU KANG': 1.06, 'SERANGOON': 1.06,
    'TOA PAYOH':     1.06, 'PASIR RIS': 1.05, 'ANG MO KIO': 1.05,
    'WOODLANDS':     1.05, 'SENGKANG': 1.05, 'YISHUN': 1.05,
    'BISHAN':        1.04, 'PUNGGOL': 1.04, 'BUKIT TIMAH': 1.03,
    'GEYLANG':       1.03, 'SEMBAWANG': 1.02,
}
DEFAULT_PREMIUM = 1.07  # fallback for towns not in the map

FLAT_TYPE_ADJUSTMENT = {
    '2 ROOM': 1.035, '3 ROOM': 1.014, 'EXECUTIVE': 1.008,
    '4 ROOM': 0.998, '5 ROOM': 0.993, 'MULTI-GENERATION': 1.000,
}

# =============================================================================
# 3. Shared Encoding Helper
# =============================================================================
def _encode_and_predict(input_dict):
    """
    Encodes categorical features and runs the XGBoost prediction.
    Only features in TREE_FEATURES are passed to the model —
    any extra keys in input_dict are silently ignored.
    Returns the raw log-space prediction (before dollar conversion).
    """
    input_df = pd.DataFrame([input_dict])[TREE_FEATURES]

    for col in categorical_cols:
        if col in input_df.columns:
            try:
                input_df[col] = encoders[col].transform(
                    input_df[col].astype(str)
                )
            except ValueError:
                input_df[col] = 0  # unseen category: safe integer fallback

    return xgb_model.predict(input_df)[0]


# =============================================================================
# 4. Prediction Function 1: PropertyGuru Listings
# Uses all available engineered features from the listing row.
# Most accurate prediction path — missing values handled natively by XGBoost.
# =============================================================================
def predict_price_listing(listing_row):
    """
    Predicts the listing price for a single PropertyGuru row.

    Args:
        listing_row: a pandas Series or dict with listing features.

    Returns:
        Predicted listing price in SGD (float).
    """
    def safe_get(row, key):
        """Returns NaN if key is missing or value is null."""
        try:
            val = row[key]
            return val if pd.notna(val) else np.nan
        except (KeyError, TypeError):
            return np.nan

    # Only features present in TREE_FEATURES are passed to the model
    input_dict = {
        'town':                              safe_get(listing_row, 'hdb_town'),
        'flat_type':                         safe_get(listing_row, 'flat_type'),
        'floor_area_sqm':                    safe_get(listing_row, 'floor_area_sqm'),
        'remaining_lease':                   safe_get(listing_row, 'remaining_lease'),
        'storey_category':                   safe_get(listing_row, 'floor_category'),
        'region':                            safe_get(listing_row, 'region'),
        'is_mature_estate':                  safe_get(listing_row, 'is_mature_estate'),
        'nearest_mrt_distance_m':            safe_get(listing_row, 'nearest_mrt_distance_m'),
        'nearest_clinic_distance_m':         safe_get(listing_row, 'nearest_clinic_distance_m'),
        'nearest_park_distance_m':           safe_get(listing_row, 'nearest_park_distance_m'),
        'nearest_community_club_distance_m': safe_get(listing_row, 'nearest_community_club_distance_m'),
        'nearest_hawker_distance_m':         safe_get(listing_row, 'nearest_hawker_distance_m'),
        'num_mrt_within_1000m':              safe_get(listing_row, 'num_mrt_within_1000m'),
        'num_clinic_within_1000m':           safe_get(listing_row, 'num_clinic_within_1000m'),
        'num_park_within_1000m':             safe_get(listing_row, 'num_park_within_1000m'),
        'num_community_club_within_1000m':   safe_get(listing_row, 'num_community_club_within_1000m'),
        'num_amenities_within_1000m':        safe_get(listing_row, 'num_amenities_within_1000m'),
    }

    log_pred   = _encode_and_predict(input_dict)
    floor_area = safe_get(listing_row, 'floor_area_sqm')

    # floor_area_sqm is critical for the inverse transform —
    # fall back to flat type median if missing from listing
    if pd.isna(floor_area):
        floor_area = {
            '2 ROOM': 45, '3 ROOM': 67, '4 ROOM': 90,
            '5 ROOM': 110, 'EXECUTIVE': 130
        }.get(listing_row.get('flat_type', ''), 90)

    # Inverse transform: log-space → transacted price → listing price
    transacted = np.exp(log_pred) * floor_area * CURRENT_RPI
    premium    = TOWN_PREMIUM.get(safe_get(listing_row, 'hdb_town'), DEFAULT_PREMIUM)
    flat_adj   = FLAT_TYPE_ADJUSTMENT.get(safe_get(listing_row, 'flat_type'), 1.0)
    return round(transacted * premium * flat_adj, 2)


# =============================================================================
# 5. Prediction Function 2: User-Facing Price Estimator
# Requires only 3-4 inputs. Missing spatial features are imputed from
# recent town + flat_type historical medians (2022+).
# Returns price with ±10% indicative range to reflect imputation uncertainty.
# =============================================================================
def predict_price_user(town, flat_type, floor_area, remaining_lease=None):
    """
    Estimates current listing price from minimal user inputs.

    Args:
        town            : HDB town name in uppercase e.g. 'QUEENSTOWN'
        flat_type       : flat type in uppercase  e.g. '4 ROOM'
        floor_area      : floor area in sqm       e.g. 98
        remaining_lease : years remaining on lease (optional)

    Returns:
        dict with keys: estimated_price, lower_bound, upper_bound, note.

    Usage:
        result = predict_price_user('QUEENSTOWN', '4 ROOM', 98,
                                     remaining_lease=68)
        print(result['estimated_price'])
    """
    # Cascading reference data fallback:
    # recent (2022+) → all-time → town-only → global
    ref = hdb_df[
        (hdb_df['town'] == town) &
        (hdb_df['flat_type'] == flat_type) &
        (hdb_df['sold_year'] >= 2022)
    ]
    if ref.empty:
        ref = hdb_df[(hdb_df['town'] == town) & (hdb_df['flat_type'] == flat_type)]
    if ref.empty:
        ref = hdb_df[hdb_df['town'] == town]
    if ref.empty:
        ref = hdb_df.copy()

    # Use provided remaining_lease or fall back to town + flat_type median
    if remaining_lease is None:
        remaining_lease = int(ref['remaining_lease'].median())

    # Impute all spatial and categorical features from historical medians
    input_dict = {
        'town':                              town,
        'flat_type':                         flat_type,
        'floor_area_sqm':                    floor_area,
        'remaining_lease':                   remaining_lease,
        'storey_category':                   ref['storey_category'].mode()[0],
        'region':                            ref['region'].mode()[0],
        'is_mature_estate':                  int(ref['is_mature_estate'].mode()[0]),
        'nearest_mrt_distance_m':            ref['nearest_mrt_distance_m'].median(),
        'nearest_clinic_distance_m':         ref['nearest_clinic_distance_m'].median(),
        'nearest_park_distance_m':           ref['nearest_park_distance_m'].median(),
        'nearest_community_club_distance_m': ref['nearest_community_club_distance_m'].median(),
        'nearest_hawker_distance_m':         ref['nearest_hawker_distance_m'].median(),
        'num_mrt_within_1000m':              ref['num_mrt_within_1000m'].median(),
        'num_clinic_within_1000m':           ref['num_clinic_within_1000m'].median(),
        'num_park_within_1000m':             ref['num_park_within_1000m'].median(),
        'num_community_club_within_1000m':   ref['num_community_club_within_1000m'].median(),
        'num_amenities_within_1000m':        ref['num_amenities_within_1000m'].median(),
    }

    # Inverse transform: log-space → transacted price → listing price
    log_pred        = _encode_and_predict(input_dict)
    transacted      = np.exp(log_pred) * floor_area * CURRENT_RPI
    estimated_price = transacted * TOWN_PREMIUM.get(town, DEFAULT_PREMIUM) * \
                      FLAT_TYPE_ADJUSTMENT.get(flat_type, 1.0)

    # ±10% band reflects uncertainty from feature imputation
    return {
        'estimated_price': round(estimated_price, 2),
        'lower_bound':     round(estimated_price * 0.90, 2),
        'upper_bound':     round(estimated_price * 1.10, 2),
        'note': (
            f"Estimated from {town} {flat_type} historical medians. "
            f"±10% indicative range — actual price varies by floor level, "
            f"condition, and remaining lease."
        )
    }