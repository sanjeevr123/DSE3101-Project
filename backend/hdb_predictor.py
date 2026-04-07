# hdb_predictor.py

import os
import joblib
import numpy as np
import pandas as pd
from datetime import datetime

_DIR = os.path.dirname(os.path.abspath(__file__))
artifacts        = joblib.load(os.path.join(_DIR, '..', 'data', 'raw', 'hdb_model_artifacts_v2.pkl'))
xgb_model        = artifacts['xgb_model']
hdb_df           = artifacts['hdb_df']
encoders         = artifacts['encoders']
TREE_FEATURES    = artifacts['TREE_FEATURES']
categorical_cols = artifacts['categorical_cols']
CURRENT_RPI      = artifacts['CURRENT_RPI']

# Town-level listing premium
# Converts transacted price → asking/listing price
TOWN_PREMIUM = {
    'MARINE PARADE':     1.17,
    'QUEENSTOWN':        1.15,
    'CLEMENTI':          1.11,
    'BUKIT MERAH':       1.10,
    'BUKIT PANJANG':     1.10,
    'HOUGANG':           1.09,
    'BEDOK':             1.08,
    'KALLANG/WHAMPOA':   1.08,
    'JURONG EAST':       1.07,
    'BUKIT BATOK':       1.07,
    'CENTRAL AREA':      1.07,
    'TAMPINES':          1.07,
    'JURONG WEST':       1.06,
    'CHOA CHU KANG':     1.06,
    'SERANGOON':         1.06,
    'TOA PAYOH':         1.06,
    'PASIR RIS':         1.05,
    'ANG MO KIO':        1.05,
    'WOODLANDS':         1.05,
    'SENGKANG':          1.05,
    'YISHUN':            1.05,
    'BISHAN':            1.04,
    'PUNGGOL':           1.04,
    'BUKIT TIMAH':       1.03,
    'GEYLANG':           1.03,
    'SEMBAWANG':         1.02,
}

DEFAULT_PREMIUM = 1.07

# Flat type adjustment on top of town premium
FLAT_TYPE_ADJUSTMENT = {
    '2 ROOM':           1.035,
    '3 ROOM':           1.014,
    'EXECUTIVE':        1.008,
    '4 ROOM':           0.998,
    '5 ROOM':           0.993,
    'MULTI-GENERATION': 1.000,
}

def _encode_and_predict(input_dict):
    """
    Shared helper used by both prediction functions.
    Encodes categoricals and runs the XGBoost prediction.
    Returns the raw transacted price (before premiums).
    """
    input_df = pd.DataFrame([input_dict])[TREE_FEATURES]

    for col in categorical_cols:
        if col in input_df.columns:
            try:
                input_df[col] = encoders[col].transform(
                    input_df[col].astype(str)
                )
            except ValueError:
                # Unseen category: fall back to first known class
                input_df[col] = encoders[col].transform(
                    [encoders[col].classes_[0]]
                )[0]

    log_pred = xgb_model.predict(input_df)[0]
    return log_pred


# ============================================================
# FUNCTION 1: For PropertyGuru listings dataset
# Uses actual engineered features from the listing row
# Most accurate prediction
# ============================================================
def predict_price_listing(listing_row):
    """
    Takes a single row from the PropertyGuru listings dataframe.
    Missing features are filled with NaN — tree models handle this natively.
    """
    def safe_get(row, key):
        """Return NaN if key is missing or value is None/NaN."""
        try:
            val = row[key]
            return val if pd.notna(val) else np.nan
        except (KeyError, TypeError):
            return np.nan

    input_dict = {
        'town':                              safe_get(listing_row, 'hdb_town'),
        'flat_type':                         safe_get(listing_row, 'flat_type'),
        'floor_area_sqm':                    safe_get(listing_row, 'floor_area_sqm'),
        'lease_commence_date':               safe_get(listing_row, 'lease_commence_date'),
        'remaining_lease':                   safe_get(listing_row, 'remaining_lease'),
        'sold_year':                         safe_get(listing_row, 'sold_year'),
        'storey_mid':                        safe_get(listing_row, 'storey_mid'),
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
        'num_hawker_within_1000m':           safe_get(listing_row, 'num_hawker_within_1000m'),
        'num_community_club_within_1000m':   safe_get(listing_row, 'num_community_club_within_1000m'),
        'num_amenities_within_1000m':        safe_get(listing_row, 'num_amenities_within_1000m'),
        'flat_age_at_sale':                  safe_get(listing_row, 'flat_age_at_sale'),
    }

    log_pred   = _encode_and_predict(input_dict)
    
    # floor_area_sqm is critical for inverse transform — fall back to flat type median if missing
    floor_area = safe_get(listing_row, 'floor_area_sqm')
    if np.isnan(floor_area):
        FLAT_TYPE_MEDIAN_SQM = {
            '2 ROOM': 45, '3 ROOM': 67, '4 ROOM': 90,
            '5 ROOM': 110, 'EXECUTIVE': 130
        }
        floor_area = FLAT_TYPE_MEDIAN_SQM.get(listing_row.get('flat_type', ''), 90)

    transacted = np.exp(log_pred) * floor_area * CURRENT_RPI

    listing_premium = TOWN_PREMIUM.get(safe_get(listing_row, 'hdb_town'), DEFAULT_PREMIUM)
    flat_adj        = FLAT_TYPE_ADJUSTMENT.get(safe_get(listing_row, 'flat_type'), 1.0)

    return round(transacted * listing_premium * flat_adj, 2)

