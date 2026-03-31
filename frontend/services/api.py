import logging
import requests
import time
import math
import re
import threading

from config.settings import (
    BACKEND_URL,
    TIMEOUT_SEC,
    ONEMAP_BASE_URL,
    ONEMAP_SEARCH_URL,
    ONEMAP_REVERSE_GEOCODE_URL,
    ONEMAP_TOKEN,
    ONEMAP_API_EMAIL,
    ONEMAP_API_PASSWORD,
    AMENITY_CACHE_TTL,
    AMENITY_CACHE_VERSION,
    API_REQUEST_DELAY_SEC,
    FALLBACK_AMENITIES,
)

AMENITY_CACHE = {}
REVERSE_GEOCODE_CACHE = {}
LAST_API_REQUEST_TIME = None
_ONEMAP_AUTH_CACHE = {"token": None, "expires_at": 0}
_ONEMAP_AUTH_LOCK = threading.Lock()
_ONEMAP_AUTH_BACKOFF = {"retry_after": 0}


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c


def _extract_token_expiry_epoch(token_response):
    now_epoch = time.time()
    for key in ("expiry_timestamp", "exp", "expires_at", "expires_on"):
        value = token_response.get(key)
        try:
            if value is not None:
                return float(value)
        except Exception:
            continue

    for key in ("expires_in", "expiry", "expiresIn"):
        value = token_response.get(key)
        try:
            if value is not None:
                return now_epoch + float(value)
        except Exception:
            continue

    return now_epoch + (12 * 60 * 60)


def get_onemap_access_token(force_refresh=False):
    now = time.time()

    # Avoid hammering auth endpoint when credentials are wrong/expired.
    if now < _ONEMAP_AUTH_BACKOFF["retry_after"]:
        return ONEMAP_TOKEN or None

    if not force_refresh and _ONEMAP_AUTH_CACHE["token"] and time.time() < _ONEMAP_AUTH_CACHE["expires_at"]:
        return _ONEMAP_AUTH_CACHE["token"]

    with _ONEMAP_AUTH_LOCK:
        if not force_refresh and _ONEMAP_AUTH_CACHE["token"] and time.time() < _ONEMAP_AUTH_CACHE["expires_at"]:
            return _ONEMAP_AUTH_CACHE["token"]

        if ONEMAP_API_EMAIL and ONEMAP_API_PASSWORD:
            try:
                response = requests.post(
                    f"{ONEMAP_BASE_URL}/api/auth/post/getToken",
                    json={"email": ONEMAP_API_EMAIL, "password": ONEMAP_API_PASSWORD},
                    timeout=TIMEOUT_SEC,
                )
                response.raise_for_status()
                token_data = response.json() or {}
                token = token_data.get("access_token")
                if token:
                    _ONEMAP_AUTH_CACHE["token"] = token
                    _ONEMAP_AUTH_CACHE["expires_at"] = _extract_token_expiry_epoch(token_data) - 60
                    _ONEMAP_AUTH_BACKOFF["retry_after"] = 0
                    return token
            except Exception as e:
                _ONEMAP_AUTH_BACKOFF["retry_after"] = time.time() + 300
                logging.getLogger("amenity_debug").warning(f"Failed to refresh OneMap token: {e}")

        if ONEMAP_TOKEN:
            return ONEMAP_TOKEN

        return None


def _get_onemap_auth_headers():
    token = get_onemap_access_token()
    if not token:
        return {}
    token_value = str(token).strip()
    if not token_value.lower().startswith("bearer "):
        token_value = f"Bearer {token_value}"
    return {"Authorization": token_value}


def safe_post(path, payload):
    try:
        r = requests.post(f"{BACKEND_URL}{path}", json=payload, timeout=TIMEOUT_SEC)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def onemap_search(query):
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
    cache_key = f"{float(lat):.5f}_{float(lon):.5f}_{int(buffer)}"
    if cache_key in REVERSE_GEOCODE_CACHE:
        return REVERSE_GEOCODE_CACHE[cache_key]

    try:
        params = {
            "location": f"{float(lat)},{float(lon)}",
            "buffer": int(buffer),
            "addressType": "All"
        }
        headers = _get_onemap_auth_headers()
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


