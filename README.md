# HomeCompass — HDB Downsizing Helper

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

**Course**: DSE3101 | **AY2025/2026** | **Group**: flatfinders

HomeCompass is a senior-friendly web application that helps elderly Singaporean HDB homeowners (aged 65 and above) make informed housing decisions. It combines a flat price estimator, a Senior Accessibility Index (SAI) scoring system, and a Lease Buyback Scheme (LBS) calculator into a guided five-step interface.

You can access the deployed app **[here](https://homecompass.onrender.com)**. Please open the **[backend](https://homecompass-backend.onrender.com/health)** link first and wait for it to load before launching the app as it is hosted on Render free tier and may take 1–2 minutes to wake up.

---

## Tech Stack

- **Frontend**: Python Dash, Dash Bootstrap Components, Leaflet.js (via iframe)
- **Backend**: FastAPI, Uvicorn, Pydantic
- **ML**: XGBoost, scikit-learn, pandas, NumPy, joblib
- **External APIs**: OneMap API (SLA) — geocoding, address resolution

---

## Prerequisites

- Python 3.10+
- OneMap account credentials — register at [https://www.onemap.gov.sg](https://www.onemap.gov.sg)

---

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

`valuation_label` is one of: `Fair Value`, `Above Market`, `Below Market`.

---

## Data Sources

| Dataset | Source | Usage |
|---|---|---|
| HDB Resale Transactions (1990–present) | [data.gov.sg](https://data.gov.sg) | XGBoost model training |
| HDB Property Information | [data.gov.sg](https://data.gov.sg) | Lease commencement date lookup |
| HDB Resale Price Index (RPI) | [data.gov.sg](https://data.gov.sg) | Price normalisation at training and inference |
| PropertyGuru Listings | PropertyGuru (scraped) | Recommendation candidate pool (12,192 listings) |
| OneMap API | [onemap.gov.sg](https://www.onemap.gov.sg) | Geocoding, amenity distances, town resolution |