# ============================================================
# FUNCTION 2: For user-facing price estimator
# Takes only 4-5 inputs, imputes missing features smartly
# Returns price with confidence range to reflect uncertainty
# ============================================================
def predict_price_user(town, flat_type, floor_area,
                       remaining_lease=None):
    """
    Takes minimal user inputs and estimates the resale price.
    Uses town + flat_type historical medians for missing features.
    Returns a dict with estimated price and confidence range.

    Usage:
        result = predict_price_user('QUEENSTOWN', '4 ROOM', 83, 2025,
                                     remaining_lease=68)
        print(result['estimated_price'])
        print(result['lower_bound'])
        print(result['upper_bound'])
    """

    # ============================================================
    # Get best matching historical reference data for imputation
    # Priority: town + flat_type + recent → town + flat_type → town
    # ============================================================
    ref = hdb_df[
        (hdb_df['town'] == town) &
        (hdb_df['flat_type'] == flat_type) &
        (hdb_df['sold_year'] >= 2022)
    ]
    if ref.empty:
        ref = hdb_df[
            (hdb_df['town'] == town) &
            (hdb_df['flat_type'] == flat_type)
        ]
    if ref.empty:
        ref = hdb_df[hdb_df['town'] == town]
    if ref.empty:
        ref = hdb_df.copy()

    # ============================================================
    # Impute lease features
    # Use user-provided remaining_lease if given, otherwise median
    # ============================================================

    if remaining_lease is None:
        remaining_lease = int(ref['remaining_lease'].median())

    sold_year = datetime.now().year    # ← add this line
    flat_age       = 99 - remaining_lease
    lease_commence = sold_year - flat_age

    # ============================================================
    # Build input using actual user values + imputed medians
    # ============================================================
    input_dict = {
        'town':                              town,
        'flat_type':                         flat_type,
        'floor_area_sqm':                    floor_area,
        'lease_commence_date':               lease_commence,
        'remaining_lease':                   remaining_lease,
        'sold_year':                         sold_year,
        'storey_mid':                        ref['storey_mid'].median(),
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
        'num_hawker_within_1000m':           ref['num_hawker_within_1000m'].median(),
        'num_community_club_within_1000m':   ref['num_community_club_within_1000m'].median(),
        'num_amenities_within_1000m':        ref['num_amenities_within_1000m'].median(),
        'flat_age_at_sale':                  flat_age,
    }

    log_pred   = _encode_and_predict(input_dict)
    transacted = np.exp(log_pred) * floor_area * CURRENT_RPI

    listing_premium = TOWN_PREMIUM.get(town, DEFAULT_PREMIUM)
    flat_adj        = FLAT_TYPE_ADJUSTMENT.get(flat_type, 1.0)
    estimated_price = transacted * listing_premium * flat_adj

    # ============================================================
    # Return price with +/- (rounded mape)% confidence range
    # This honestly reflects the uncertainty from model
    # ============================================================
    mape_val = 0.10  # Use a fixed MAPE of 10% for user-facing estimator to reflect higher uncertainty from imputation
    return {
        'estimated_price': round(estimated_price, 2),
        'lower_bound':     round(estimated_price * (1-mape_val), 2),
        'upper_bound':     round(estimated_price * (1+mape_val), 2),
        'note': (
            f"Estimated based on {town} {flat_type} historical averages. "
            f"Actual price may vary depending on floor level, exact location, "
            f"and remaining lease."
        )
    }