def get_nearby_amenities(amenity_type, lat, lon, radius_km=3, limit=3):
    global LAST_API_REQUEST_TIME

    cache_key = f"{AMENITY_CACHE_VERSION}_{amenity_type}_{float(lat):.3f}_{float(lon):.3f}"
    if cache_key in AMENITY_CACHE:
        cache_entry = AMENITY_CACHE[cache_key]
        if time.time() - cache_entry["timestamp"] < AMENITY_CACHE_TTL:
            return cache_entry["data"]
        else:
            del AMENITY_CACHE[cache_key]

    if LAST_API_REQUEST_TIME is not None:
        elapsed = time.time() - LAST_API_REQUEST_TIME
        if elapsed < API_REQUEST_DELAY_SEC:
            wait_time = API_REQUEST_DELAY_SEC - elapsed
            print(f"Throttling {amenity_type}: waiting {wait_time:.1f}s...")
            time.sleep(wait_time)

    # ── OneMap theme-based amenity types ──
    onemap_theme_map = {
        "healthcare": ["moh_hospitals", "vaccination_polyclinics"],
        "hawker": ["ssot_hawkercentres"],
        "parks": ["nationalparks"],
    }

    if amenity_type in onemap_theme_map:
        try:
            results = _fetch_onemap_theme_amenities(
                onemap_theme_map[amenity_type], lat, lon, radius_km, limit
            )
            if not results:
                logging.getLogger("amenity_debug").debug(
                    f"[OneMap] {amenity_type} API returned no records within {radius_km}km; using fallback."
                )
                results = _get_nearby_fallback_amenities(amenity_type, lat, lon, radius_km, limit)
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

    if amenity_type in ("transport",):
        try:
            results = _fetch_onemap_transport(lat, lon, radius_km, limit)
            if not results:
                results = _get_nearby_fallback_amenities(amenity_type, lat, lon, radius_km, limit)
            AMENITY_CACHE[cache_key] = {
                "data": results,
                "timestamp": time.time()
            }
            return results
        except Exception as e:
            print(f"API error for transport: {e}. Using fallback mock data.")
            mock_results = _get_nearby_fallback_amenities(amenity_type, lat, lon, radius_km, limit)
            AMENITY_CACHE[cache_key] = {
                "data": mock_results,
                "timestamp": time.time()
            }
            return mock_results

    print(f"Using fallback mock data for {amenity_type}")
    mock_results = _get_nearby_fallback_amenities(amenity_type, lat, lon, radius_km, limit)
    AMENITY_CACHE[cache_key] = {
        "data": mock_results,
        "timestamp": time.time()
    }
    return mock_results


def _fetch_onemap_theme_amenities(theme_names, lat, lon, radius_km=3, limit=3):
    """Generic fetcher for OneMap theme-based amenities (healthcare, hawker, parks)."""
    logger = logging.getLogger("amenity_debug")
    logger.debug(f"[OneMap] Fetching themes {theme_names} near ({lat}, {lon}), radius={radius_km}km")
    themes = theme_names
    results = []
    for theme in themes:
        url = f"{ONEMAP_BASE_URL}/api/public/themesvc/retrieveTheme?queryName={theme}"
        headers = _get_onemap_auth_headers()
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 401:
                fresh_token = get_onemap_access_token(force_refresh=True)
                if fresh_token:
                    token_value = fresh_token if str(fresh_token).lower().startswith("bearer ") else f"Bearer {fresh_token}"
                    headers = {"Authorization": token_value}
                    resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            logger.debug(f"[OneMap] {theme} API returned {len(data.get('SrchResults', []))} results")
            for idx, item in enumerate(data.get("SrchResults", [])):
                coords = item.get("LatLng")
                logger.debug(f"[OneMap] {theme} result {idx}: NAME={item.get('NAME')}, LatLng={coords}")
                try:
                    lat_ = None
                    lon_ = None

                    if coords:
                        parts = str(coords).split(",")
                        if len(parts) == 2:
                            lat_ = float(parts[0].strip())
                            lon_ = float(parts[1].strip())

                    if lat_ is None or lon_ is None:
                        raw_lat = item.get("LATITUDE") or item.get("Latitude") or item.get("lat") or item.get("Lat") or item.get("Y")
                        raw_lon = item.get("LONGITUDE") or item.get("Longitude") or item.get("lon") or item.get("Lon") or item.get("lng") or item.get("X")
                        if raw_lat is not None and raw_lon is not None:
                            lat_ = float(raw_lat)
                            lon_ = float(raw_lon)

                    if lat_ is None or lon_ is None:
                        continue

                    logger.debug(f"[OneMap] Parsed coords: lat={lat_}, lon={lon_}")
                    dist = _haversine_km(lat, lon, lat_, lon_)
                    logger.debug(f"[OneMap] Distance to ({lat_}, {lon_}): {dist}")
                    if dist is not None and dist <= radius_km:
                        logger.debug(f"[OneMap] {theme} result {idx} within {radius_km}km: {item.get('NAME')}")
                        name = item.get("NAME") or item.get("Theme_Name") or item.get("DESCRIPTION") or ""
                        block = (item.get("ADDRESSBLOCKHOUSENUMBER") or "").strip()
                        street = (item.get("ADDRESSSTREETNAME") or "").strip()
                        building = (item.get("ADDRESSBUILDINGNAME") or "").strip()
                        postal = (item.get("ADDRESSPOSTALCODE") or "").strip()
                        generic_address = (item.get("ADDRESS") or item.get("Address") or "").strip()

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
    logger.debug(f"[OneMap] Total theme amenities within {radius_km}km: {len(results)}")
    results = sorted(results, key=lambda x: x["distance_km"])
    for result in results:
        result.pop("distance_km", None)
        result.pop("type", None)
    return results[:limit]


