"""
FastAPI for HomeCompass App: Backend Integration 
Run:  uvicorn backend.main:app --reload
"""

######################################################################
# main.py is the FastAPI Backend server which exposes two
# endpoints used by frontend /predict/sell and /recommend.
# This handles all request and response logic such as resolving
# postal codes to HDB towns, filtering and scoring propertyguru 
# listings by SAI, computing valuation and whether fair deal or not,
# and returns structured JSON to frontend to output
######################################################################

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Annotated, Optional, List
from datetime import datetime
import requests
import json
import os
import re
import math
import pandas as pd

from backend.model import HDBPredictor
from backend.hdb_predictor import predict_price_listing

# OneMap API endpoint for geocoding postal codes to block/street/address

ONEMAP_SEARCH_URL = "https://www.onemap.gov.sg/api/common/elastic/search"

#Block+street → town lookup
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOOKUP_PATH = os.environ.get("BLOCK_STREET_LOOKUP", os.path.join(_BASE_DIR, "models", "block_street_to_town.json"))
_BLOCK_STREET_LOOKUP: dict[str, str] = {}


# Loads block+street→town JSON lookup table built from HDB transaction data.
# Used as primary town resolution method before falling back to address string matching.
def _load_lookup():
    global _BLOCK_STREET_LOOKUP
    try:
        with open(LOOKUP_PATH) as f:
            _BLOCK_STREET_LOOKUP = json.load(f)
        print(f"Loaded {len(_BLOCK_STREET_LOOKUP)} block+street→town entries.")
    except FileNotFoundError:
        print(f"WARNING: {LOOKUP_PATH} not found. Town lookup will be limited.")

#Normalises street names to match lookup table keys (e.g. "AVENUE 6" → "AVE 6").

_ABBREV = [
    (r"\bAVENUE\b",    "AVE"),
    (r"\bSTREET\b",    "ST"),
    (r"\bDRIVE\b",     "DR"),
    (r"\bROAD\b",      "RD"),
    (r"\bCRESCENT\b",  "CRES"),
    (r"\bCLOSE\b",     "CL"),
    (r"\bTERRACE\b",   "TER"),
    (r"\bPLACE\b",     "PL"),
    (r"\bLINK\b",      "LK"),
    (r"\bLANE\b",      "LN"),
    (r"\bWALK\b",      "WK"),
    (r"\bNORTH\b",     "NTH"),
    (r"\bSOUTH\b",     "STH"),
    (r"\bEAST\b",      "EST"),
    (r"\bWEST\b",      "WST"),
    (r"\bCENTRAL\b",   "CTRL"),
    (r"\bUPPER\b",     "UPP"),
    (r"\bLOWER\b",     "LWR"),
    (r"\bNEW\b",       "NEW"),
    (r"\bBUKIT\b",     "BT"),
    (r"\bLORONG\b",    "LOR"),
    (r"\bJALAN\b",     "JLN"),
    (r"\bPARK\b",      "PK"),
]

def _normalise_street(name: str) -> str:
    name = name.upper().strip()
    for pattern, replacement in _ABBREV:
        name = re.sub(pattern, replacement, name)
    return name.strip()

# Looks up HDB town using block number + normalised street name as key.
def _town_from_block_street(block: str, road: str) -> str | None:
    block = block.strip().upper()
    road_norm = _normalise_street(road)
    key = f"{block}|{road_norm}"
    town = _BLOCK_STREET_LOOKUP.get(key)
    if town:
        return town
    key_raw = f"{block}|{road.strip().upper()}"
    return _BLOCK_STREET_LOOKUP.get(key_raw)


#Town name matching (fallback) 

HDB_TOWNS = sorted([
    "ANG MO KIO", "BEDOK", "BISHAN", "BUKIT BATOK", "BUKIT MERAH",
    "BUKIT TIMAH", "BUKIT PANJANG", "CENTRAL AREA", "CHOA CHU KANG",
    "CLEMENTI", "GEYLANG", "HOUGANG", "JURONG EAST", "JURONG WEST",
    "KALLANG/WHAMPOA", "MARINE PARADE", "PASIR RIS", "PUNGGOL",
    "QUEENSTOWN", "SEMBAWANG", "SENGKANG", "SERANGOON", "TAMPINES",
    "TOA PAYOH", "WOODLANDS", "YISHUN",
], key=len, reverse=True)

