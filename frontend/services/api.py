import logging
import requests
import time
import json as json_module
import csv
import io
import math

from config.settings import (
    BACKEND_URL,
    TIMEOUT_SEC,
    ONEMAP_SEARCH_URL,
    ONEMAP_REVERSE_GEOCODE_URL,
    ONEMAP_TOKEN,
    DATA_GOV_API_KEY,
    TRANSPORT_DATASET_ID,
    AMENITY_CACHE_TTL,
    AMENITY_CACHE_VERSION,
    API_REQUEST_DELAY_SEC,
    FALLBACK_AMENITIES,
)

AMENITY_CACHE = {}
REVERSE_GEOCODE_CACHE = {}
LAST_API_REQUEST_TIME = None


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c


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

    api_configs = {
        "hawker": {"format": "poll_download", "dataset_id": "d_4a086da0a5553be1d89383cd90d07ecd"},
        "parks": {"format": "poll_download", "dataset_id": "d_0542d48f0991541706b58059381a6eca"},
        "mrt": {"format": "metadata", "collection_id": 367},
        "transport": {"format": "poll_download", "dataset_id": TRANSPORT_DATASET_ID},
    }

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

    if amenity_type in ("hawker", "parks", "transport"):
        try:
            records = _fetch_amenity_records(config, amenity_type)
            results = _filter_amenities_by_distance(records, lat, lon, radius_km, limit, amenity_type=amenity_type)
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
        print(f"Using fallback mock data for {amenity_type}")
        mock_results = _get_nearby_fallback_amenities(amenity_type, lat, lon, radius_km, limit)
        AMENITY_CACHE[cache_key] = {
            "data": mock_results,
            "timestamp": time.time()
        }
        return mock_results


def _fetch_onemap_healthcare(lat, lon, radius_km=3, limit=3):
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
                        parts = str(coords).split(",")
                        if len(parts) == 2:
                            lat_ = float(parts[0].strip())
                            lon_ = float(parts[1].strip())
                            logger.debug(f"[OneMap] Parsed coords: lat={lat_}, lon={lon_}")
                            dist = _haversine_km(lat, lon, lat_, lon_)
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
    results = sorted(results, key=lambda x: x["distance_km"])
    for result in results:
        result.pop("distance_km", None)
        result.pop("type", None)
    return results[:limit]


def _get_nearby_fallback_amenities(amenity_type, lat, lon, radius_km, limit):
    fallback_key = "mrt" if amenity_type == "transport" else amenity_type
    fallback_data = FALLBACK_AMENITIES.get(fallback_key, [])
    results = []

    for amenity in fallback_data:
        dist = _haversine_km(lat, lon, amenity["lat"], amenity["lon"])
        if dist is not None and dist <= radius_km:
            amenity_copy = amenity.copy()
            results.append(amenity_copy)

    return results[:limit]


def _fetch_amenity_records(config, amenity_type, max_retries=3):
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
                    geojson = json_module.loads(response.text)
                    if isinstance(geojson, dict) and "features" in geojson:
                        return geojson
                    if isinstance(geojson, dict):
                        return geojson.get("records", [])
                    return geojson
                except Exception:
                    csv_data = csv.DictReader(io.StringIO(response.text))
                    return list(csv_data)

            return []

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"Rate limited for {amenity_type}, attempt {attempt+1}/{max_retries}. Waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    raise
            else:
                raise
        except Exception:
            raise

    return []


def _filter_amenities_by_distance(records, lat, lon, radius_km, limit, amenity_type=None):
    results = []
    logger = logging.getLogger("amenity_debug")

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
                    logger.debug(f"[AmenityDebug] Feature {i}: Calling _haversine_km(lat={lat}, lon={lon}, rec_lat={rec_lat}, rec_lon={rec_lon})")
                    logger.debug(f"[AmenityDebug] Types: lat={type(lat)}, lon={type(lon)}, rec_lat={type(rec_lat)}, rec_lon={type(rec_lon)}")
                    try:
                        dist = _haversine_km(lat, lon, rec_lat, rec_lon)
                        logger.debug(f"[AmenityDebug] Feature {i}: _haversine_km result: {dist}")
                    except Exception as e:
                        logger.debug(f"[AmenityDebug] Feature {i}: Exception in _haversine_km: {e}")
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
            dist = _haversine_km(lat, lon, rec_lat, rec_lon)
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
