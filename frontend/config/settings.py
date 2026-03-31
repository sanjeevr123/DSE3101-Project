
import os
from pathlib import Path

_FRONTEND_DIR = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
    # Override existing process env vars so edits in .env are reflected after restart.
    load_dotenv(_FRONTEND_DIR / ".env", override=True)
except ImportError:
    # python-dotenv not installed — parse .env manually as a fallback
    _env_path = _FRONTEND_DIR / ".env"
    if _env_path.is_file():
        with open(_env_path, encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if not _line or _line.startswith("#") or "=" not in _line:
                    continue
                _key, _val = _line.split("=", 1)
                _key = _key.strip()
                _val = _val.strip().strip('"').strip("'")
                os.environ.setdefault(_key, _val)

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
TIMEOUT_SEC = int(os.getenv("TIMEOUT_SEC", "6"))

ONEMAP_BASE_URL = os.getenv("ONEMAP_BASE_URL", "https://www.onemap.gov.sg")
ONEMAP_SEARCH_URL = f"{ONEMAP_BASE_URL}/api/common/elastic/search"
ONEMAP_REVERSE_GEOCODE_URL = f"{ONEMAP_BASE_URL}/api/public/revgeocode"
ONEMAP_TOKEN = os.getenv("ONEMAP_TOKEN", "").strip()
ONEMAP_API_EMAIL = os.getenv("ONEMAP_API_EMAIL", "").strip()
ONEMAP_API_PASSWORD = os.getenv("ONEMAP_API_PASSWORD", "").strip()

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
    "healthcare": [
        {"name": "Changi General Hospital", "address": "2 Simei St 3, Singapore 529889", "lat": 1.3405, "lon": 103.9496},
        {"name": "Sengkang General Hospital", "address": "110 Sengkang East Way, Singapore 544886", "lat": 1.3917, "lon": 103.8940},
        {"name": "Khoo Teck Puat Hospital", "address": "90 Yishun Central, Singapore 768828", "lat": 1.4246, "lon": 103.8384},
        {"name": "Singapore General Hospital", "address": "Outram Rd, Singapore 169608", "lat": 1.2794, "lon": 103.8349},
        {"name": "Ng Teng Fong General Hospital", "address": "1 Jurong East St 21, Singapore 609606", "lat": 1.3331, "lon": 103.7437},
        {"name": "Tan Tock Seng Hospital", "address": "11 Jalan Tan Tock Seng, Singapore 308433", "lat": 1.3215, "lon": 103.8452},
        {"name": "KK Women's and Children's Hospital", "address": "100 Bukit Timah Rd, Singapore 229899", "lat": 1.3106, "lon": 103.8463},
        {"name": "National University Hospital", "address": "5 Lower Kent Ridge Rd, Singapore 119074", "lat": 1.2933, "lon": 103.7845},
        {"name": "Alexandra Hospital", "address": "378 Alexandra Rd, Singapore 159964", "lat": 1.2870, "lon": 103.8018},
        {"name": "Bedok Polyclinic", "address": "11 Bedok North St 1, Singapore 469662", "lat": 1.3267, "lon": 103.9327},
        {"name": "Tampines Polyclinic", "address": "1 Tampines St 41, Singapore 529203", "lat": 1.3569, "lon": 103.9442},
        {"name": "Marine Parade Polyclinic", "address": "80 Marine Parade Central, Singapore 440080", "lat": 1.3037, "lon": 103.9072},
        {"name": "Punggol Polyclinic", "address": "681 Punggol Dr, Singapore 820681", "lat": 1.4017, "lon": 103.9067},
        {"name": "Sengkang Polyclinic", "address": "2 Sengkang Sq, Singapore 545025", "lat": 1.3910, "lon": 103.8957},
        {"name": "Ang Mo Kio Polyclinic", "address": "21 Ang Mo Kio Central 2, Singapore 569666", "lat": 1.3725, "lon": 103.8467},
        {"name": "Bukit Batok Polyclinic", "address": "50 Bukit Batok West Ave 3, Singapore 659164", "lat": 1.3497, "lon": 103.7495},
        {"name": "Choa Chu Kang Polyclinic", "address": "2 Teck Whye Crescent, Singapore 688846", "lat": 1.3817, "lon": 103.7501},
        {"name": "Clementi Polyclinic", "address": "451 Clementi Ave 3, Singapore 120451", "lat": 1.3136, "lon": 103.7655},
        {"name": "Eunos Polyclinic", "address": "1 Chin Cheng Ave, Singapore 429401", "lat": 1.3140, "lon": 103.9021},
        {"name": "Geylang Polyclinic", "address": "21 Geylang East Central, Singapore 389707", "lat": 1.3186, "lon": 103.8858},
        {"name": "Hougang Polyclinic", "address": "89 Hougang Ave 4, Singapore 538829", "lat": 1.3700, "lon": 103.8957},
        {"name": "Jurong Polyclinic", "address": "190 Jurong East Ave 1, Singapore 609788", "lat": 1.3481, "lon": 103.7298},
        {"name": "Kallang Polyclinic", "address": "2A Boon Keng Rd, Singapore 329772", "lat": 1.3130, "lon": 103.8627},
        {"name": "Outram Polyclinic", "address": "3 Second Hospital Ave, Singapore 168937", "lat": 1.2812, "lon": 103.8344},
        {"name": "Pasir Ris Polyclinic", "address": "1 Pasir Ris Dr 4, Singapore 519457", "lat": 1.3732, "lon": 103.9499},
        {"name": "Pioneer Polyclinic", "address": "26 Jurong West St 61, Singapore 648201", "lat": 1.3508, "lon": 103.6943},
        {"name": "Toa Payoh Polyclinic", "address": "2003 Lorong 8 Toa Payoh, Singapore 319260", "lat": 1.3369, "lon": 103.8498},
        {"name": "Woodlands Polyclinic", "address": "10 Woodlands St 31, Singapore 738579", "lat": 1.4315, "lon": 103.7731},
        {"name": "Yishun Polyclinic", "address": "30A Yishun Central 1, Singapore 768796", "lat": 1.4300, "lon": 103.8354},
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