# ── Module-level cache for MRT station data (fetched once per app lifetime) ──
_MRT_STATION_CACHE = {"data": None, "lock": threading.Lock()}


def _fetch_onemap_transport(lat, lon, radius_km=3, limit=3):
    """Fetch nearby MRT/LRT stations via OneMap search API with aggressive caching."""
    logger = logging.getLogger("amenity_debug")

    # Populate cache on first call
    with _MRT_STATION_CACHE["lock"]:
        if _MRT_STATION_CACHE["data"] is None:
            logger.debug("[OneMap] Building MRT station cache from search API...")
            all_stations = _build_mrt_station_cache()
            _MRT_STATION_CACHE["data"] = all_stations
            logger.debug(f"[OneMap] Cached {len(all_stations)} unique MRT/LRT stations")

    stations = _MRT_STATION_CACHE["data"] or []
    results = []
    for stn in stations:
        dist = _haversine_km(lat, lon, stn["lat"], stn["lon"])
        if dist is not None and dist <= radius_km:
            results.append({
                "lat": stn["lat"],
                "lon": stn["lon"],
                "name": stn["name"],
                "address": stn.get("address"),
                "distance_km": dist,
            })

    results = sorted(results, key=lambda x: x["distance_km"])
    for r in results:
        r.pop("distance_km", None)
    return results[:limit]


def _build_mrt_station_cache():
    """Fetch all MRT/LRT station entries from OneMap search, deduplicate by station name."""
    headers = _get_onemap_auth_headers()
    if not headers:
        print("[OneMap] No auth headers for MRT search, returning empty")
        return []
    url = f"{ONEMAP_BASE_URL}/api/common/elastic/search"
    seen_names = {}
    page = 1
    max_pages = 25  # ~250 results covers all unique stations

    while page <= max_pages:
        params = {
            "searchVal": "MRT STATION",
            "returnGeom": "Y",
            "getAddrDetails": "Y",
            "pageNum": page,
        }
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code != 200:
                print(f"[OneMap] MRT search page {page}: HTTP {resp.status_code}, stopping")
                break
            data = resp.json()
            results = data.get("results", [])
            if not results:
                break
            for item in results:
                sv = (item.get("SEARCHVAL") or "").strip()
                if not sv:
                    continue
                # Extract base station name (remove exit codes like "EXIT A")
                upper = sv.upper()
                if "MRT" not in upper and "LRT" not in upper:
                    continue
                # Deduplicate: keep first occurrence per base station name
                # e.g. "CALDECOTT MRT STATION (TE9)" and "CALDECOTT MRT STATION EXIT A"
                # -> keep as "CALDECOTT MRT STATION"
                base = upper
                for sep in [" EXIT ", " - EXIT"]:
                    idx = base.find(sep)
                    if idx > 0:
                        base = base[:idx].strip()
                # Remove line codes in parens: "(TE9)" -> ""
                base = re.sub(r'\s*\([A-Z]{1,3}\d{1,3}\)\s*$', '', base).strip()
                if base in seen_names:
                    continue
                try:
                    lat_ = float(item.get("LATITUDE", 0))
                    lon_ = float(item.get("LONGITUDE", 0))
                except (ValueError, TypeError):
                    continue
                if lat_ == 0 or lon_ == 0:
                    continue
                addr = (item.get("ADDRESS") or item.get("BLK_NO", "") + " " + item.get("ROAD_NAME", "")).strip()
                seen_names[base] = {
                    "name": sv,
                    "lat": lat_,
                    "lon": lon_,
                    "address": addr if addr else None,
                }
            total_pages = data.get("totalNumPages", 1)
            if page >= total_pages:
                break
            page += 1
            time.sleep(0.15)  # rate-limit
        except Exception as e:
            print(f"[OneMap] Error fetching MRT page {page}: {e}")
            break

    print(f"[OneMap] MRT cache complete: {len(seen_names)} unique stations from {page} pages")
    return list(seen_names.values())


def _get_nearby_fallback_amenities(amenity_type, lat, lon, radius_km, limit):
    fallback_key = "mrt" if amenity_type == "transport" else amenity_type
    fallback_data = FALLBACK_AMENITIES.get(fallback_key, [])
    results = []

    for amenity in fallback_data:
        dist = _haversine_km(lat, lon, amenity["lat"], amenity["lon"])
        if dist is None:
            continue
        if dist <= radius_km:
            amenity_copy = amenity.copy()
            results.append(amenity_copy)

    return results[:limit]
