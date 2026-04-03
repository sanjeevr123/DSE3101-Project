from urllib.parse import urlencode
import math

from config.constants import TOWN_TO_DISTRICT, PG_HDB_CODES_BY_ROOMS


def build_propertyguru_url(town, rooms, min_price, max_price, distance_to_mrt_km=0.5):
    district = TOWN_TO_DISTRICT.get(town, "D20")
    type_codes = PG_HDB_CODES_BY_ROOMS.get(int(rooms), PG_HDB_CODES_BY_ROOMS[3])
    params = {
        "listingType": "sale",
        "page": 1,
        "districtCode": district,
        "propertyTypeGroup": "H",
        "propertyTypeCode": type_codes,
        "isCommercial": "false",
        "_freetextDisplay": f"{district} {town}",
        "minPrice": int(min_price),
        "maxPrice": int(max_price),
        "distanceToMRT": float(distance_to_mrt_km),
    }
    return f"https://www.propertyguru.com.sg/property-for-sale?{urlencode(params, doseq=True)}"


def weights_from_sliders(hc, tr, hw, rec):
    return {
        "clinic": hc,
        "mrt":    tr,
        "hawker": hw,
        "park":   rec,
    }


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c