# Fallback town resolution using known estate aliases and HDB town name substring matching.

def _town_from_address_string(address: str) -> str | None:
    upper = address.upper().replace("SINGAPORE", "").strip()

    #Known estate aliases not in HDB town names
    aliases = {
    "BIDADARI":   "TOA PAYOH",
    "DAWSON":     "QUEENSTOWN",
    "TREELODGE":  "PUNGGOL",
    "DOVER":      "QUEENSTOWN",
    "DUXTON":     "BUKIT MERAH",
    "PINNACLE":   "BUKIT MERAH",
    "SKYVILLE":   "QUEENSTOWN",  #this one in queenstown?
    "WATERWAY":   "PUNGGOL",
    "NORTHSHORE": "PUNGGOL",
    "MATILDA":    "PUNGGOL",
    "CANBERRA":   "SEMBAWANG",
    "MARSILING":  "WOODLANDS",
    "RIVERVALE":  "SENGKANG",
    "FERNVALE":   "SENGKANG",
    "ANCHORVALE": "SENGKANG",
    "COMPASSVALE":"SENGKANG",
    "BUANGKOK":   "SENGKANG",
    "EDGEFIELD":  "PUNGGOL",
    "SUMANG":     "PUNGGOL",
    "SAMUDERA":   "PUNGGOL",
    "STRATHMORE": "QUEENSTOWN",
    "COMMONWEALTH":"QUEENSTOWN",
    "GHIM MOH":   "QUEENSTOWN",
    "STIRLING":   "QUEENSTOWN",
    "BENDEMEER":  "KALLANG/WHAMPOA",
    "WHAMPOA":    "KALLANG/WHAMPOA",
    "BOON KENG":  "KALLANG/WHAMPOA",
    "JELAPANG":   "BUKIT PANJANG",
    "FAJAR":      "BUKIT PANJANG",
    "SEGAR":      "BUKIT PANJANG",
    "ELIAS":      "PASIR RIS",
    "LOYANG":     "PASIR RIS",
    "YUNG":       "JURONG WEST",
    "TAMAN":      "JURONG WEST",
}
    for alias, town in aliases.items():
        if alias in upper:
            return town

    for town in HDB_TOWNS:
        if "/" in town:
            if any(p in upper for p in town.split("/")):
                return town
        elif town in upper:
            return town
    return None

# Primary entry point for town resolution. Calls OneMap API with postal code,
# tries block+street lookup first, falls back to address string matching.
def _town_from_postal(postal: str) -> str | None:
    try:
        r = requests.get(
            ONEMAP_SEARCH_URL,
            params={"searchVal": postal, "returnGeom": "N", "getAddrDetails": "Y", "pageNum": 1},
            timeout=5,
        )
        results = r.json().get("results") or []
        if not results:
            return None

        top     = results[0]
        address = top.get("ADDRESS", "")
        block   = top.get("BLK_NO", "")
        road    = top.get("ROAD_NAME", "")

        if block and road:
            town = _town_from_block_street(block, road)
            if town:
                return town

        return _town_from_address_string(address)

    except Exception:
        pass
    return None


# Computes SAI score (0-100) for a listing using exponential decay distance (50%)
# and linear density (50%), weighted by user slider preferences.

def _calculate_sai(row: dict, weights: dict, max_counts: dict, half_life: float = 500) -> float:

    decay_rate = math.log(2) / half_life

    distances = {
        "clinic": row.get("nearest_clinic_distance_m", 500),
        "hawker": row.get("nearest_hawker_distance_m", 500),
        "park":   row.get("nearest_park_distance_m", 500),
        "mrt":    row.get("nearest_mrt_distance_m", 500),
    }
    counts = {
        "clinic": row.get("num_clinic_within_1000m", 1),
        "hawker": row.get("num_hawker_within_1000m", 1),
        "park":   row.get("num_park_within_1000m", 1),
        "mrt":    row.get("num_mrt_within_1000m", 1),
    }

    weighted_sum  = 0.0
    total_weights = 0.0

    for category in ["clinic", "hawker", "park", "mrt"]:
        max_c  = max_counts.get(category, 1)
        dist   = distances[category] if distances[category] == distances[category] else 500  # NaN check
        count  = counts[category]    if counts[category]    == counts[category]    else 1
        weight = weights.get(category, 1)

        count_capped = min(count, max_c)
        dist_score   = 50 * math.exp(-decay_rate * dist)
        count_score  = 50 * (count_capped / max_c) if max_c > 0 else 0

        weighted_sum  += (dist_score + count_score) * weight
        total_weights += weight

    return round(weighted_sum / total_weights, 1) if total_weights > 0 else 0.0


