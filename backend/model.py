import os
from backend.hdb_predictor import predict_price_user, hdb_df

class HDBPredictor:
    def predict(self, town, flat_type, floor_area_sqm, listing_premium=1.0, remaining_lease=None):
        result = predict_price_user(
            town=town,
            flat_type=flat_type,
            floor_area=floor_area_sqm,
            remaining_lease=remaining_lease,
        )

        recent = hdb_df[
            (hdb_df['town'] == town) &
            (hdb_df['flat_type'] == flat_type) &
            (hdb_df['sold_year'] >= 2023)
        ]
        if recent.empty:
            recent = hdb_df[(hdb_df['town'] == town) & (hdb_df['flat_type'] == flat_type)]
        median_town = int(recent['resale_price'].median()) if not recent.empty else int(result['estimated_price'])

        return {
            "transacted_price": float(result['estimated_price']),
            "asking_price":     float(result['estimated_price']),
            "median_town":      median_town,
        }