"""
HDB Downsizing Helper — Prediction API
Run:  uvicorn backend.main:app --reload
"""

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

# ── OneMap ────────────────────────────────────────────────────────────────────

ONEMAP_SEARCH_URL = "https://www.onemap.gov.sg/api/common/elastic/search"

# ── Block+street → town lookup ────────────────────────────────────────────────

LOOKUP_PATH = os.environ.get("BLOCK_STREET_LOOKUP", "models/block_street_to_town.json")
_BLOCK_STREET_LOOKUP: dict[str, str] = {}

def _load_lookup():
    global _BLOCK_STREET_LOOKUP
    try:
        with open(LOOKUP_PATH) as f:
            _BLOCK_STREET_LOOKUP = json.load(f)
        print(f"Loaded {len(_BLOCK_STREET_LOOKUP)} block+street→town entries.")
    except FileNotFoundError:
        print(f"WARNING: {LOOKUP_PATH} not found. Town lookup will be limited.")

# ── Street name normaliser ────────────────────────────────────────────────────

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


def _town_from_block_street(block: str, road: str) -> str | None:
    block = block.strip().upper()
    road_norm = _normalise_street(road)
    key = f"{block}|{road_norm}"
    town = _BLOCK_STREET_LOOKUP.get(key)
    if town:
        return town
    key_raw = f"{block}|{road.strip().upper()}"
    return _BLOCK_STREET_LOOKUP.get(key_raw)


# ── Town name matching (fallback) ─────────────────────────────────────────────

HDB_TOWNS = sorted([
    "ANG MO KIO", "BEDOK", "BISHAN", "BUKIT BATOK", "BUKIT MERAH",
    "BUKIT TIMAH", "BUKIT PANJANG", "CENTRAL AREA", "CHOA CHU KANG",
    "CLEMENTI", "GEYLANG", "HOUGANG", "JURONG EAST", "JURONG WEST",
    "KALLANG/WHAMPOA", "MARINE PARADE", "PASIR RIS", "PUNGGOL",
    "QUEENSTOWN", "SEMBAWANG", "SENGKANG", "SERANGOON", "TAMPINES",
    "TOA PAYOH", "WOODLANDS", "YISHUN",
], key=len, reverse=True)