# Loads and preprocesses PropertyGuru listings dataset at startup.
# Parses prices, zero-pads postal codes, deduplicates, and computes max amenity counts.

PG_DATA_PATH = os.environ.get("PG_DATA_PATH", os.path.join(_BASE_DIR, "data", "raw", "propertyguru_listings_final.csv"))
_pg_df: pd.DataFrame | None = None
_pg_max_counts: dict = {}

# Initialises lookup table, PropertyGuru dataset, and XGBoost predictor at startup.
def _load_pg_data():
    global _pg_df, _pg_max_counts
    try:
        _pg_df = pd.read_csv(PG_DATA_PATH)

        # Derive room_count from flat_type since new CSV dropped this column
        flat_type_to_rooms = {'2 ROOM': 2, '3 ROOM': 3, '4 ROOM': 4, '5 ROOM': 5, 'EXECUTIVE': 6}
        _pg_df['room_count'] = _pg_df['flat_type'].map(flat_type_to_rooms).fillna(4)

        # Parse price: "S$ 850,000" → 850000
        _pg_df["buy_price"] = (
            _pg_df["price_detail"]
            .str.replace(r"[^\d]", "", regex=True)
            .astype(float)
        )

        # Postal: zero-padded 6-digit string
        _pg_df["postal"] = (
            _pg_df["postal_code"]
            .astype("Int64")
            .astype(str)
            .str.replace("<NA>", "", regex=False)
            .str.zfill(6)
        )

        if "address_from_url" not in _pg_df.columns:
            _pg_df["address_from_url"] = _pg_df["onemap_full_address"]

        _pg_df = _pg_df.dropna(subset=["hdb_town"])
        print(f"After town mapping: {len(_pg_df)} listings with valid towns.")

        _pg_df = _pg_df.drop_duplicates(subset=["listing_url"])
        print(f"After deduplication: {len(_pg_df)} listings.")

        _pg_max_counts = {
            "clinic": int(_pg_df["num_clinic_within_1000m"].max()),
            "hawker": int(_pg_df["num_hawker_within_1000m"].max()),
            "park":   int(_pg_df["num_park_within_1000m"].max()),
            "mrt":    int(_pg_df["num_mrt_within_1000m"].max()),
        }
        print(f"Max counts: {_pg_max_counts}")
        print(f"Loaded PropertyGuru dataset: {len(_pg_df)} listings.")

    except FileNotFoundError:
        print(f"WARNING: {PG_DATA_PATH} not found. /recommend will not work.")


#App setup 

app = FastAPI(
    title="HomeCompassAPI",
    description="HomeCompassAPI",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

#Load everything at startup

_predictor: HDBPredictor | None = None


@app.on_event("startup")
def _startup():
    global _predictor
    _load_lookup()
    _load_pg_data()
    try:
        _predictor = HDBPredictor()
        print("Model loaded successfully.")
    except FileNotFoundError as e:
        print(f"WARNING: {e}")


def get_predictor() -> HDBPredictor:
    if _predictor is None:
        raise HTTPException(status_code=503, detail="Model not loaded.")
    return _predictor


#Schemas

class PredictRequest(BaseModel):
    town:            str   = Field(..., examples=["BEDOK"])
    flat_type:       str   = Field(..., examples=["3 ROOM"])
    floor_area_sqm:  float = Field(..., gt=0)
    sold_year:       int   = Field(..., ge=2011, le=2030)
    sold_month:      int   = Field(..., ge=1, le=12)
    listing_premium: float = Field(1.05, gt=1.0)


class PredictResponse(BaseModel):
    town:             str
    flat_type:        str
    floor_area_sqm:   float
    sold_year:        int
    sold_month:       int
    transacted_price: float
    asking_price:     float


class SellRequest(BaseModel):
    postal:         str             = Field(..., examples=["560123"])
    flat_type:      str             = Field(..., examples=["4 ROOM"])
    floor_area_sqm: Optional[float] = Field(None, gt=0)
    remaining_lease:  Optional[int]   = Field(None)


class SellResponse(BaseModel):
    price:       int
    low:         int
    high:        int
    median_town: int
    town:        str


class Constraints(BaseModel):
    max_budget:      int       = Field(..., gt=0)
    max_rooms:       int       = Field(..., ge=2)
    preferred_towns: List[str] = Field(default=[])


class Weights(BaseModel):
    clinic: float = Field(5.0, ge=1, le=10)
    hawker: float = Field(5.0, ge=1, le=10)
    park:   float = Field(5.0, ge=1, le=10)
    mrt:    float = Field(5.0, ge=1, le=10)


class RecommendRequest(BaseModel):
    constraints: Constraints
    weights:     Weights


class RecommendedListing(BaseModel):
    town:             str
    rooms:            int
    postal:           str
    buy_price:        int
    listing_url:      str
    address_from_url: str
    predicted_price:  int = 0
    valuation_label:  str = "N/A"


#Endpoints 
@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "message": "HDB Resale Predictor API is running."}


