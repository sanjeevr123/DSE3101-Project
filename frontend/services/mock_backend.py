def mock_predict_price(postal_code, flat_type, floor_area):
    base = 520_000
    if flat_type and flat_type.startswith("5"):
        base += 45_000
    elif flat_type and flat_type.startswith("3"):
        base -= 60_000
    elif flat_type and flat_type.startswith("2"):
        base -= 95_000
    if floor_area:
        base += int((float(floor_area) - 90) * 1200)
    try:
        base += (int(str(postal_code).strip()[:2]) % 7) * 3500
    except Exception:
        pass
    return {"price": int(base), "low": int(base * 0.93), "high": int(base * 1.07), "median_town": int(base * 0.98)}


def mock_recommendations(constraints):
    return [
        {"town": "Ang Mo Kio", "rooms": 3, "postal": "560123", "buy_price": 480_000,
         "amenity_score": 84, "mrt_dist_km": 0.45, "clinic_dist_m": 220, "hawker_dist_m": 320, "park_dist_m": 380},
        {"town": "Bedok", "rooms": 3, "postal": "460123", "buy_price": 420_000,
         "amenity_score": 78, "mrt_dist_km": 0.35, "clinic_dist_m": 180, "hawker_dist_m": 260, "park_dist_m": 410},
        {"town": "Tampines", "rooms": 3, "postal": "520123", "buy_price": 430_000,
         "amenity_score": 80, "mrt_dist_km": 0.55, "clinic_dist_m": 260, "hawker_dist_m": 290, "park_dist_m": 520},
    ]
