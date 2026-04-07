


# Wrapper class for the v2 XGBoost prediction model.
# Exposes a single predict() method used by the /predict/sell endpoint.
#This is for future refinements such as a frontend dashboard that displays user's flat details
#compared to their town (not used now to simplify app)
import os
from datetime import datetime
from backend.hdb_predictor import predict_price_user, hdb_df

class HDBPredictor:
    def predict(self, town, flat_type, floor_area_sqm, listing_premium=1.0, remaining_lease=None):
        try:
            result = predict_price_user(
                town=town,
                flat_type=flat_type,
                floor_area=floor_area_sqm,
                sold_year=datetime.now().year,
                remaining_lease=remaining_lease,
            )
        except Exception as e:
            print(f"ERROR in predict_price_user: {e}")
            raise

        recent = hdb_df[
            (hdb_df['town'] == town) &
            (hdb_df['flat_type'] == flat_type) &
            (hdb_df['sold_year'] >= 2023)
        ]

        # Compute town-level median from recent (2023+) transactions as reference price.
        # Falls back to all-time median for that town+flat_type if recent data is sparse.
        if recent.empty:
            recent = hdb_df[(hdb_df['town'] == town) & (hdb_df['flat_type'] == flat_type)]
        median_town = int(recent['resale_price'].median()) if not recent.empty else int(result['estimated_price'])

        return {
            "transacted_price": float(result['estimated_price']),
            "asking_price":     float(result['estimated_price']),
            "median_town":      median_town,
        }