@app.get("/health", tags=["Health"])
def health():
    return {"model_loaded": _predictor is not None}


@app.post("/predict", response_model=PredictResponse, tags=["Prediction"])
def predict(body: PredictRequest):
    predictor = get_predictor()
    try:
        result = predictor.predict(
            town=body.town.upper().strip(),
            flat_type=body.flat_type.upper().strip(),
            floor_area_sqm=body.floor_area_sqm,
            remaining_lease=body.remaining_lease,
            listing_premium=body.listing_premium,   
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return PredictResponse(
        town=body.town, flat_type=body.flat_type,
        floor_area_sqm=body.floor_area_sqm,
        sold_year=body.sold_year, sold_month=body.sold_month,
        **result,
    )



#/predict/sell: fed to frontend
# Resolves postal code to HDB town, imputes missing floor area,
# and returns estimated selling price
@app.post("/predict/sell", response_model=SellResponse, tags=["Prediction"])
def predict_sell(body: SellRequest):
    predictor = get_predictor()

    town = _town_from_postal(body.postal.strip())

    if not town:
        raise HTTPException(
            status_code=422,
            detail=f"Could not resolve HDB town for postal code '{body.postal}'.",
        )

    floor_area = body.floor_area_sqm
    if not floor_area:
        defaults = {"2 ROOM": 45.0, "3 ROOM": 73.0, "4 ROOM": 93.0,
                    "5 ROOM": 110.0, "EXECUTIVE": 130.0}
        floor_area = defaults.get(body.flat_type.upper().strip(), 90.0)

    print(f"DEBUG: postal={body.postal}, resolved_town={town}, flat_type={body.flat_type.upper().strip()}, area={floor_area}, remaining_lease={body.remaining_lease}")

    
    try:
        result = predictor.predict(
        town=town,
        flat_type=body.flat_type.upper().strip(),
        floor_area_sqm=floor_area,
        remaining_lease=body.remaining_lease,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    price = int(result["asking_price"])
    return SellResponse(
        price=price,
        low=int(price * 0.93),  ##not shown to frontend
        high=int(price * 1.07), ##not shown to frontend
        median_town=result["median_town"], ##not shown to frontend
        town=town,
    )
##/recommend: fed to frontend
# Filters PropertyGuru listings by budget and flat type, scores by SAI,
# and returns top 3 with fair value labels using predict_price_listing().
@app.post("/recommend", response_model=List[RecommendedListing], tags=["Recommendation"])
def recommend(body: RecommendRequest):
    print(f"\n{'='*60}")
    print(f"DEBUG /recommend")
    print(f"  Constraints: budget={body.constraints.max_budget}, max_rooms={body.constraints.max_rooms}, towns={body.constraints.preferred_towns}")
    print(f"  Weights: clinic={body.weights.clinic}, hawker={body.weights.hawker}, park={body.weights.park}, mrt={body.weights.mrt}")
    print(f"{'='*60}")

    if _pg_df is None:
        raise HTTPException(status_code=503, detail="PropertyGuru dataset not loaded.")

    df = _pg_df.copy()
    
    df = df.dropna(subset=["buy_price", "postal",
                        "nearest_mrt_distance_m", "nearest_clinic_distance_m",
                        "nearest_park_distance_m", "nearest_hawker_distance_m"])

    df = df[df["buy_price"] <= body.constraints.max_budget]
    df = df[df["room_count"] == body.constraints.max_rooms]

    if body.constraints.preferred_towns:
        pattern = "|".join(re.escape(t.strip()) for t in body.constraints.preferred_towns)
        df = df[df["hdb_town"].str.contains(pattern, case=False, na=False)]

    if df.empty:
        raise HTTPException(
            status_code=404,
            detail="No listings found matching your constraints. Try increasing budget or relaxing filters.",
        )

    df = df.sort_values("buy_price").drop_duplicates(subset=["onemap_full_address"], keep="first")

    weights = {
        "clinic": body.weights.clinic,
        "hawker": body.weights.hawker,
        "park":   body.weights.park,
        "mrt":    body.weights.mrt,
    }

    df = df.copy()
    df["sai_score"] = df.apply(
        lambda row: _calculate_sai(row.to_dict(), weights, _pg_max_counts), axis=1
    )

    top3 = df.sort_values(by=["sai_score", "buy_price"], ascending=[False, True]).head(3)

    room_to_flat = {2: "2 ROOM", 3: "3 ROOM", 4: "4 ROOM", 5: "5 ROOM", 6: "EXECUTIVE"}

    results = []
    print(f"\nDEBUG SAI Scores (top 3):")
    for _, row in top3.iterrows():
        # Fair value calculation 
        flat_type = room_to_flat.get(int(row["room_count"]), "4 ROOM")
        try:
            row_dict = row.to_dict()
            row_dict['flat_type'] = flat_type
            row_dict['hdb_town'] = str(row['hdb_town']).upper()
            print(f"  [PRED INPUT] town={row_dict.get('hdb_town')} | flat_type={row_dict.get('flat_type')} | floor_area={row_dict.get('floor_area_sqm'):.1f}sqm | remaining_lease={row_dict.get('remaining_lease')} | storey_mid={row_dict.get('storey_mid')} | floor_category={row_dict.get('floor_category')} | region={row_dict.get('region')} | is_mature={row_dict.get('is_mature_estate')} | lease_commence={row_dict.get('lease_commence_date')} | sold_year={row_dict.get('sold_year')}")
            predicted_price = int(predict_price_listing(row_dict))
            actual = int(row["buy_price"])
            diff_pct = (actual - predicted_price) / predicted_price * 100
            if diff_pct > 10:  #for valuation, set at 10%
                valuation_label = "Above Market"
            elif diff_pct < -10:
                valuation_label = "Below Market"
            else:
                valuation_label = "Fair Value"
        except Exception as e:
            predicted_price = 0
            valuation_label = "N/A"
            print(f"  [WARN] Valuation failed for {row['hdb_town']}: {e}")

        print(f"  {row['onemap_full_address']} | town={row['hdb_town']} | rooms={int(row['room_count'])} | price=${int(row['buy_price']):,} | SAI={row['sai_score']} | predicted=${predicted_price:,} | valuation={valuation_label}")
        print(f"    distances: clinic={row.get('nearest_clinic_distance_m','N/A'):.0f}m, hawker={row.get('nearest_hawker_distance_m','N/A'):.0f}m, park={row.get('nearest_park_distance_m','N/A'):.0f}m, mrt={row.get('nearest_mrt_distance_m','N/A'):.0f}m")
        print(f"    counts: clinic={row.get('num_clinic_within_1000m','N/A')}, hawker={row.get('num_hawker_within_1000m','N/A')}, park={row.get('num_park_within_1000m','N/A')}, mrt={row.get('num_mrt_within_1000m','N/A')}")

        results.append(RecommendedListing(
            town=str(row["hdb_town"]),
            rooms=int(row["room_count"]),
            postal=str(row["postal"]),
            buy_price=int(row["buy_price"]),
            listing_url=str(row["listing_url"]),
            address_from_url=str(row["onemap_full_address"]),
            predicted_price=predicted_price,
            valuation_label=valuation_label,
        ))

    print(f"{'='*60}\n")
    return results