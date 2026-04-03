"""
HDB Downsizing Helper — Prediction API
Run:  uvicorn backend.main:app --reload
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Annotated, Optional
from datetime import datetime
import requests
import json
import os
import re

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
# OneMap returns full names e.g. "TOH YI DRIVE"
# Training data uses abbreviations e.g. "TOH YI DR"
# We normalise OneMap → training-data style before lookup.

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
    (r"\bPARK\b", "PK"),
]

def _normalise_street(name: str) -> str:
    name = name.upper().strip()
    for pattern, replacement in _ABBREV:
        name = re.sub(pattern, replacement, name)
    return name.strip()


def _town_from_block_street(block: str, road: str) -> str | None:
    """Look up town using block + normalised street name."""
    block = block.strip().upper()
    road_norm = _normalise_street(road)
    key = f"{block}|{road_norm}"
    town = _BLOCK_STREET_LOOKUP.get(key)
    if town:
        return town
    # Try without normalisation in case training data uses full name
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
    """Scan address string for a known HDB town name."""
    upper = address.upper().replace("SINGAPORE", "").strip()

    # Known estate aliases not in HDB town names
    aliases = {
        "BIDADARI": "TOA PAYOH",
        "DAWSON": "QUEENSTOWN",
        "TREELODGE": "PUNGGOL",
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
    """
    Resolve HDB town from postal code via OneMap.
    1. Block + street name lookup against training data (most accurate)
    2. Town name scan of address string (fast fallback)
    """
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

        # Primary: block + street lookup
        if block and road:
            town = _town_from_block_street(block, road)
            if town:
                return town

        # Fallback: town name in address string
        return _town_from_address_string(address)

    except Exception:
        pass
    return None


# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="HDB Resale Price Predictor",
    description="Hybrid Linear + XGBoost model for Singapore HDB resale prices.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Load model + lookup at startup ────────────────────────────────────────────

_predictor: HDBPredictor | None = None


@app.on_event("startup")
def _load_model():
    global _predictor
    _load_lookup()
    try:
        _predictor = HDBPredictor()
        print("Model loaded successfully.")
    except FileNotFoundError as e:
        print(f"WARNING: {e}")
        print("Run `python -m backend.model` to train and save the model first.")


def get_predictor() -> HDBPredictor:
    if _predictor is None:
        raise HTTPException(
            status_code=503,
            detail="Model not loaded. Run `python -m backend.model` first.",
        )
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
    price:       int = Field(..., description="Point estimate (SGD)")
    low:         int = Field(..., description="Lower bound ~93%")
    high:        int = Field(..., description="Upper bound ~107%")
    median_town: int = Field(..., description="Town median ~98%")
    town:        str = Field(..., description="Resolved HDB town")


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
    """
    Step 1 endpoint — called by the Dash frontend with postal code, flat type,
    and optional floor area. Returns price in the same shape as mock_predict_price().
    """
    predictor = get_predictor()

    town = _town_from_postal(body.postal.strip())
    print(f"DEBUG: postal={body.postal}, resolved_town={town}, "
          f"flat_type={body.flat_type}, area={body.floor_area_sqm}")

    if not town:
        raise HTTPException(
            status_code=422,
            detail=f"Could not resolve HDB town for postal code '{body.postal}'. "
                   "Check it is a valid 6-digit Singapore HDB postal code.",
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