def _town_from_address_string(address: str) -> str | None:
    upper = address.upper().replace("SINGAPORE", "").strip()

    # Known estate aliases not in HDB town names
    aliases = {
    "BIDADARI":   "TOA PAYOH",
    "DAWSON":     "QUEENSTOWN",
    "TREELODGE":  "PUNGGOL",
    "DOVER":      "QUEENSTOWN",
    "DUXTON":     "BUKIT MERAH",
    "PINNACLE":   "BUKIT MERAH",
    "SKYVILLE":   "DAWSON",  # actually Queenstown
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


# ── SAI calculation (mirrors notebook's calculate_sai_for_row exactly) ───────

def _calculate_sai(row: dict, weights: dict, max_counts: dict, half_life: float = 500) -> float:
    """
    Mirrors calculate_sai_for_row() from the notebook exactly.
    Categories: clinic, hawker, park, mrt
    Scoring: 50% exponential decay distance + 50% linear density
    """
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


# ── PropertyGuru dataset ──────────────────────────────────────────────────────

PG_DATA_PATH = os.environ.get("PG_DATA_PATH", "data/raw/propertyguru_final.csv")
_pg_df: pd.DataFrame | None = None
_pg_max_counts: dict = {}


def _load_pg_data():
    global _pg_df, _pg_max_counts
    try:
        _pg_df = pd.read_csv(PG_DATA_PATH)

        def parse_area_sqm(area_str):
            try:
                digits = re.sub(r"[^\d.]", "", str(area_str).replace(",", ""))
                val = float(digits) * 0.092903  # always sqft
                return val
            except:
                return None

        def infer_room_count(sqm):
            if sqm is None:
                return 3
            if sqm < 40:
                return 2
            elif sqm < 78:
                return 3
            elif sqm < 105:
                return 4
            elif sqm < 125:
                return 5
            else:
                return 6

        # Floor area inference (fallback)
        _pg_df["floor_area_sqm"] = _pg_df["area_detail"].apply(parse_area_sqm)
        _pg_df["room_count"] = _pg_df["floor_area_sqm"].apply(infer_room_count)
        # Override: 1 bedroom = 2-room HDB flat
        _pg_df.loc[_pg_df["bedrooms_detail"] == 1, "room_count"] = 2

        # HDB lookup override (more accurate where available)
        try:
            hdb_raw = pd.read_csv("data/raw/HDB_full_resale_info.csv.gz")
            flat_type_map = {}
            for _, row in hdb_raw[["block", "street_name", "flat_type"]].drop_duplicates().iterrows():
                key = f"{str(row['block']).strip().upper()} {str(row['street_name']).strip().upper()}"
                flat_type_map[key] = row["flat_type"]

            flat_type_to_rooms = {
                "2 ROOM": 2, "3 ROOM": 3, "4 ROOM": 4,
                "5 ROOM": 5, "EXECUTIVE": 6, "MULTI-GENERATION": 6,
            }

            def lookup_room_count(address):
                try:
                    key = address.strip().upper()
                    flat_type = flat_type_map.get(key)
                    if flat_type:
                        return flat_type_to_rooms.get(flat_type)
                except:
                    pass
                return None

            hdb_rooms = _pg_df["address_from_url"].apply(lookup_room_count)
            matched = hdb_rooms.notna().sum()
            print(f"HDB lookup matched {matched}/{len(_pg_df)} listings.")
            # Override floor area inference where HDB lookup succeeded
            _pg_df["room_count"] = hdb_rooms.combine_first(_pg_df["room_count"])
        except Exception as e:
            import traceback
            print(f"HDB lookup failed: {e}")
            traceback.print_exc()

        # Map nearest MRT station to HDB town
        station_to_town = {
            'ADMIRALTY MRT STATION': 'Woodlands', 'ALJUNIED MRT STATION': 'Geylang',
            'ANG MO KIO MRT STATION': 'Ang Mo Kio', 'BAKAU LRT STATION': 'Sengkang',
            'BANGKIT LRT STATION': 'Bukit Panjang', 'BARTLEY MRT STATION': 'Serangoon',
            'BAYSHORE MRT STATION': 'Bedok', 'BEAUTY WORLD MRT STATION': 'Bukit Timah',
            'BEDOK MRT STATION': 'Bedok', 'BEDOK NORTH MRT STATION': 'Bedok',
            'BEDOK RESERVOIR MRT STATION': 'Bedok', 'BENCOOLEN MRT STATION': 'Central Area',
            'BENDEMEER MRT STATION': 'Kallang/Whampoa', 'BISHAN MRT STATION': 'Bishan',
            'BOON KENG MRT STATION': 'Kallang/Whampoa', 'BOON LAY MRT STATION': 'Jurong West',
            'BRADDELL MRT STATION': 'Toa Payoh', 'BRIGHT HILL MRT STATION': 'Bishan',
            'BUANGKOK MRT STATION': 'Sengkang', 'BUGIS MRT STATION': 'Central Area',
            'BUKIT BATOK MRT STATION': 'Bukit Batok', 'BUKIT GOMBAK MRT STATION': 'Bukit Batok',
            'BUKIT PANJANG LRT STATION': 'Bukit Panjang', 'BUKIT PANJANG MRT STATION': 'Bukit Panjang',
            'BUONA VISTA MRT STATION': 'Queenstown', 'CALDECOTT MRT STATION': 'Toa Payoh',
            'CANBERRA MRT STATION': 'Sembawang', 'CC9': 'Central Area',
            'CHANGI AIRPORT MRT STATION': 'Tampines', 'CHENG LIM LRT STATION': 'Sengkang',
            'CHINATOWN MRT STATION': 'Central Area', 'CHINESE GARDEN MRT STATION': 'Jurong East',
            'CHOA CHU KANG MRT STATION': 'Choa Chu Kang', 'CLEMENTI MRT STATION': 'Clementi',
            'COMMONWEALTH MRT STATION': 'Queenstown', 'COMPASSVALE LRT STATION': 'Sengkang',
            'CORAL EDGE LRT STATION': 'Punggol', 'COVE LRT STATION': 'Punggol',
            'DAKOTA MRT STATION': 'Geylang', 'DAMAI LRT STATION': 'Punggol',
            'DOVER MRT STATION': 'Queenstown', 'DT4': 'Central Area',
            'EUNOS MRT STATION': 'Geylang', 'FAJAR LRT STATION': 'Bukit Panjang',
            'FARRER PARK MRT STATION': 'Kallang/Whampoa', 'FARRER ROAD MRT STATION': 'Bukit Timah',
            'FARMWAY LRT STATION': 'Sengkang', 'FERNVALE LRT STATION': 'Sengkang',
            'GEYLANG BAHRU MRT STATION': 'Kallang/Whampoa', 'GREAT WORLD MRT STATION': 'Central Area',
            'HARBOURFRONT MRT STATION': 'Bukit Merah', 'HAVELOCK MRT STATION': 'Bukit Merah',
            'HOLLAND VILLAGE MRT STATION': 'Queenstown', 'HOUGANG MRT STATION': 'Hougang',
            'JALAN BESAR MRT STATION': 'Central Area', 'JELAPANG LRT STATION': 'Bukit Panjang',
            'JURONG EAST MRT STATION': 'Jurong East', 'KADALOOR LRT STATION': 'Punggol',
            'KAKI BUKIT MRT STATION': 'Bedok', 'KALLANG MRT STATION': 'Kallang/Whampoa',
            'KANGKAR LRT STATION': 'Sengkang', 'KATONG PARK MRT STATION': 'Marine Parade',
            'KEAT HONG LRT STATION': 'Choa Chu Kang', 'KEMBANGAN MRT STATION': 'Bedok',
            'KHATIB MRT STATION': 'Yishun', 'KOVAN MRT STATION': 'Hougang',
            'KUPANG LRT STATION': 'Sengkang', 'LABRADOR PARK MRT STATION': 'Bukit Merah',
            'LAKESIDE MRT STATION': 'Jurong West', 'LAVENDER MRT STATION': 'Kallang/Whampoa',
            'LAYAR LRT STATION': 'Sengkang', 'LENTOR MRT STATION': 'Ang Mo Kio',
            'LITTLE INDIA MRT STATION': 'Central Area', 'LORONG CHUAN MRT STATION': 'Serangoon',
            'MACPHERSON MRT STATION': 'Geylang', 'MARINE PARADE MRT STATION': 'Marine Parade',
            'MARINE TERRACE MRT STATION': 'Marine Parade', 'MARSILING MRT STATION': 'Woodlands',
            'MARYMOUNT MRT STATION': 'Bishan', 'MATTAR MRT STATION': 'Geylang',
            'MAXWELL MRT STATION': 'Central Area', 'MAYFLOWER MRT STATION': 'Ang Mo Kio',
            'MERIDIAN LRT STATION': 'Punggol', 'MOUNTBATTEN MRT STATION': 'Geylang',
            'NIBONG LRT STATION': 'Punggol', 'NICOLL HIGHWAY MRT STATION': 'Central Area',
            'NOVENA MRT STATION': 'Kallang/Whampoa', 'OASIS LRT STATION': 'Punggol',
            'ONE-NORTH MRT STATION': 'Queenstown', 'OUTRAM PARK MRT STATION': 'Central Area',
            'PASIR RIS MRT STATION': 'Pasir Ris', 'PAYA LEBAR MRT STATION': 'Geylang',
            'PENDING LRT STATION': 'Bukit Panjang', 'PETIR LRT STATION': 'Bukit Panjang',
            'PHOENIX LRT STATION': 'Bukit Panjang', 'PIONEER MRT STATION': 'Jurong West',
            'POTONG PASIR MRT STATION': 'Toa Payoh', 'PUNGGOL LRT STATION': 'Punggol',
            'PUNGGOL MRT STATION': 'Punggol', 'PUNGGOL POINT LRT STATION': 'Punggol',
            'QUEENSTOWN MRT STATION': 'Queenstown', 'RANGGUNG LRT STATION': 'Sengkang',
            'REDHILL MRT STATION': 'Bukit Merah', 'RENJONG LRT STATION': 'Sengkang',
            'RIVIERA LRT STATION': 'Punggol', 'ROCHOR MRT STATION': 'Central Area',
            'RUMBIA LRT STATION': 'Sengkang', 'SAMUDERA LRT STATION': 'Punggol',
            'SEGAR LRT STATION': 'Bukit Panjang', 'SEMBAWANG MRT STATION': 'Sembawang',
            'SENGKANG MRT STATION': 'Sengkang', 'SENJA LRT STATION': 'Bukit Panjang',
            'SERANGOON MRT STATION': 'Serangoon', 'SIMEI MRT STATION': 'Tampines',
            'SOO TECK LRT STATION': 'Punggol', 'SOUTH VIEW LRT STATION': 'Choa Chu Kang',
            'SUMANG LRT STATION': 'Punggol', 'TAI SENG MRT STATION': 'Geylang',
            'TAMPINES EAST MRT STATION': 'Tampines', 'TAMPINES MRT STATION': 'Tampines',
            'TAMPINES WEST MRT STATION': 'Tampines', 'TANAH MERAH MRT STATION': 'Bedok',
            'TANJONG PAGAR MRT STATION': 'Central Area', 'TECK WHYE LRT STATION': 'Choa Chu Kang',
            'TELOK BLANGAH MRT STATION': 'Bukit Merah', 'THANGGAM LRT STATION': 'Sengkang',
            'TIONG BAHRU MRT STATION': 'Bukit Merah', 'TOA PAYOH MRT STATION': 'Toa Payoh',
            'TONGKANG LRT STATION': 'Sengkang', 'UBI MRT STATION': 'Geylang',
            'UPPER CHANGI MRT STATION': 'Tampines', 'UPPER THOMSON MRT STATION': 'Bishan',
            'WOODLANDS MRT STATION': 'Woodlands', 'WOODLANDS NORTH MRT STATION': 'Woodlands',
            'WOODLANDS SOUTH MRT STATION': 'Woodlands', 'WOODLEIGH MRT STATION': 'Toa Payoh',
            'YEW TEE MRT STATION': 'Choa Chu Kang', 'YIO CHU KANG MRT STATION': 'Ang Mo Kio',
            'YISHUN MRT STATION': 'Yishun',
        }
        _pg_df["hdb_town"] = _pg_df["nearest_mrt_name"].map(station_to_town)
        _pg_df = _pg_df.dropna(subset=["hdb_town"])
        print(f"After town mapping: {len(_pg_df)} listings with valid towns.")

        _pg_df = _pg_df.drop_duplicates(subset=["listing_url"])
        print(f"After deduplication: {len(_pg_df)} listings.")

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

        # Fixed max counts from dataset (as per notebook)
        # Dynamic max counts from dataset
        _pg_max_counts = {
            "clinic": int(_pg_df["num_clinic_within_1000m"].max()),
            "hawker": int(_pg_df["num_hawker_within_1000m"].max()),
            "park":   int(_pg_df["num_park_within_1000m"].max()),
            "mrt":    int(_pg_df["num_mrt_within_1000m"].max()),
        }
        print(f"Max counts: {_pg_max_counts}")

        print(f"Loaded PropertyGuru dataset: {len(_pg_df)} listings.")
        print(f"Max counts: {_pg_max_counts}")
    except FileNotFoundError:
        print(f"WARNING: {PG_DATA_PATH} not found. /recommend will not work.")


# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="HDB Resale Price Predictor",
    description="RPI-normalized XGBoost model for Singapore HDB resale prices.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Load everything at startup ────────────────────────────────────────────────

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


# ── Schemas ───────────────────────────────────────────────────────────────────

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


# ── Endpoints ─────────────────────────────────────────────────────────────────

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
            sold_year=body.sold_year,
            sold_month=body.sold_month,
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


@app.get("/predict", response_model=PredictResponse, tags=["Prediction"])
def predict_get(
    town:            Annotated[str,   Query(examples=["BEDOK"])],
    flat_type:       Annotated[str,   Query(examples=["3 ROOM"])],
    floor_area_sqm:  Annotated[float, Query(gt=0)],
    sold_year:       Annotated[int,   Query(ge=2011, le=2030)],
    sold_month:      Annotated[int,   Query(ge=1, le=12)],
    listing_premium: Annotated[float, Query(gt=1.0)] = 1.05,
):
    predictor = get_predictor()
    try:
        result = predictor.predict(
            town=town.upper().strip(),
            flat_type=flat_type.upper().strip(),
            floor_area_sqm=floor_area_sqm,
            sold_year=sold_year,
            sold_month=sold_month,
            listing_premium=listing_premium,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return PredictResponse(
        town=town, flat_type=flat_type,
        floor_area_sqm=floor_area_sqm,
        sold_year=sold_year, sold_month=sold_month,
        **result,
    )


@app.post("/predict/sell", response_model=SellResponse, tags=["Prediction"])
def predict_sell(body: SellRequest):
    predictor = get_predictor()

    town = _town_from_postal(body.postal.strip())
    print(f"DEBUG: postal={body.postal}, resolved_town={town}, "
          f"flat_type={body.flat_type}, area={body.floor_area_sqm}")

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

    now = datetime.now()
    try:
        result = predictor.predict(
            town=town,
            flat_type=body.flat_type.upper().strip(),
            floor_area_sqm=floor_area,
            sold_year=now.year,
            sold_month=now.month,
            listing_premium=1.10,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    price = int(result["asking_price"])
    return SellResponse(
        price=price,
        low=int(price * 0.93),
        high=int(price * 1.07),
        median_town=int(price * 0.98),
        town=town,
    )


@app.post("/recommend", response_model=List[RecommendedListing], tags=["Recommendation"])
def recommend(body: RecommendRequest):
    """
    Filter PropertyGuru listings by constraints, score by SAI, return top 3.


    """

    print(f"\n{'='*60}")
    print(f"DEBUG /recommend")
    print(f"  Constraints: budget={body.constraints.max_budget}, max_rooms={body.constraints.max_rooms}, towns={body.constraints.preferred_towns}")
    print(f"  Weights: clinic={body.weights.clinic}, hawker={body.weights.hawker}, park={body.weights.park}, mrt={body.weights.mrt}")
    print(f"{'='*60}")

    if _pg_df is None:
        raise HTTPException(status_code=503, detail="PropertyGuru dataset not loaded.")

    df = _pg_df.copy()

    # ── Drop rows missing required fields ─────────────────────────────────────
    df = df.dropna(subset=["buy_price", "postal", "latitude", "longitude",
                            "nearest_mrt_distance_m", "nearest_clinic_distance_m",
                            "nearest_park_distance_m", "nearest_hawker_distance_m"])

    # ── Filter: budget ────────────────────────────────────────────────────────
    df = df[df["buy_price"] <= body.constraints.max_budget]

    # ── Filter: min rooms ─────────────────────────────────────────────────────
    df = df[df["room_count"] == body.constraints.max_rooms]

    # ── Filter: preferred towns (case-insensitive partial match) ──────────────
    if body.constraints.preferred_towns:
        pattern = "|".join(
            re.escape(t.strip()) for t in body.constraints.preferred_towns
        )
        df = df[df["hdb_town"].str.contains(pattern, case=False, na=False)]

    if df.empty:
        raise HTTPException(
            status_code=404,
            detail="No listings found matching your constraints. Try increasing budget or relaxing filters.",
        )
    # Keep cheapest listing per block
    df = df.sort_values("buy_price").drop_duplicates(subset=["onemap_full_address"], keep="first")
    # ── Calculate SAI for each listing (mirrors notebook exactly) ──────────────
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

    # ── Top 3 by SAI ──────────────────────────────────────────────────────────
    top3 = df.sort_values(by=["sai_score", "buy_price"], ascending=[False, True]).head(3)

    results = []
    for _, row in top3.iterrows():
        results.append(RecommendedListing(
            town=str(row["hdb_town"]),
            rooms=int(row["room_count"]),
            postal=str(row["postal"]),
            buy_price=int(row["buy_price"]),
            listing_url=str(row["listing_url"]),
            address_from_url=str(row["onemap_full_address"]),
        ))
    print(f"\nDEBUG SAI Scores (top 3):")
    for _, row in top3.iterrows():
        print(f"  {row['address_from_url']} | town={row['hdb_town']} | rooms={int(row['room_count'])} | price=${int(row['buy_price']):,} | SAI={row['sai_score']}")
        print(f"    distances: clinic={row.get('nearest_clinic_distance_m','N/A'):.0f}m, hawker={row.get('nearest_hawker_distance_m','N/A'):.0f}m, park={row.get('nearest_park_distance_m','N/A'):.0f}m, mrt={row.get('nearest_mrt_distance_m','N/A'):.0f}m")
        print(f"    counts: clinic={row.get('num_clinic_within_1000m','N/A')}, hawker={row.get('num_hawker_within_1000m','N/A')}, park={row.get('num_park_within_1000m','N/A')}, mrt={row.get('num_mrt_within_1000m','N/A')}")
    print(f"{'='*60}\n")

    return results