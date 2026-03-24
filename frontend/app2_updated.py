# app.py
# ============================================================================
# HDB Downsizing Helper — mock
# ============================================================================
# HOW TO RUN:
#   pip install dash requests
#   python app.py
#   Open http://127.0.0.1:8050
#
# TEAM OWNERSHIP:
#   Member 5 (FE Lead)  — state management, callbacks, backend integration
#   Member 6 (Map)      — Leaflet map, markers, geocoding
#   Member 7 (UI/UX)    — all styling, layouts, step indicator, form components
#   Member 8 (Output)   — Step 4 result cards, PropertyGuru links, equity display
#
# Look for comments tagged with your member number, e.g.:
#   # MEMBER 7: adjust font size here
#   # MEMBER 6: change marker colour here
#   # MEMBER 8: update card layout here
#   # MEMBER 5: replace with real backend call
# ============================================================================


import logging
logging.basicConfig(level=logging.DEBUG, force=True)
logger = logging.getLogger("amenity_debug")
logger.setLevel(logging.DEBUG)
logger.debug("[Startup] amenity_debug logger is active.")

# Utility: Print all OneMap themes related to healthcare for QUERYNAME discovery
def print_healthcare_themes(onemap_token):
    """
    Prints all OneMap themes whose name or description contains 'health', 'hospital', or 'clinic'.
    Pass your OneMap API token as the argument.
    """
    url = "https://www.onemap.gov.sg/api/common/thematic/getAllThemesInfo"
    headers = {"Authorization": f"Bearer {onemap_token}"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        print("\n[OneMap] Healthcare-related themes:")
        for theme in data.get("THEMES", []):
            name = theme.get("THEMENAME", "")
            desc = theme.get("DESCRIPTION", "")
            queryname = theme.get("QUERYNAME", "")
            if any(x in (name+desc).lower() for x in ["health", "hospital", "clinic"]):
                print(f"  - Name: {name}\n    Description: {desc}\n    QUERYNAME: {queryname}\n")
        print("[Done] Use the QUERYNAME(s) above in your amenity fetch logic.")
    except Exception as e:
        print(f"[Error] Could not fetch OneMap themes: {e}")

from dash import Dash, html, dcc, Input, Output, State
import dash
import requests
from urllib.parse import urlencode
import math
import time
import json as json_module
import csv
import io

# ============================================================================
# CONFIG — MEMBER 5: update backend URL when backend team is ready
# ============================================================================
BACKEND_URL = "http://127.0.0.1:8000"
TIMEOUT_SEC = 6
ONEMAP_SEARCH_URL = "https://www.onemap.gov.sg/api/common/elastic/search"
ONEMAP_REVERSE_GEOCODE_URL = "https://www.onemap.gov.sg/api/public/revgeocode"
ONEMAP_TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoxMjEyMCwiZm9yZXZlciI6ZmFsc2UsImlzcyI6Ik9uZU1hcCIsImlhdCI6MTc3NDE3OTM5MSwibmJmIjoxNzc0MTc5MzkxLCJleHAiOjE3NzQ0Mzg1OTEsImp0aSI6ImRjNTE4MTU4LTVlN2UtNDZmZC05YWZmLTU0MWQxNWUwNTJjZSJ9.DB4YwPcdb7-icP5FXzx7Q5nL2H1YO6h5ladvnrYeVi46OCGI6eRkc2DcM5YjqPrYoYnrZ0RY_KOAzKj1fe-dhjj0CM_rFBFB2nouxs2hSf0Qx45WtWu8DnDFsGsY6LHemziKtyDTfvbNQGHPh2fX5JOanRlNP2-U_KfAMxtD9NWx9PrtOufRwgHXxxMWxwP0eQeBBw3-yRNy6o-EfcE2UV0tMgVtyC2kJHWKMrvzLprmoj8lj2xT5ETd52X2WLawZyX5mpHixNoriydaXKI6lR2Ntdsq76C_na5WGDurN29WPQ6QbmbdpPFwF0k005LU2-q3A9wW76XJGhJoAjYTag"
DATA_GOV_API_KEY = "v2:c9ed14bd6d2d9c9667a3e7b509a11d432231159500282eca500daaa311e7a8f7:grc7IN7jf0IKQDBdSl_RM-TUvyzbIVzw"  # API key for higher rate limits
TRANSPORT_DATASET_ID = "d_b39d3a0871985372d7e1637193335da5"

# Global cache for amenity data to avoid rate limit issues
AMENITY_CACHE_FILE = "amenity_cache.json"  # Persistent cache file
AMENITY_CACHE = {}
AMENITY_CACHE_TTL = 3600  # Cache for 1 hour per session
AMENITY_CACHE_VERSION = "v4"
REVERSE_GEOCODE_CACHE = {}
LAST_API_REQUEST_TIME = None  # Global request timestamp
API_REQUEST_DELAY_SEC = 1.5  # Minimal delay between API requests (reduced from 30s)

# Fallback mock data for when APIs are rate limited
FALLBACK_AMENITIES = {
    "hawker": [
        {"name": "Maxwell Food Centre", "address": "1 Kadayanallur St, Singapore 069184", "lat": 1.2745, "lon": 103.8447},
        {"name": "Chinatown Complex", "address": "335 Smith St, Singapore 050335", "lat": 1.2838, "lon": 103.8426},
        {"name": "Lau Pa Sat", "address": "18 Raffles Quay, Singapore 048582", "lat": 1.2858, "lon": 103.8510},
    ],
    "parks": [
        {"name": "Bishan Park", "address": "500 Bishan St 11, Singapore 579917", "lat": 1.3521, "lon": 103.8496},
        {"name": "Bukit Timah Nature Reserve", "address": "177 Hindhede Dr, Singapore 588994", "lat": 1.3622, "lon": 103.8176},
        {"name": "East Coast Park", "address": "1210 East Coast Pkwy, Singapore 449855", "lat": 1.2920, "lon": 103.9544},
    ],
    "mrt": [
        {"name": "Raffles Place MRT", "address": "10 Collyer Quay, Singapore 049315", "lat": 1.2865, "lon": 103.8517},
        {"name": "Tanjong Pagar MRT", "address": "111 Tanjong Pagar Rd, Singapore 088546", "lat": 1.2762, "lon": 103.8429},
        {"name": "Outram Park MRT", "address": "159 Outram Rd, Singapore 169040", "lat": 1.2897, "lon": 103.8358},
    ],
    "transport": [
        {"name": "Raffles Place MRT", "address": "10 Collyer Quay, Singapore 049315", "lat": 1.2865, "lon": 103.8517},
        {"name": "Tanjong Pagar MRT", "address": "111 Tanjong Pagar Rd, Singapore 088546", "lat": 1.2762, "lon": 103.8429},
        {"name": "Outram Park MRT", "address": "159 Outram Rd, Singapore 169040", "lat": 1.2897, "lon": 103.8358},
    ],
}

app = Dash(__name__, suppress_callback_exceptions=True)
server = app.server

# ============================================================================
# STYLING — MEMBER 7: this is your main section to customise
# ============================================================================
# All colours, fonts, sizes, and spacing are defined here.
# Change these variables to update the entire app's look and feel.

# MEMBER 7: adjust overall background — currently a soft gradient
PAGE_BG = "linear-gradient(135deg, #e8f7ff 0%, #eefcf3 55%, #f2f5ff 100%)"
# MEMBER 7: adjust shadow intensity for cards and buttons
SHADOW = "0 10px 26px rgba(15, 23, 42, 0.12)"

# MEMBER 7: base page style — font family, text colour, padding
base_page_style = {
    "minHeight": "100vh",
    "background": PAGE_BG,
    "padding": "22px 18px",           # MEMBER 7: adjust page padding
    "fontFamily": "system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif",  # MEMBER 7: change font family
    "color": "#0f172a",               # MEMBER 7: base text colour
}
container_style = {
    "maxWidth": "1180px",             # MEMBER 7: adjust max width of content area
    "margin": "0 auto",
}

# MEMBER 7: main title style (the "Downsizing Helper" heading)
title_style = {
    "fontSize": "46px",               # MEMBER 7: title font size
    "fontWeight": "950",              # MEMBER 7: title font weight
    "margin": "0",
    "display": "flex",
    "alignItems": "center",
    "gap": "12px",
}

# MEMBER 7: white card style used on every step
card_style = {
    "marginTop": "16px",
    "padding": "20px",                # MEMBER 7: card inner padding
    "borderRadius": "24px",           # MEMBER 7: card corner rounding
    "background": "rgba(255,255,255,0.92)",  # MEMBER 7: card background
    "border": "1px solid rgba(15,23,42,0.10)",
    "boxShadow": "0 2px 0 rgba(0,0,0,0.03)",
}

# MEMBER 7: form label style (e.g. "Postal code", "Flat type")
label_style = {
    "fontSize": "22px",               # MEMBER 7: label font size — keep large for seniors
    "fontWeight": "950",
    "marginBottom": "8px",
}

# MEMBER 7: text input style (postal code, floor area, budget)
input_style_big = {
    "width": "100%",
    "padding": "18px",                # MEMBER 7: input padding
    "fontSize": "24px",               # MEMBER 7: input font size — keep large for seniors
    "borderRadius": "18px",           # MEMBER 7: input corner rounding
    "border": "2px solid rgba(15,23,42,0.18)",
}

# MEMBER 7: primary action button (blue)
btn_primary = {
    "padding": "16px 22px",
    "fontSize": "24px",               # MEMBER 7: button font size
    "fontWeight": "950",
    "borderRadius": "18px",           # MEMBER 7: button corner rounding
    "border": "0",
    "background": "#0ea5e9",          # MEMBER 7: primary button colour
    "color": "white",
    "boxShadow": SHADOW,
    "cursor": "pointer",
    "minHeight": "60px",              # MEMBER 7: minimum button height — keep large for seniors
}

# MEMBER 7: back button style (outlined)
btn_back = {
    "padding": "16px 22px",
    "fontSize": "24px",
    "fontWeight": "950",
    "borderRadius": "18px",
    "border": "2px solid rgba(15,23,42,0.18)",
    "background": "rgba(255,255,255,0.85)",
    "color": "#0f172a",
    "cursor": "pointer",
    "minHeight": "60px",
}

# MEMBER 7: reset / start-over button
btn_reset = {
    "padding": "14px 18px",
    "fontSize": "20px",
    "fontWeight": "900",
    "borderRadius": "18px",
    "border": "1px solid rgba(15,23,42,0.18)",
    "background": "rgba(255,255,255,0.75)",
    "color": "#0f172a",
    "cursor": "pointer",
}

# MEMBER 7: success banner (green)
banner_ok = {
    "padding": "14px 16px",
    "borderRadius": "18px",
    "background": "rgba(34,197,94,0.15)",   # MEMBER 7: success background colour
    "border": "1px solid rgba(34,197,94,0.35)",
    "fontSize": "22px",
    "fontWeight": "950",
    "marginTop": "14px",
}

# MEMBER 7: warning/error banner (red)
banner_warn = {
    "padding": "14px 16px",
    "borderRadius": "18px",
    "background": "rgba(239,68,68,0.12)",   # MEMBER 7: warning background colour
    "border": "1px solid rgba(239,68,68,0.35)",
    "fontSize": "22px",
    "fontWeight": "950",
    "marginTop": "14px",
    "color": "#991b1b",                     # MEMBER 7: warning text colour
}


# ============================================================================
# PROPERTYGURU LINK HELPERS — MEMBER 8: expand and maintain
# ============================================================================

# MEMBER 8: add all 26 HDB towns mapped to their PropertyGuru district code
TOWN_TO_DISTRICT = {
    "Ang Mo Kio": "D20",
    "Bishan": "D20",
    "Toa Payoh": "D12",
    "Yishun": "D27",
    "Sengkang": "D28",
    "Punggol": "D28",
    "Tampines": "D18",
    "Pasir Ris": "D18",
    "Bedok": "D16",
    "Marine Parade": "D15",
    "Bukit Panjang": "D23",
    "Choa Chu Kang": "D23",
    "Bukit Batok": "D23",
    "Jurong West": "D22",
    "Jurong East": "D22",
    # MEMBER 8: add remaining — Woodlands, Sembawang, Queenstown,
    # Bukit Merah, Clementi, Hougang, Geylang, Kallang/Whampoa,
    # Serangoon, Central Area, etc.
}

# MEMBER 8: room-type codes for PropertyGuru URL scheme
PG_HDB_CODES_BY_ROOMS = {
    2: ["2A", "2Am", "2I", "2Im", "2S", "2STD"],
    3: ["3A", "3Am", "3I", "3Im", "3NG", "3NGm", "3PA", "3S", "3STD"],
    4: ["4A", "4Am", "4I", "4Im", "4NG", "4NGm", "4PA", "4S", "4STD"],
    5: ["5A", "5Am", "5I", "5Im", "5NG", "5NGm", "5PA", "5S", "5STD"],
    # MEMBER 8: add EXECUTIVE codes if needed
}


def build_propertyguru_url(town, rooms, min_price, max_price, distance_to_mrt_km=0.5):
    """
    Build a deep-link to PropertyGuru filtered listing.
    MEMBER 8: adjust default MRT distance, add more filters as needed.
    """
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


# ============================================================================
# BACKEND / API UTILITIES — MEMBER 5: manage backend integration
# ============================================================================

def safe_post(path, payload):
    """
    Call real backend API. Returns JSON dict or None on failure.
    MEMBER 5: when backend is live, this should just work.
    The None return triggers mock fallback in each callback.
    """
    try:
        r = requests.post(f"{BACKEND_URL}{path}", json=payload, timeout=TIMEOUT_SEC)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def onemap_search(query):
    """
    Public OneMap geocoding search. No auth needed.
    MEMBER 6: you may enhance error handling or add retry logic.
    Returns: { lat, lon, address, postal } or None
    """
    try:
        params = {"searchVal": query, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": 1}
        r = requests.get(ONEMAP_SEARCH_URL, params=params, timeout=TIMEOUT_SEC)
        r.raise_for_status()
        results = r.json().get("results") or []
        if not results:
            return None
        top = results[0]
        return {
            "lat": float(top.get("LATITUDE")),
            "lon": float(top.get("LONGITUDE")),
            "address": top.get("ADDRESS") or query,
            "postal": top.get("POSTAL") or "",
        }
    except Exception:
        return None


def get_nearby_amenity_location(name, town_or_postal):
    """
    Find a real amenity coordinate via OneMap, falling back safely.
    """
    if not name:
        return None
    candidates = [
        f"{name} {town_or_postal} Singapore", 
        f"{name} {town_or_postal}",
        f"{name} Singapore",
        name,
    ]
    for query in candidates:
        geo = onemap_search(query)
        if geo:
            return geo
    return None


def onemap_reverse_geocode(lat, lon, buffer=200):
    """
    Resolve nearest address from coordinates using OneMap reverse geocoding.
    Returns formatted address string or None.
    """
    cache_key = f"{float(lat):.5f}_{float(lon):.5f}_{int(buffer)}"
    if cache_key in REVERSE_GEOCODE_CACHE:
        return REVERSE_GEOCODE_CACHE[cache_key]

    try:
        params = {
            "location": f"{float(lat)},{float(lon)}",
            "buffer": int(buffer),
            "addressType": "All"
        }
        headers = {"Authorization": ONEMAP_TOKEN}
        r = requests.get(ONEMAP_REVERSE_GEOCODE_URL, params=params, headers=headers, timeout=TIMEOUT_SEC)
        r.raise_for_status()
        info = (r.json().get("GeocodeInfo") or [])
        if not info:
            REVERSE_GEOCODE_CACHE[cache_key] = None
            return None

        top = info[0]
        block = (top.get("BLOCK") or "").strip()
        road = (top.get("ROAD") or "").strip()
        building = (top.get("BUILDINGNAME") or "").strip()
        postal = (top.get("POSTALCODE") or "").strip()

        parts = []
        if block and block != "NIL":
            if road and road != "NIL":
                parts.append(f"{block} {road}")
            else:
                parts.append(block)
        elif road and road != "NIL":
            parts.append(road)

        if building and building != "NIL":
            parts.append(building)

        if postal and postal != "NIL":
            if postal.isdigit() and len(postal) == 6:
                parts.append(f"Singapore {postal}")
            else:
                parts.append(postal)

        address = ", ".join(parts) if parts else None
        REVERSE_GEOCODE_CACHE[cache_key] = address
        return address
    except Exception:
        REVERSE_GEOCODE_CACHE[cache_key] = None
        return None


def get_amenities_from_datagov(amenity_type, lat, lon, radius_km=3, limit=3):
    """
    Fetch real amenities from data.gov.sg API with aggressive rate limiting.
    
    Falls back to mock data if APIs are consistently rate limited.
    
    Args:
        amenity_type: 'healthcare', 'hawker', 'parks', or 'mrt'
        lat, lon: center coordinates
        radius_km: search radius in kilometers
        limit: max number of amenities to return
    
    Returns:
        List of dicts with: {lat, lon, name, address}
    """
    global LAST_API_REQUEST_TIME
    
    # Check cache first
    cache_key = f"{AMENITY_CACHE_VERSION}_{amenity_type}_{float(lat):.3f}_{float(lon):.3f}"
    if cache_key in AMENITY_CACHE:
        cache_entry = AMENITY_CACHE[cache_key]
        if time.time() - cache_entry["timestamp"] < AMENITY_CACHE_TTL:
            return cache_entry["data"]
        else:
            del AMENITY_CACHE[cache_key]
    
    # Global throttling: wait between API calls to avoid rate limits
    if LAST_API_REQUEST_TIME is not None:
        elapsed = time.time() - LAST_API_REQUEST_TIME
        if elapsed < API_REQUEST_DELAY_SEC:
            wait_time = API_REQUEST_DELAY_SEC - elapsed
            print(f"Throttling {amenity_type}: waiting {wait_time:.1f}s...")
            time.sleep(wait_time)
    
    # Try real API
    api_configs = {
        "hawker": {"format": "poll_download", "dataset_id": "d_4a086da0a5553be1d89383cd90d07ecd"},
        "parks": {"format": "poll_download", "dataset_id": "d_0542d48f0991541706b58059381a6eca"},
        "mrt": {"format": "metadata", "collection_id": 367},
        "transport": {"format": "poll_download", "dataset_id": TRANSPORT_DATASET_ID},
    }

    # Special handling for healthcare: fetch both polyclinics and hospitals from OneMap
    if amenity_type == "healthcare":
        try:
            results = _fetch_onemap_healthcare(lat, lon, radius_km, limit)
            AMENITY_CACHE[cache_key] = {
                "data": results,
                "timestamp": time.time()
            }
            return results
        except Exception as e:
            print(f"API error for healthcare: {e}. Using fallback mock data.")
            mock_results = _get_nearby_fallback_amenities(amenity_type, lat, lon, radius_km, limit)
            AMENITY_CACHE[cache_key] = {
                "data": mock_results,
                "timestamp": time.time()
            }
            return mock_results

    config = api_configs.get(amenity_type)
    if not config:
        return []

    # Use real API for hawker centres, parks, and transport
    if amenity_type in ("hawker", "parks", "transport"):
        try:
            records = _fetch_amenity_records(config, amenity_type)
            results = _filter_amenities_by_distance(records, lat, lon, radius_km, limit, amenity_type=amenity_type)
            # Cache API results
            AMENITY_CACHE[cache_key] = {
                "data": results,
                "timestamp": time.time()
            }
            return results
        except Exception as e:
            print(f"API error for {amenity_type}: {e}. Using fallback mock data.")
            mock_results = _get_nearby_fallback_amenities(amenity_type, lat, lon, radius_km, limit)
            AMENITY_CACHE[cache_key] = {
                "data": mock_results,
                "timestamp": time.time()
            }
            return mock_results
    else:
        # For other amenity types, keep fallback
        print(f"Using fallback mock data for {amenity_type}")
        mock_results = _get_nearby_fallback_amenities(amenity_type, lat, lon, radius_km, limit)
        AMENITY_CACHE[cache_key] = {
            "data": mock_results,
            "timestamp": time.time()
        }
        return mock_results

def _fetch_onemap_healthcare(lat, lon, radius_km=3, limit=3):
    """
    Fetch both polyclinics and hospitals from OneMap, merge, filter by distance, and return sorted by distance.
    """
    import requests, logging
    logger = logging.getLogger("amenity_debug")
    logger.debug(f"[OneMap] Entered _fetch_onemap_healthcare with lat={lat}, lon={lon}, radius_km={radius_km}, limit={limit}")
    themes = ["moh_hospitals", "vaccination_polyclinics"]
    results = []
    for theme in themes:
        url = f"https://www.onemap.gov.sg/api/public/themesvc/retrieveTheme?queryName={theme}"
        headers = {"Authorization": ONEMAP_TOKEN}
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            logger.debug(f"[OneMap] {theme} API returned {len(data.get('SrchResults', []))} results")
            for idx, item in enumerate(data.get("SrchResults", [])):
                coords = item.get("LatLng")
                logger.debug(f"[OneMap] {theme} result {idx}: NAME={item.get('NAME')}, LatLng={coords}")
                if coords:
                    try:
                        # LatLng is returned as "lat,lon" string, not a list
                        parts = str(coords).split(",")
                        if len(parts) == 2:
                            lat_ = float(parts[0].strip())
                            lon_ = float(parts[1].strip())
                            logger.debug(f"[OneMap] Parsed coords: lat={lat_}, lon={lon_}")
                            dist = haversine_km(lat, lon, lat_, lon_)
                            logger.debug(f"[OneMap] Distance to ({lat_}, {lon_}): {dist}")
                            if dist is not None and dist <= radius_km:
                                logger.debug(f"[OneMap] {theme} result {idx} within {radius_km}km: {item.get('NAME')}")
                                name = item.get("NAME") or item.get("Theme_Name") or ""
                                block = (item.get("ADDRESSBLOCKHOUSENUMBER") or "").strip()
                                street = (item.get("ADDRESSSTREETNAME") or "").strip()
                                building = (item.get("ADDRESSBUILDINGNAME") or "").strip()
                                postal = (item.get("ADDRESSPOSTALCODE") or "").strip()
                                generic_address = (item.get("ADDRESS") or "").strip()

                                addr_parts = []
                                if generic_address:
                                    addr_parts.append(generic_address)

                                if block and block != "-":
                                    if street:
                                        addr_parts.append(f"{block} {street}")
                                    else:
                                        addr_parts.append(block)
                                elif street:
                                    addr_parts.append(street)

                                if building and building.lower() != name.lower():
                                    addr_parts.append(building)

                                if postal:
                                    if postal.isdigit() and len(postal) == 6:
                                        addr_parts.append(f"Singapore {postal}")
                                    else:
                                        addr_parts.append(postal)

                                # Deduplicate while preserving order
                                seen = set()
                                clean_parts = []
                                for part in addr_parts:
                                    key = part.lower()
                                    if key not in seen:
                                        seen.add(key)
                                        clean_parts.append(part)

                                address = ", ".join(clean_parts)
                                results.append({
                                    "lat": lat_,
                                    "lon": lon_,
                                    "name": name,
                                    "address": address, 
                                    "type": theme,
                                    "distance_km": dist
                                })
                    except Exception as e:
                        logger.debug(f"[OneMap] Exception parsing coords for {theme} result {idx}: {e}")
                        continue
        except Exception as e:
            logger.debug(f"[OneMap] Exception fetching {theme}: {e}")
            continue
    logger.debug(f"[OneMap] Total healthcare amenities within {radius_km}km: {len(results)}")
    # Sort by distance and limit
    results = sorted(results, key=lambda x: x["distance_km"])
    # Remove the distance_km and type fields for output consistency
    for r in results:
        r.pop("distance_km", None)
        r.pop("type", None)
    return results[:limit]


def _get_nearby_fallback_amenities(amenity_type, lat, lon, radius_km, limit):
    """
    Use mock amenity data when APIs are rate limited.
    Filters mock data by distance.
    """
    fallback_key = "mrt" if amenity_type == "transport" else amenity_type
    fallback_data = FALLBACK_AMENITIES.get(fallback_key, [])
    results = []
    
    for amenity in fallback_data:
        dist = haversine_km(lat, lon, amenity["lat"], amenity["lon"])
        if dist is not None and dist <= radius_km:
            amenity_copy = amenity.copy()
            results.append(amenity_copy)
    
    return results[:limit]


def _fetch_amenity_records(config, amenity_type, max_retries=3):
    """
    Fetch records from data.gov.sg API with exponential backoff retry logic.
    Retries on rate limit errors (429) with increasing delays.
    Fails fast on other errors to allow fallback to mock data.
    """
    for attempt in range(max_retries):
        try:
            if config["format"] == "ckan_datastore":
                url = f"https://data.gov.sg/api/action/datastore_search?resource_id={config['resource_id']}"
                headers = {"x-api-key": DATA_GOV_API_KEY} if DATA_GOV_API_KEY else {}
                response = requests.get(url, headers=headers, timeout=TIMEOUT_SEC)
                response.raise_for_status()
                try:
                    data = response.json()
                    if data.get("success"):
                        records = data.get("result", {}).get("records", [])
                        if records:
                            print(f"DEBUG: Healthcare JSON records found: {len(records)}")
                            return records
                except Exception as e:
                    print(f"DEBUG: Healthcare JSON parse failed: {e}")
                # If not JSON or no records, try CSV fallback
                print("DEBUG: Trying CSV fallback for healthcare dataset...")
                response = requests.get(url.replace("datastore_search", "datastore_search?format=csv"), headers=headers, timeout=TIMEOUT_SEC)
                response.raise_for_status()
                csv_data = csv.DictReader(io.StringIO(response.text))
                records = list(csv_data)
                print(f"DEBUG: Healthcare CSV records found: {len(records)}")
                return records
            
            elif config["format"] == "metadata":
                url = f"https://api-production.data.gov.sg/v2/public/api/collections/{config['collection_id']}/metadata"
                response = requests.get(url, timeout=TIMEOUT_SEC)
                response.raise_for_status()
                data = response.json()
                return data.get("records", [])
            
            elif config["format"] == "poll_download":
                url = f"https://api-open.data.gov.sg/v1/public/api/datasets/{config['dataset_id']}/poll-download"
                headers = {"x-api-key": DATA_GOV_API_KEY} if DATA_GOV_API_KEY else {}
                response = requests.get(url, headers=headers, timeout=TIMEOUT_SEC)
                response.raise_for_status()
                json_data = response.json()
                
                if json_data.get("code") != 0:
                    print(f"API error for {amenity_type}: {json_data.get('errMsg')}")
                    return []
                
                data_url = json_data.get("data", {}).get("url")
                if not data_url:
                    return []
                
                response = requests.get(data_url, headers=headers, timeout=TIMEOUT_SEC)
                response.raise_for_status()
                try:
                    # Try GeoJSON
                    geojson = json_module.loads(response.text)
                    if isinstance(geojson, dict) and "features" in geojson:
                        return geojson  # Return full GeoJSON dict
                    # Otherwise, try records
                    if isinstance(geojson, dict):
                        return geojson.get("records", [])
                    return geojson
                except Exception:
                    csv_data = csv.DictReader(io.StringIO(response.text))
                    return list(csv_data)
            
            return []
        
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                # Rate limited — implement exponential backoff
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s...
                    print(f"Rate limited for {amenity_type}, attempt {attempt+1}/{max_retries}. Waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    # Final attempt failed, raise to trigger fallback
                    raise
            else:
                # Other HTTP errors — don't retry
                raise
        except Exception as e:
            # Network or parsing errors — don't retry
            raise
    
    return []


def _filter_amenities_by_distance(records, lat, lon, radius_km, limit, amenity_type=None):
    """
    Filter and extract amenity data from records by distance.
    """
    results = []
    logger = logging.getLogger("amenity_debug")
    # Handle GeoJSON features for hawker centres
    if isinstance(records, dict) and "features" in records:
        features = records["features"]
        logger.debug(f"[AmenityDebug] GeoJSON features found: {len(features)}")
        for i, feature in enumerate(features):
            try:
                coords = feature.get("geometry", {}).get("coordinates", [])
                if len(coords) == 2:
                    rec_lon, rec_lat = coords[0], coords[1]
                    props = feature.get("properties", {})
                    default_label = {
                        "hawker": "Hawker Centre",
                        "transport": "Transport Point",
                        "parks": "Park",
                    }.get(amenity_type, "Amenity")

                    transport_station = (props.get("STATION_NA") or "").strip()
                    transport_exit = (props.get("EXIT_CODE") or "").strip()
                    transport_name = ""
                    if amenity_type == "transport" and transport_station:
                        transport_name = f"{transport_station} ({transport_exit})" if transport_exit else transport_station

                    name_candidates = [
                        transport_name,
                        props.get("NAME"),
                        props.get("Name"),
                        props.get("name"),
                        props.get("TITLE"),
                        props.get("Title"),
                        props.get("facility_name"),
                        props.get("ADDRESSBUILDINGNAME"),
                        props.get("DESCRIPTION"),
                    ]
                    name = next((str(v).strip() for v in name_candidates if v and str(v).strip()), f"Unnamed {default_label}")
                    address = props.get("ADDRESS_MYENV")
                    if not address:
                        block = props.get("ADDRESSBLOCKHOUSENUMBER", "")
                        street = props.get("ADDRESSSTREETNAME", "")
                        postal = props.get("ADDRESSPOSTALCODE", "")
                        addr_parts = []
                        if block and str(block).strip() and str(block).strip() != "-":
                            addr_parts.append(str(block).strip())
                        if street and str(street).strip():
                            addr_parts.append(str(street).strip())
                        if postal and str(postal).strip():
                            postal_text = str(postal).strip()
                            if postal_text.isdigit() and len(postal_text) == 6:
                                addr_parts.append(f"Singapore {postal_text}")
                            else:
                                addr_parts.append(postal_text)
                        address = ", ".join(addr_parts)
                    if not address or not str(address).strip() or str(address).strip().lower() == "singapore":
                        resolved = onemap_reverse_geocode(rec_lat, rec_lon)
                        address = resolved or "Address not available"
                    # Debug: print the exact values passed to haversine_km
                    logger.debug(f"[AmenityDebug] Feature {i}: Calling haversine_km(lat={lat}, lon={lon}, rec_lat={rec_lat}, rec_lon={rec_lon})")
                    logger.debug(f"[AmenityDebug] Types: lat={type(lat)}, lon={type(lon)}, rec_lat={type(rec_lat)}, rec_lon={type(rec_lon)}")
                    try:
                        dist = haversine_km(lat, lon, rec_lat, rec_lon)
                        logger.debug(f"[AmenityDebug] Feature {i}: haversine_km result: {dist}")
                    except Exception as e:
                        logger.debug(f"[AmenityDebug] Feature {i}: Exception in haversine_km: {e}")
                        dist = None
                    if i < 5:
                        if dist is not None:
                            logger.debug(f"[AmenityDebug] Feature {i}: name={name}, coords=({rec_lat}, {rec_lon}), dist={dist:.3f} km")
                        else:
                            logger.debug(f"[AmenityDebug] Feature {i}: name={name}, coords=({rec_lat}, {rec_lon}), dist=None (lat/lon={lat},{lon})")
                    if dist is not None and dist <= radius_km:
                        if amenity_type == "parks" and (not address or address.strip().lower() == "singapore"):
                            resolved = onemap_reverse_geocode(rec_lat, rec_lon)
                            address = resolved or "Address not available"
                        results.append({
                            "lat": rec_lat,
                            "lon": rec_lon,
                            "name": name,
                            "address": address
                        })
            except Exception as e:
                logger.debug(f"[AmenityDebug] Exception parsing feature {i}: {e}, coords={feature.get('geometry', {}).get('coordinates', [])}")
                continue
        logger.debug(f"[AmenityDebug] Amenities within {radius_km}km: {len(results)} (limit {limit})")
        return results[:limit]
    # Fallback to original record parsing
        for record in records:
                try:
                        rec_lat = None
                        rec_lon = None
                        for lat_field in ["latitude", "Latitude", "lat", "Lat", "LATITUDE", "lat_long"]:
                                if lat_field in record:
                                        val = record[lat_field]
                                        if val:
                                                rec_lat = float(val)
                                                break
                        for lon_field in ["longitude", "Longitude", "lon", "Lon", "LONGITUDE", "Long"]:
                                if lon_field in record:
                                        val = record[lon_field]
                                        if val:
                                                rec_lon = float(val)
                                                break
                        if rec_lat is None or rec_lon is None or (rec_lat == 0 and rec_lon == 0):
                                name = None
                                for name_field in ["name", "Name", "NAME", "facility_name", "title", "Title", "place_name", "Place"]:
                                        if name_field in record and record[name_field]:
                                                name = record[name_field]
                                                break
                                if name:
                                        geo = get_nearby_amenity_location(name, "Singapore")
                                        if geo:
                                                rec_lat = geo["lat"]
                                                rec_lon = geo["lon"]
                        if rec_lat is None or rec_lon is None or (rec_lat == 0 and rec_lon == 0):
                                continue
                        dist = haversine_km(lat, lon, rec_lat, rec_lon)
                        if dist <= radius_km:
                                name = None
                                for name_field in ["name", "Name", "NAME", "facility_name", "Facility Name", "Facility"]:
                                        if name_field in record:
                                                name = record[name_field]
                                                break
                                address = None
                                for addr_field in ["address", "Address", "ADDRESS", "location", "Location", "Address Block"]:
                                        if addr_field in record:
                                                address = record[addr_field]
                                                break
                                results.append({
                                        "lat": rec_lat,
                                        "lon": rec_lon,
                                        "name": name or "Unnamed Facility",
                                        "address": address or ""
                                })
                except (ValueError, TypeError, KeyError):
                        continue
        return results[:limit]
    return results[:limit]


# ============================================================================
# MOCK BACKEND — MEMBER 5: replace bodies with real API when ready
# ============================================================================

def mock_predict_price(postal_code, flat_type, floor_area):
    """
    MOCK — replace with: safe_post("/predict/sell", payload)
    Expected real response: { price: int, low: int, high: int, median_town: int }
    """
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
    """
    MOCK — replace with: safe_post("/recommend", full_payload)
    Expected real response: list of dicts, each with:
      { town, rooms, postal, buy_price, amenity_score,
        mrt_dist_km, clinic_dist_m, hawker_dist_m, park_dist_m }
    """
    return [
        {"town": "Ang Mo Kio", "rooms": 3, "postal": "560123", "buy_price": 480_000,
         "amenity_score": 84, "mrt_dist_km": 0.45, "clinic_dist_m": 220, "hawker_dist_m": 320, "park_dist_m": 380},
        {"town": "Bedok", "rooms": 3, "postal": "460123", "buy_price": 420_000,
         "amenity_score": 78, "mrt_dist_km": 0.35, "clinic_dist_m": 180, "hawker_dist_m": 260, "park_dist_m": 410},
        {"town": "Tampines", "rooms": 3, "postal": "520123", "buy_price": 430_000,
         "amenity_score": 80, "mrt_dist_km": 0.55, "clinic_dist_m": 260, "hawker_dist_m": 290, "park_dist_m": 520},
    ]


def weights_from_sliders(hc, tr, hw, rec):
    """Normalise raw slider values (1-10) into weights summing to 1."""
    raw = {"healthcare": float(hc), "transport": float(tr), "hawker": float(hw), "recreation": float(rec)}
    s = sum(raw.values()) or 1.0
    return {k: raw[k] / s for k in raw}


# ============================================================================
# MAP — MEMBER 6: this is your main section
# ============================================================================


def haversine_km(lat1, lon1, lat2, lon2):
    """Calculate the straight-line distance in km between two lat/lon points."""
    R = 6371.0
    lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c
def leaflet_map_html(center_lat, center_lon, points, amenities, zoom=14):
    """
    Generate a complete Leaflet HTML page as a string for iframe injection.
    MEMBER 6: customise tile layer, marker styles, legend, popups, zoom.
    """
    def js_point(p):
        return {
            "name": p["name"], 
            "lat": p["lat"], 
            "lon": p["lon"], 
            "color": p.get("color", "#0ea5e9"),
            "price": p.get("price", "N/A"),        # Adding price information
            "distance": p.get("distance", "N/A")   # Adding distance information
        }

    def js_am(a):
        return {
            "name": a.get("name") or "Unnamed amenity", 
            "lat": a["lat"], 
            "lon": a["lon"], 
            "kind": a.get("kind", "Amenity"),
            "address": a.get("address") or "Address not available",
            "distance": a.get("distance", "N/A")
        }

    points_js = [js_point(p) for p in points]
    amen_js = [js_am(a) for a in amenities]

    return f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
    integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin=""/>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
    integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
  <style>
    html, body {{ height: 100%; margin: 0; }}
    #map {{ height: 100%; width: 100%; border-radius: 18px; }}
    /* MEMBER 6: adjust popup font styling */
    .leaflet-popup-content {{ font-size: 16px; font-weight: 700; }}
    /* MEMBER 6: adjust legend position, colours, font */
    .legend {{
      position: absolute; bottom: 12px; left: 12px; z-index: 999;
      background: rgba(255,255,255,0.92); padding: 10px 12px;
      border: 1px solid rgba(15,23,42,0.15); border-radius: 12px;
      font-family: system-ui; font-size: 14px; font-weight: 800; color: #0f172a;
    }}
    .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 999px; margin-right: 8px; }}
    .amenity-icon {{ font-size: 24px; background: none; border: none; }}
  </style>
</head>
<body>
  <div id="map"></div>
  <!-- MEMBER 6: update legend labels and dot colours -->
  <div class="legend">
    <span style="background-color:#0ea5e9; padding: 5px;">🏠 Your flat</span><br>
    <span style="background-color:#22c55e; padding: 5px;">🏢 Recommended flats</span><br>
    <span>🏥 Healthcare</span><br>
    <span>🚇 Transport</span><br>
    <span>🍜 Hawker Centre</span><br>
    <span>🌳 Nature</span>
  </div>
  <script>
    const center = [{center_lat}, {center_lon}];
    const map = L.map('map', {{ zoomControl: true }}).setView(center, {zoom});


    // MEMBER 6: tile layer — could switch to OneMap tiles
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 19, attribution: '&copy; OpenStreetMap'
    }}).addTo(map);

    const points = {points_js};
    const amenities = {amen_js};
    const homeIcon = L.icon({{
      iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-blue.png',
      iconSize: [25, 41],
      iconAnchor: [12, 41],
      popupAnchor: [1, -34],
    }});
    const recommendIcon = L.icon({{
      iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-green.png',
      iconSize: [25, 41],
      iconAnchor: [12, 41],
      popupAnchor: [1, -34],
    }});
    const amenityIcon = L.icon({{
      iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-orange.png',
      iconSize: [25, 41],
      iconAnchor: [12, 41],
      popupAnchor: [1, -34],
    }});

    // Add markers for points
    points.forEach((p, index) => {{
      const icon = index === 0 ? homeIcon : recommendIcon;
      L.marker([p.lat, p.lon], {{ icon: icon }}).addTo(map).bindPopup(`<b>${{p.name}}</b><br>Estimated price: $${{p.price}}<br>Distance from your flat: ${{p.distance}}`);
    }});

    // Add markers for amenities
    amenities.forEach(a => {{
      let iconHtml = '';
      switch(a.kind) {{
        case 'healthcare': iconHtml = '🏥'; break;
        case 'transport': iconHtml = '🚇'; break;
        case 'hawker centre': iconHtml = '🍜'; break;
        case 'nature': iconHtml = '🌳'; break;
        default: iconHtml = '📍';
      }}
      const amenityIcon = L.divIcon({{
        html: iconHtml,
        className: 'amenity-icon',
        iconSize: [30, 30],
        iconAnchor: [15, 15]
      }});
      L.marker([a.lat, a.lon], {{ icon: amenityIcon }}).addTo(map).bindPopup(`<b>${{a.name}}</b><br>Address: ${{a.address}}<br>Distance: ${{a.distance}} from your HDB`);
    }});

    // MEMBER 6: adjust fit-bounds padding
    const all = points.map(p => [p.lat, p.lon]).concat(amenities.map(a => [a.lat, a.lon]));
    if (all.length > 1) {{ map.fitBounds(L.latLngBounds(all).pad(0.18)); }}
  </script>
