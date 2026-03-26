BACKEND_URL = "http://127.0.0.1:8000"
TIMEOUT_SEC = 6
ONEMAP_SEARCH_URL = "https://www.onemap.gov.sg/api/common/elastic/search"
ONEMAP_REVERSE_GEOCODE_URL = "https://www.onemap.gov.sg/api/public/revgeocode"
ONEMAP_TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoxMjEyMCwiZm9yZXZlciI6ZmFsc2UsImlzcyI6Ik9uZU1hcCIsImlhdCI6MTc3NDE3OTM5MSwibmJmIjoxNzc0MTc5MzkxLCJleHAiOjE3NzQ0Mzg1OTEsImp0aSI6ImRjNTE4MTU4LTVlN2UtNDZmZC05YWZmLTU0MWQxNWUwNTJjZSJ9.DB4YwPcdb7-icP5FXzx7Q5nL2H1YO6h5ladvnrYeVi46OCGI6eRkc2DcM5YjqPrYoYnrZ0RY_KOAzKj1fe-dhjj0CM_rFBFB2nouxs2hSf0Qx45WtWu8DnDFsGsY6LHemziKtyDTfvbNQGHPh2fX5JOanRlNP2-U_KfAMxtD9NWx9PrtOufRwgHXxxMWxwP0eQeBBw3-yRNy6o-EfcE2UV0tMgVtyC2kJHWKMrvzLprmoj8lj2xT5ETd52X2WLawZyX5mpHixNoriydaXKI6lR2Ntdsq76C_na5WGDurN29WPQ6QbmbdpPFwF0k005LU2-q3A9wW76XJGhJoAjYTag"
DATA_GOV_API_KEY = "v2:c9ed14bd6d2d9c9667a3e7b509a11d432231159500282eca500daaa311e7a8f7:grc7IN7jf0IKQDBdSl_RM-TUvyzbIVzw"
TRANSPORT_DATASET_ID = "d_b39d3a0871985372d7e1637193335da5"

AMENITY_CACHE_FILE = "amenity_cache.json"
AMENITY_CACHE_TTL = 3600
AMENITY_CACHE_VERSION = "v4"
API_REQUEST_DELAY_SEC = 1.5

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
