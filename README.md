# HomeCompass — HDB Downsizing Helper

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

**Course**: DSE3101 | **AY2025/2026** | **Group**: flatfinders

## Overview
HomeCompass is a senior-friendly web application designed to help elderly Singaporean HDB homeowners (aged 65 and above) make informed and confident housing downsizing decisions. The system integrates three core components into a guided five-step interface:

- Resale Price Estimator — predicts the current market value of the user's existing flat using an XGBoost model trained on ~250,000 historical HDB resale transactions from 2015 to 2026 
- Senior Accessibility Index (SAI) Scoring — ranks available listings by proximity to and density of senior-critical amenities (MRT stations, hawker centres, parks, clinics, and community clubs), weighted by the user's lifestyle preferences
- Lease Buyback Scheme (LBS) Calculator — estimates LBS proceeds to give users a complete financial picture of their downsizing options

You can access the deployed app **[HomeCompass here](https://homecompassapp.onrender.com/)**. Please open the **[Backend](https://homecompassbackend.onrender.com/)** link first and wait for it to load before launching the app as it is hosted on Render free tier and may take 1–2 minutes to wake up.

---

## System Workflow

```text
User Input (postal code, flat type, floor area, remaining lease, lifestyle preferences)
        │
        ▼
┌──────────────────────────────────────────────────────────────────┐
│                        BACKEND (FastAPI)                         │
│                                                                  │
│  1. Postal code → geocoordinates + town via OneMap API           │
│  2. XGBoost model → RPI-normalised resale price estimate         │
│  3. LBS proceeds calculation                                     │
│  4. PropertyGuru listing pool filtered by budget + flat type     │
│  5. SAI score computed per listing from amenity distances        │
│     and counts, weighted by user lifestyle preferences           │
│  6. Top 3 listings ranked by SAI score and returned              │
└──────────────────────────────────────────────────────────────────┘
        │
        ▼
Frontend (Dash) — 5-step guided interface
  Step 1: Enter current flat details (postal code, flat type, floor area, lease)
  Step 2: View selling price estimate + confidence interval
  Step 3: Set budget, flat type, and town preferences
  Step 4: View LBS estimate; set lifestyle and amenity priority weights
  Step 5: View top 3 listing recommendations with SAI scores,
          valuation labels, interactive map, and direct PropertyGuru links
```

---

## Tech Stack

- **Frontend**: Python Dash, Dash Bootstrap Components, Leaflet.js (via iframe)
- **Backend**: FastAPI, Uvicorn, Pydantic
- **ML**: XGBoost, scikit-learn, pandas, NumPy, joblib
- **External APIs**: OneMap API (SLA) — geocoding, amenity distances, town resolution

---

##  Repository Structure

```text
DSE3101-Project/
├── backend/
│   ├── main.py                               # FastAPI app entry point; defines all API endpoints
│   ├── model.py                              # Model loading, inference logic, listing price premiums
│   ├── hdb_predictor.py                      # Core prediction functions (predict_price_user,
│   │                                         # predict_price_listing)
│   ├── 01_data_collection.ipynb              # Raw data ingestion and geospatial feature computation
│   ├── 02_data_exploration.ipynb             # EDA, distribution analysis, correlation heatmaps
│   ├── 03_final_models.ipynb                 # Final model training pipeline and evaluation
│   ├── xgboost_training.ipynb                # Initial XGBoost hyperparameter tuning and cross-validation
│   ├── SAI_implementation.ipynb              # SAI score derivation and validation on PropertyGuru data
│   ├── propertyguru_listings_scraping.ipynb  # PropertyGuru scraping pipeline
│   └── propertyguru_listings_prep.ipynb      # Listing data cleaning and amenity enrichment
├── frontend/
│   ├── app.py                                # Dash app entry point; five-step UI layout and callbacks
│   ├── config/
│   │   ├── constants.py                      # App-wide constants (town lists, flat types, LBS parameters)
│   │   ├── settings.py                       # Environment and API configuration
│   │   └── style.py                          # UI styling and theme definitions
│   ├── services/
│   │   ├── api.py                            # HTTP calls to FastAPI backend
│   │   └── mock_backend.py                   # Mock responses for local UI development without backend
│   └── utils/
│       └── helpers.py                        # Shared utility functions (formatting, validation)
├── data/
│   └── raw/
│       ├── HDB_full_resale_info.csv.gz        # Full HDB resale transaction dataset (1990–2026, ~971k rows)
│       ├── HDBPropertyInformation.csv         # Lease commencement dates for LBS calculation
│       ├── HousingAndDevelopmentBoard...csv   # Quarterly RPI data
│       ├── propertyguru_listings_final.csv    # Scraped and cleaned PropertyGuru listings (12,192)
│       ├── CHASClinics.geojson                # Clinic locations (SLA)
│       ├── CommunityClubs.geojson             # Community club locations
│       ├── HawkerCentresGEOJSON.geojson       # Hawker centre locations
│       ├── LTAMRTStationExitGEOJSON.geojson   # MRT station exits (LTA)
│       ├── NParksParksandNatureReserves.geojson  # Parks and nature reserves (NParks)
│       └── address_coords_cache.csv           # Cached geocoding results to reduce OneMap API calls
├── models/
│   ├── hdb_model_artifacts_v2.pkl             # Serialised XGBoost model, encoders, and training artifacts
│   └── block_street_to_town.json              # Lookup table mapping block/street to HDB town
├── requirements.txt
└── README.md
```text

---

## Data Sources

| Dataset | Source | Usage |
|---|---|---|
| HDB Resale Transactions (1990–2026) | [data.gov.sg](https://data.gov.sg) | XGBoost model training |
| HDB Property Information | [data.gov.sg](https://data.gov.sg) | Lease commencement date lookup |
| HDB Resale Price Index (RPI) | [data.gov.sg](https://data.gov.sg) | Price normalisation at training and inference |
| PropertyGuru Listings | PropertyGuru (scraped) | Recommendation candidate pool (12,192 listings) |
| OneMap API | [onemap.gov.sg](https://www.onemap.gov.sg) | Geocoding, amenity proximity, town resolution |
| Amenity GeoJSON Files | data.gov.sg/LTA/NParks | Geospatial computation of amenity distances and counts |

---

## Prerequisites
- Python 3.10+
- OneMap account credentials — register at [https://www.onemap.gov.sg](https://www.onemap.gov.sg)


## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/sanjeevr123/DSE3101-Project.git
cd DSE3101-Project
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

In the `frontend/` directory, copy `.env.example` to `.env` and fill in your OneMap credentials:

```bash
cp frontend/.env.example frontend/.env
```

Edit `frontend/.env`:
ONEMAP_API_EMAIL=your_email@example.com
ONEMAP_API_PASSWORD=your_password

### 4. Run the backend

From the project root:

```bash
uvicorn backend.main:app --reload
```

Backend runs at `http://127.0.0.1:8000`. Visit `http://127.0.0.1:8000/docs` for the interactive API docs.

### 5. Run the frontend

In a separate terminal, from the `frontend/` directory:

```bash
python app.py
```

Open `http://127.0.0.1:8050` in your browser.

---

## Model

### Algorithm
The price prediction model is an XGBoost regressor trained on ~250,000 HDB resale transactions spanning 2015 to 2026.

### Target Variable
Rather than predicting raw resale price, the model predicts a normalised log price:
```text
log_price_norm = log(resale_price / (floor_area_sqm × RPI_annual))
```
Dividing by floor_area_sqm converts the target to a per-square-metre basis, removing the mechanical size-price relationship. Dividing by the annual average RPI removes the macro market trend, so the model learns only the structural and locational value of each flat. At inference, predictions are inverted back to SGD:
```text
estimated_price = exp(log_price_norm_pred) × floor_area_sqm × CURRENT_RPI
```
The live RPI is fetched from the data.gov.sg API at server startup, ensuring predictions are always anchored to the prevailing market level without requiring model retraining.

### Preprocessing
- **Deduplication** — duplicate rows removed via DataFrame.drop_duplicates()
- **RPI merging** — quarterly RPI data converted from wide to long format, averaged annually, and merged onto each transaction row by sold_year
- **Categorical encoding** — town, flat_type, storey_category, and region label-encoded using sklearn LabelEncoder; encoders are persisted in the model artifacts to ensure consistent mappings at inference
- **Feature exclusions** — identifiers, raw coordinates, lease derivations, and any columns derived from resale_price (e.g. town_median_price) were excluded to prevent data leakage
- **Geospatial features** — distances to and counts of nearby amenities (MRT, hawker centres, parks, clinics, community clubs) were pre-computed by geocoding each flat's address via OneMap and calculating distances against Singapore's public amenity datasets
- **Sample weights** — transactions are assigned linearly increasing weights by recency, ranging from 1.0 (oldest year) to 2.0 (most recent training year), reflecting that recent market conditions are more representative of current pricing

---

## Key Features (Ranked by Importance)

| Feature | Description |
|---------|-------------|
| `is_mature_estate` | Consistent price premium for mature estates |
| `max_floor_lvl` | Maximum floor level of the block |
| `region` | Regional location grouping |
| `remaining_lease` | Non-linear lease decay effect; CPF restrictions apply below ~70 years |
| `storey_category` | Floor level — Low / Mid / High |
| `nearest_mrt_distance_m` | Within-town MRT proximity; not fully captured by town alone |
| `num_amenities_within_1000m` | Total amenities within 1km radius |
| `flat_type` | Size and layout category |

---

## Cross-Validation Strategy
A time-based train/test split was used rather than random k-fold cross-validation:

```text
Training set: All transactions with sold_year < 2023
Test set: All transactions with sold_year ≥ 2023
```

This mirrors real-world deployment conditions where the model is trained on historical data and evaluated on future unseen transactions. Random k-fold splitting would allow future transactions to leak into the training set, producing inflated evaluation metrics that would not reflect actual out-of-sample performance. Early stopping (50 rounds) was applied during training using the held-out test set as the evaluation set, automatically selecting the best iteration and preventing overfitting.

---

## Model Performance

| Evaluation Set | RMSE | MAPE |
|----------------|-----|------|
| Internal test set (2023+ transactions) | $43,872 | ~4.78% |

---

## SAI Score
The Senior Accessibility Index (SAI) is computed for each PropertyGuru listing using the distances to and counts of nearby senior-critical amenities: MRT stations, hawker centres, parks, clinics, and community clubs. Each amenity dimension is weighted by the user's stated lifestyle preferences, supplied via sliders in the frontend. Listings are ranked by their weighted SAI score, ensuring recommendations are tailored to each individual user's accessibility priorities rather than a one-size-fits-all ranking.

---

## Application Interface

The frontend is structured as a **five-step wizard** designed specifically for senior users, following established UX principles to minimise cognitive load and decision fatigue.

### Five-Step Wizard

| Step | Description |
|------|-------------|
| **Step 1** | Enter current flat details — postal code, flat type, floor area, remaining lease |
| **Step 2** | View estimated selling price with ±10% confidence interval and town median benchmark |
| **Step 3** | Set downsizing preferences — maximum budget, flat type, preferred towns |
| **Step 4** | Review LBS financial estimate; set amenity priority weights |
| **Step 5** | View top 3 listing recommendations with SAI scores, cash unlocked estimates, interactive map, flat comparison modal, and direct PropertyGuru links |

Each recommendation card displays the listed price, estimated cash unlocked from downsizing, distance from the user's current flat, and nearby amenities within 1km. An interactive Leaflet map overlays the user's current flat, recommended flats, and surrounding amenities, with layer toggling to reduce visual clutter. A comparison modal allows users to assess trade-offs across all three recommendations side-by-side.

---

## API Reference

### `POST /predict/sell`

Estimates the selling price of the user's current flat.

**Request body:**
```json
{
  "postal": "560123",
  "flat_type": "4 ROOM",
  "floor_area_sqm": 93,
  "remaining_lease": 72
}
```

**Response:**
```json
{
  "price": 750000,
  "low": 697500,
  "high": 802500,
  "median_town": 720000,
  "town": "ANG MO KIO"
}
```
## Price Prediction Output

| Field | Description |
|-------|-------------|
| `price` | Point estimate of current market value (SGD) |
| `low` / `high` | ±10% indicative confidence interval |
| `median_town` | Median resale price for same flat type in same town |
| `town` | HDB town resolved from postal code via OneMap |

---

### `POST /recommend`

Returns the top 3 recommended listings based on user constraints and lifestyle preferences.

**Request body:**
```json
{
  "constraints": {
    "max_budget": 600000,
    "max_rooms": 3,
    "preferred_towns": ["Tampines", "Bedok"]
  },
  "weights": {
    "clinic": 8,
    "hawker": 6,
    "park": 5,
    "mrt": 9
  }
}
```

**Response** (list of up to 3):
```json
[
  {
    "town": "Tampines",
    "rooms": 3,
    "postal": "520228",
    "buy_price": 550000,
    "listing_url": "https://www.propertyguru.com.sg/...",
    "address_from_url": "228 SIMEI STREET 4 SINGAPORE 520228",
    "predicted_price": 520000,
    "valuation_label": "Above Market"
  }
]
```

## Listing Recommendation Fields

| Field | Description |
|-------|-------------|
| `buy_price` | PropertyGuru asking price (SGD) |
| `predicted_price` | Model-estimated fair market value |
| `valuation_label` | One of: **Fair Value**, **Above Market**, **Below Market** |
| `listing_url` | Direct link to the live PropertyGuru listing |

---

## Known Limitations
- **Listing freshness** — the PropertyGuru listing pool is a scraped snapshot and is not updated in real time; listings may have been taken down or repriced since scraping
- **User-facing prediction** — geospatial features (MRT distance, amenity counts) are imputed from town-level medians when a specific block address is not provided; the ±10% confidence band reflects this uncertainty
- **Listing premiums** — per-town and per-flat-type multipliers used to bridge transacted and asking prices were calibrated from a single listing snapshot and should be recalibrated periodically
- **English only** — the interface does not currently support other languages, limiting accessibility for seniors more comfortable in Mandarin, Malay, or Tamil
- **Mobile responsiveness** — the layout has not been fully optimised for small-screen devices; seniors accessing via tablet or phone may encounter display issues

---

## Contributors
- Sharuz
- Avaneesh
- Aswin
- Sanjeev
- Amanda
- Nathaniel 
- Harsha
- Vidushi