</body>
</html>
"""




# ============================================================================
# STEP INDICATOR — MEMBER 7: style the progress bar
# ============================================================================

def step_indicator(step):
    """
    The 1 → 2 → 3 → 4 progress bar at the top of every page.
    MEMBER 7: adjust circle size, colours, connector style, label fonts.
    """
    steps = [("1", "Price estimate"), ("2", "What matters"), ("3", "Your limits"), ("4", "Results")]
    chips = []
    for i, (num, name) in enumerate(steps, start=1):
        active = (i == step)
        chips.append(
            html.Div([
                html.Div(num, style={
                    "width": "52px",             # MEMBER 7: circle diameter
                    "height": "52px",
                    "borderRadius": "999px",
                    "display": "flex", "alignItems": "center", "justifyContent": "center",
                    "fontSize": "22px",          # MEMBER 7: number font size
                    "fontWeight": "950",
                    "background": "#0ea5e9" if active else "rgba(15,23,42,0.08)",  # MEMBER 7: active vs inactive
                    "color": "white" if active else "#0f172a",
                    "border": "2px solid rgba(15,23,42,0.12)",
                }),
                html.Div(name, style={
                    "fontSize": "18px",          # MEMBER 7: label font size
                    "fontWeight": "950",
                    "opacity": 1 if active else 0.72,
                    "marginTop": "8px",
                    "textAlign": "center",
                    "width": "140px",
                }),
            ], style={"display": "flex", "flexDirection": "column", "alignItems": "center"})
        )
        if i < 4:
            # MEMBER 7: connector line between steps
            chips.append(html.Div(style={
                "height": "4px", "flex": "1",
                "background": "rgba(15,23,42,0.12)",  # MEMBER 7: connector colour
                "borderRadius": "999px",
                "margin": "0 12px",
                "alignSelf": "center",
            }))
    return html.Div(chips, style={"display": "flex", "alignItems": "center", "marginTop": "16px"})


def nav_row(step):
    """Back/Next navigation buttons. MEMBER 7: adjust labels and disabled appearance."""
    labels = {1: "Next →", 2: "Next →", 3: "See results →", 4: "Back"}
    next_label = labels.get(step, "Next →")

    back_style = dict(btn_back)
    if step == 1:
        back_style.update({"opacity": "0.45", "cursor": "not-allowed", "boxShadow": "none"})

    return html.Div([
        html.Button("← Back", id="btn_back", n_clicks=0, style=back_style, disabled=(step == 1)),
        html.Button(next_label, id="btn_next", n_clicks=0, style=btn_primary),
    ], style={"display": "flex", "gap": "14px", "justifyContent": "space-between", "marginTop": "18px"})


# ============================================================================
# PAGES
# ============================================================================

# ── STEP 1: Estimate your flat ─────────────────────────────────────────────
# MEMBER 7: form layout   |   MEMBER 5: callback wiring

def step_1_estimate():
    return html.Div([
        # MEMBER 7: step heading — adjust fontSize, fontWeight
        html.Div("Step 1: Estimate your flat price", style={"fontSize": "36px", "fontWeight": "950"}),
        html.Div([
            html.Div("Postal code", style=label_style),
            dcc.Input(id="sell_postal", type="text", placeholder="Example: 560123", style=input_style_big),
            html.Div(style={"height": "14px"}),  # MEMBER 7: spacing between fields

            html.Div("Flat type", style=label_style),
            dcc.Dropdown(
                id="sell_flat_type",
                options=["2 ROOM", "3 ROOM", "4 ROOM", "5 ROOM", "EXECUTIVE"],
                value="4 ROOM", clearable=False,
                style={"fontSize": "22px"},  # MEMBER 7: dropdown font size
            ),
            html.Div(style={"height": "14px"}),

            html.Div("Floor area (sqm) (optional)", style=label_style),
            dcc.Input(id="sell_area", type="number", value=90, style=input_style_big),
            html.Div(style={"height": "16px"}),

            html.Button("Estimate price", id="btn_estimate", n_clicks=0, style=btn_primary),
            html.Div(id="sell_pred_box"),
            html.Div(id="step1_saved_banner"),
        ], style=card_style),
    ])


# ── STEP 2: Priority sliders ──────────────────────────────────────────────
# MEMBER 7: slider layout and styling

def step_2_preferences():
    slider_style = {"padding": "10px 6px"}  # MEMBER 7: slider container padding
    return html.Div([
        html.Div("Step 2: Tell us what matters to you", style={"fontSize": "36px", "fontWeight": "950"}),
        html.Div([
            # MEMBER 7: adjust emoji, label text, default value for each slider
            html.Div("🏥 Healthcare nearby", style=label_style),
            html.Div(dcc.Slider(id="pref_healthcare", min=1, max=10, step=1, value=8,
                                marks={i: str(i) for i in range(1, 11)}), style=slider_style),
            html.Hr(),

            html.Div("🚆 Transport (MRT / bus)", style=label_style),
            html.Div(dcc.Slider(id="pref_transport", min=1, max=10, step=1, value=7,
                                marks={i: str(i) for i in range(1, 11)}), style=slider_style),
            html.Hr(),

            html.Div("🍲 Hawker centres / food", style=label_style),
            html.Div(dcc.Slider(id="pref_hawker", min=1, max=10, step=1, value=6,
                                marks={i: str(i) for i in range(1, 11)}), style=slider_style),
            html.Hr(),

            html.Div("🌳 Parks / recreation", style=label_style),
            html.Div(dcc.Slider(id="pref_recreation", min=1, max=10, step=1, value=6,
                                marks={i: str(i) for i in range(1, 11)}), style=slider_style),

            html.Div(id="pref_saved_banner"),
        ], style=card_style),
    ])


# ── STEP 3: Budget & constraints ──────────────────────────────────────────
# MEMBER 7: form layout   |   MEMBER 8: expand town list

def step_3_limits():
    return html.Div([
        html.Div("Step 3: Tell us your limits", style={"fontSize": "36px", "fontWeight": "950"}),
        html.Div([
            html.Div("💵 Maximum budget to buy ($)", style=label_style),
            dcc.Input(id="lim_budget", type="number", value=550000, style=input_style_big),
            html.Div(style={"height": "14px"}),

            html.Div("🛏️ Minimum rooms", style=label_style),
            dcc.Dropdown(id="lim_min_rooms", options=[2, 3, 4, 5], value=3, clearable=False,
                         style={"fontSize": "22px"}),
            html.Div(style={"height": "14px"}),

            # MEMBER 8: verify this covers all 26 HDB towns
            html.Div("📍 Preferred towns (optional)", style=label_style),
            dcc.Dropdown(
                id="lim_towns",
                options=[
                    "Ang Mo Kio", "Bedok", "Bishan", "Bukit Batok", "Bukit Merah",
                    "Bukit Panjang", "Choa Chu Kang", "Clementi", "Geylang",
                    "Hougang", "Jurong East", "Jurong West", "Kallang/Whampoa",
                    "Marine Parade", "Pasir Ris", "Punggol", "Queenstown",
                    "Sembawang", "Sengkang", "Serangoon", "Tampines",
                    "Toa Payoh", "Woodlands", "Yishun",
                ],
                multi=True, value=[],
                placeholder="Select towns (optional)",
                style={"fontSize": "22px"},
            ),

            html.Div(id="limits_saved_banner"),
        ], style=card_style),
    ])


# ── STEP 4: Results ───────────────────────────────────────────────────────
# MEMBER 8: result cards + layout   |   MEMBER 6: map

def step_4_results():
    return html.Div([
        html.Div("Step 4: Results", style={"fontSize": "36px", "fontWeight": "950"}),
        html.Div([
            # Left column: results — MEMBER 8: owns this section
            html.Div([
                html.Button("Run results", id="btn_run_all", n_clicks=0, style=btn_primary),
                html.Div(id="results_list", style={"marginTop": "16px"}),
                html.Div([
                    html.Button("Start over", id="btn_reset", n_clicks=0, style=btn_reset),
                ], style={"marginTop": "14px"}),
            ], style={
                "flex": "1",
                "minWidth": "420px",  # MEMBER 8: min width of results column
            }),

            # Right column: map — MEMBER 6: owns this section
            html.Div([
                html.Div("Map (zoom and drag)", style={
                    "fontSize": "22px",   # MEMBER 6: map header font size
                    "fontWeight": "950",
                    "marginBottom": "10px",
                }),
                html.Iframe(
                    id="results_map",
                    srcDoc="<html><body style='font-family:system-ui;padding:16px'>Run results to view map.</body></html>",
                    style={
                        "width": "100%",
                        "height": "720px",     # MEMBER 6: map height
                        "border": "0",
                        "borderRadius": "18px",  # MEMBER 6: map corner rounding
                        "boxShadow": SHADOW,
                        "background": "white",
                    },
                ),
            ], style={
                "flex": "1.2",
                "minWidth": "520px",  # MEMBER 6: min width of map column
            }),
        ], style={
            **card_style,
            "display": "flex",
            "gap": "18px",            # MEMBER 7: gap between results and map columns
            "alignItems": "flex-start",
        }),
    ])


# ============================================================================
# LAYOUT — MEMBER 5: overall structure
# ============================================================================

app.layout = html.Div([
    # Client-side stores — MEMBER 5: data persists across steps
    dcc.Store(id="step", data=1),
    dcc.Store(id="sell_payload"),
    dcc.Store(id="sell_geo"),
    dcc.Store(id="sell_pred"),
    dcc.Store(id="prefs_weights"),
    dcc.Store(id="constraints"),
    dcc.Store(id="recs_data"),

    html.Div([
        html.Div([
            # MEMBER 7: title emoji and text
            html.H1(["🏠", html.Span("Downsizing Helper")], style=title_style),
            html.Div(id="step_indicator"),
        ], style=container_style),
        html.Div(id="main_content", style=container_style),
        html.Div(id="nav_area", style=container_style),
    ], style=base_page_style),
])


# ============================================================================
# CALLBACKS — MEMBER 5: owns all callback wiring
# ============================================================================

# ── Render current step ──

@app.callback(
    Output("main_content", "children"),
    Output("nav_area", "children"),
    Output("step_indicator", "children"),
    Input("step", "data"),
)
def render_step(step):
    step = int(step or 1)
    pages = {1: step_1_estimate, 2: step_2_preferences, 3: step_3_limits, 4: step_4_results}
    return pages[step](), nav_row(step), step_indicator(step)


# ── Navigation ──

@app.callback(
    Output("step", "data"),
    Input("btn_next", "n_clicks"),
    Input("btn_back", "n_clicks"),
    State("step", "data"),
    prevent_initial_call=True,
)
def go_next_back(n_next, n_back, step):
    trig = dash.callback_context.triggered_id
    step = int(step or 1)
    if trig == "btn_next":
        return min(step + 1, 4)
    if trig == "btn_back":
        return max(step - 1, 1)
    return step


# ── Step 1: auto-save + geocode ──

@app.callback(
    Output("sell_payload", "data"),
    Output("sell_geo", "data"),
    Output("step1_saved_banner", "children"),
    Input("sell_postal", "value"),
    Input("sell_flat_type", "value"),
    Input("sell_area", "value"),
)
def autosave_step1(postal, flat_type, area):
    postal = (postal or "").strip()
    payload = {
        "postal": postal,
        "flat_type": flat_type,
        "floor_area_sqm": float(area) if area not in (None, "") else None,
    }
    if not postal:
        return payload, None, html.Div("Please enter your postal code.", style=banner_warn)
    geo = onemap_search(postal) or onemap_search(f"Singapore {postal}")
    if not geo:
        return payload, None, html.Div("⚠️ Could not locate postal code on map. Please check it.", style=banner_warn)
    return payload, geo, html.Div("✅ Saved. We found your location.", style=banner_ok)


# ── Step 1: estimate price ──

@app.callback(
    Output("sell_pred", "data"),
    Output("sell_pred_box", "children"),
    Input("btn_estimate", "n_clicks"),
    State("sell_payload", "data"),
    prevent_initial_call=True,
)
def estimate_price(n, sell_payload):
    if not sell_payload or not sell_payload.get("postal"):
        return None, html.Div("Please enter your postal code first.", style=banner_warn)

    # MEMBER 5: try real backend first, fall back to mock
    pred = safe_post("/predict/sell", sell_payload)
    if not pred:
        pred = mock_predict_price(sell_payload["postal"], sell_payload["flat_type"], sell_payload.get("floor_area_sqm"))

    # MEMBER 7: style price display — large number, confidence range
    box = html.Div([
        html.Div("Estimated selling price", style={"fontSize": "22px", "fontWeight": "950", "opacity": "0.85"}),
        html.Div(f"${pred['price']:,.0f}", style={
            "fontSize": "52px",           # MEMBER 7: main price font size
            "fontWeight": "950",
        }),
        html.Div(f"Range: ${pred['low']:,.0f} – ${pred['high']:,.0f}", style={
            "fontSize": "22px", "fontWeight": "900", "opacity": "0.85",
        }),
        html.Div(f"Town median (rough): ${pred.get('median_town', int(pred['price'] * 0.98)):,.0f}", style={
            "fontSize": "22px", "fontWeight": "900", "opacity": "0.80",
        }),
    ], style={"marginTop": "14px"})
    return pred, box


# ── Step 2: save weights ──

@app.callback(
    Output("prefs_weights", "data"),
    Output("pref_saved_banner", "children"),
    Input("pref_healthcare", "value"),
    Input("pref_transport", "value"),
    Input("pref_hawker", "value"),
    Input("pref_recreation", "value"),
)
def save_prefs(hc, tr, hw, rec):
    return weights_from_sliders(hc, tr, hw, rec), html.Div("✅ Saved.", style=banner_ok)


# ── Step 3: save constraints ──

@app.callback(
    Output("constraints", "data"),
    Output("limits_saved_banner", "children"),
    Input("lim_budget", "value"),
    Input("lim_min_rooms", "value"),
    Input("lim_towns", "value"),
)
def save_limits(budget, min_rooms, towns):
    return {
        "max_budget": int(budget or 0),
        "min_rooms": int(min_rooms or 2),
        "preferred_towns": towns or [],
    }, html.Div("✅ Saved.", style=banner_ok)


# ── Step 4: run results ──
# MEMBER 5: orchestration | MEMBER 8: cards | MEMBER 6: map

@app.callback(
    Output("results_list", "children"),
    Output("results_map", "srcDoc"),
    Output("recs_data", "data"),
    Input("btn_run_all", "n_clicks"),
    State("sell_payload", "data"),
    State("sell_geo", "data"),
    State("sell_pred", "data"),
    State("prefs_weights", "data"),
    State("constraints", "data"),
    prevent_initial_call=True,
)
def run_results(n, sell_payload, sell_geo, sell_pred, prefs_w, constraints):
    # Validation
    if not sell_payload or not sell_payload.get("postal"):
        return html.Div("Please go back to Step 1 and enter your postal code.", style=banner_warn), dash.no_update, None
    if not sell_geo:
        return html.Div("We could not locate your flat. Please check postal code in Step 1.", style=banner_warn), dash.no_update, None
    if not prefs_w:
        return html.Div("Please complete Step 2.", style=banner_warn), dash.no_update, None
    if not constraints:
        return html.Div("Please complete Step 3.", style=banner_warn), dash.no_update, None

    if not sell_pred:
        sell_pred = mock_predict_price(sell_payload["postal"], sell_payload["flat_type"], sell_payload.get("floor_area_sqm"))

    # MEMBER 5: replace mock with real backend call when ready:
    #   payload = {"sell_payload": sell_payload, "sell_pred": sell_pred,
    #              "weights": prefs_w, "constraints": constraints}
    #   recs = safe_post("/recommend", payload)
    #   if not recs:
    #       recs = mock_recommendations(constraints)
    recs = mock_recommendations(constraints)

    # Geocode each recommendation
    for r in recs:
        geo = onemap_search(r["postal"]) or onemap_search(f"Singapore {r['postal']}")
        if geo:
            r["lat"], r["lon"], r["address"] = geo["lat"], geo["lon"], geo["address"]
            
            # Calculate the distance from the user's current flat (sell_geo) to this recommended flat
            r["dist_from_home_km"] = haversine_km(sell_geo["lat"], sell_geo["lon"], r["lat"], r["lon"])
        else:
            # Fallback for geocoding failure
            r["lat"] = sell_geo["lat"] + 0.01  # Default to slightly different coordinates
            r["lon"] = sell_geo["lon"] + 0.01
            r["address"] = f"{r['town']} (approx)"
            r["dist_from_home_km"] = 0.01  # Default distance if geocoding fails

    # Derived fields
    for r in recs:
        r["cash_unlocked"] = int(sell_pred["price"] - r["buy_price"])
        dist = haversine_km(sell_geo["lat"], sell_geo["lon"], r["lat"], r["lon"])
        r["dist_from_home_km"] = round(dist, 2) if dist is not None else 0.0

    # ── Result cards — MEMBER 8: customise everything in this block ──
    cards = []
    for i, r in enumerate(recs, start=1):
        pg_url = build_propertyguru_url(
            town=r["town"], rooms=r["rooms"],
            min_price=max(0, int(r["buy_price"] * 0.90)),
            max_price=int(r["buy_price"] * 1.10),
        )
        cards.append(html.Div([
            # MEMBER 8: card title
            html.Div(f"#{i} • {r['town']} • {r['rooms']} rooms", style={
                "fontSize": "28px",           # MEMBER 8: title size
                "fontWeight": "950",
            }),
            # MEMBER 8: buy price
            html.Div(f"Buy price (estimate): ${r['buy_price']:,.0f}", style={
                "fontSize": "22px", "fontWeight": "900",
            }),
            # MEMBER 8: cash unlocked
            html.Div(f"Cash unlocked (estimate): ${r['cash_unlocked']:,.0f}", style={
                "fontSize": "22px", "fontWeight": "900",
            }),
            # MEMBER 8: distance
            html.Div(f"Distance from your flat: {r['dist_from_home_km']} km", style={
                "fontSize": "20px", "fontWeight": "900", "opacity": "0.88",
            }),
            # MEMBER 8: amenity distances
            html.Div(
                f"Amenities nearby: Clinic ~{r['clinic_dist_m']}m • Hawker ~{r['hawker_dist_m']}m • Park ~{r['park_dist_m']}m",
                style={"fontSize": "20px", "fontWeight": "850", "opacity": "0.85"},
            ),
            # MEMBER 8: MRT distance
            html.Div(f"MRT distance (approx): {r['mrt_dist_km']:.2f} km", style={
                "fontSize": "20px", "fontWeight": "850", "opacity": "0.85",
            }),
            # MEMBER 8: PropertyGuru link
            html.A("🔎 View matching listings on PropertyGuru", href=pg_url, target="_blank", style={
                "display": "inline-block",
                "marginTop": "10px",
                "fontSize": "20px",           # MEMBER 8: link size
                "fontWeight": "950",
                "textDecoration": "none",
                "color": "#0ea5e9",           # MEMBER 8: link colour
            }),
        ], style={**card_style, "marginTop": "14px"}))

    # ── Map — MEMBER 6: customise markers and amenities ──
    points = [
        {"name": f"Your flat ({sell_payload['postal']})", "lat": sell_geo["lat"], "lon": sell_geo["lon"], "color": "#0ea5e9"},
    ]
    for r in recs:
        points.append({
            "name": f"Option: {r['town']} ({r['postal']})",
            "lat": r["lat"], 
            "lon": r["lon"], 
            "color": "#22c55e", 
            "price": r["buy_price"],
            "distance": f"{r['dist_from_home_km']} km"
        })

    # Fetch real amenities from data.gov.sg — MEMBER 6: customize collection IDs
    amenities = []
    base_lat, base_lon = sell_geo["lat"], sell_geo["lon"]
    radius_km = 2.0
    hawker_debug_rows = []
    for idx, r in enumerate(recs):
        rec_lat, rec_lon = r["lat"], r["lon"]

        # Healthcare (CHAS clinics, sorted by distance)
        healthcare_amenities = get_amenities_from_datagov("healthcare", rec_lat, rec_lon, radius_km=2.0, limit=9999)
        healthcare_with_dist = []
        for amenity in healthcare_amenities:
            dist = haversine_km(rec_lat, rec_lon, amenity["lat"], amenity["lon"])
            healthcare_with_dist.append({**amenity, "distance_km": dist})
        healthcare_with_dist.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 9999)
        logger.info(f"DEBUG: Found {len(healthcare_with_dist)} clinics for rec #{idx+1} at ({rec_lat}, {rec_lon})")
        for amenity in healthcare_with_dist:
            dist_from_home = amenity["distance_km"]
            dist_str = f"{dist_from_home:.2f} km" if dist_from_home is not None else "N/A"
            amenities.append({
                "name": amenity["name"],
                "lat": amenity["lat"],
                "lon": amenity["lon"],
                "kind": "healthcare",
                "address": amenity.get("address", ""),
                "distance": dist_str
            })

        # Hawker centres (API, fallback if needed)
        hawker_amenities = get_amenities_from_datagov("hawker", rec_lat, rec_lon, radius_km=2.0, limit=100)
        hawker_with_dist = []
        for amenity in hawker_amenities:
            dist = haversine_km(rec_lat, rec_lon, amenity["lat"], amenity["lon"])
            if dist is not None and dist <= 2.0:
                hawker_with_dist.append({**amenity, "distance_km": dist})
        hawker_with_dist.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 9999)
        logger.info(f"DEBUG: Found {len(hawker_with_dist)} hawker centres within 2km for rec #{idx+1} at ({rec_lat}, {rec_lon})")
        for amenity in hawker_with_dist:
            dist_from_home = amenity["distance_km"]
            dist_str = f"{dist_from_home:.2f} km" if dist_from_home is not None else "N/A"
            amenities.append({
                "name": amenity["name"],
                "lat": amenity["lat"],
                "lon": amenity["lon"],
                "kind": "hawker centre",
                "address": amenity.get("address", ""),
                "distance": dist_str
            })
            hawker_debug_rows.append([
                amenity["name"], amenity.get("address", ""), amenity["lat"], amenity["lon"], dist_str
            ])

        # Transport (API dataset linked by TRANSPORT_DATASET_ID)
        transport_amenities = get_amenities_from_datagov("transport", rec_lat, rec_lon, radius_km=2.0, limit=100)
        transport_with_dist = []
        for amenity in transport_amenities:
            dist = haversine_km(rec_lat, rec_lon, amenity["lat"], amenity["lon"])
            if dist is not None and dist <= 2.0:
                transport_with_dist.append({**amenity, "distance_km": dist})
        transport_with_dist.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 9999)
        logger.info(f"DEBUG: Found {len(transport_with_dist)} transport points within 2km for rec #{idx+1} at ({rec_lat}, {rec_lon})")
        for amenity in transport_with_dist:
            dist_from_home = amenity["distance_km"]
            dist_str = f"{dist_from_home:.2f} km" if dist_from_home is not None else "N/A"
            amenities.append({
                "name": amenity["name"],
                "lat": amenity["lat"],
                "lon": amenity["lon"],
                "kind": "transport",
                "address": amenity.get("address", ""),
                "distance": dist_str
            })

        # Nature parks (API, fallback if needed)
        park_amenities = get_amenities_from_datagov("parks", rec_lat, rec_lon, radius_km=2.0, limit=100)
        park_with_dist = []
        for park in park_amenities:
            dist = haversine_km(rec_lat, rec_lon, park["lat"], park["lon"])
            if dist is not None and dist <= 2.0:
                park_with_dist.append({**park, "distance_km": dist})
        park_with_dist.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 9999)
        logger.info(f"DEBUG: Found {len(park_with_dist)} parks within 2km for rec #{idx+1} at ({rec_lat}, {rec_lon})")
        for park in park_with_dist:
            dist_from_home = park["distance_km"]
            dist_str = f"{dist_from_home:.2f} km" if dist_from_home is not None else "N/A"
            amenities.append({
                "name": park["name"],
                "lat": park["lat"],
                "lon": park["lon"],
                "kind": "nature",
                "address": park.get("address", ""),
                "distance": dist_str
            })
            hawker_debug_rows.append([
                park["name"], park.get("address", ""), park["lat"], park["lon"], dist_str
            ])

        # NOTE: We intentionally skip healthcare/parks/mrt for now to reduce API load.

    map_doc = leaflet_map_html(sell_geo["lat"], sell_geo["lon"], points, amenities, zoom=14)

    # Display hawker centre debug table
    hawker_table = html.Table([
        html.Tr([html.Th("Name"), html.Th("Address"), html.Th("Lat"), html.Th("Lon"), html.Th("Distance from home")])
    ] + [html.Tr([html.Td(x) for x in row]) for row in hawker_debug_rows], style={"marginTop": "18px", "fontSize": "16px", "background": "#f9fafb", "borderRadius": "12px", "padding": "8px"})

    return html.Div([*cards, hawker_table]), map_doc, recs


# ── Reset ──

@app.callback(
    Output("step", "data", allow_duplicate=True),
    Output("sell_payload", "data", allow_duplicate=True),
    Output("sell_geo", "data", allow_duplicate=True),
    Output("sell_pred", "data", allow_duplicate=True),
    Output("prefs_weights", "data", allow_duplicate=True),
    Output("constraints", "data", allow_duplicate=True),
    Output("recs_data", "data", allow_duplicate=True),
    Input("btn_reset", "n_clicks"),
    prevent_initial_call=True,
)
def reset_all(n):
    return 1, None, None, None, None, None, None


# ============================================================================
# RUN
# ============================================================================
if __name__ == "__main__":
    app.run(debug=True)