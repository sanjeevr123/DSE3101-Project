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
#   Member 8 (Output)   — Step 5 result cards, PropertyGuru links, equity display
#
# STEP ORDER:
#   1 — Price estimate
#   2 — LBS scenario          ← NEW (inserted between steps 1 and 2)
#   3 — What matters to you   ← was 2
#   4 — Your limits           ← was 3; lim_budget pre-filled from lbs_result
#   5 — Results               ← was 4
#
# Look for comments tagged with your member number, e.g.:
#   # MEMBER 7: adjust font size here
#   # MEMBER 6: change marker colour here
#   # MEMBER 8: update card layout here
#   # MEMBER 5: replace with real backend call
# ============================================================================

from dash import Dash, html, dcc, Input, Output, State, ALL
import dash
import requests
from urllib.parse import urlencode
import math

# ============================================================================
# CONFIG — MEMBER 5: update backend URL when backend team is ready
# ============================================================================
BACKEND_URL = "http://127.0.0.1:8000"
TIMEOUT_SEC = 6
ONEMAP_SEARCH_URL = "https://www.onemap.gov.sg/api/common/elastic/search"

app = Dash(__name__, suppress_callback_exceptions=True)
server = app.server

# ============================================================================
# STYLING — MEMBER 7: this is your main section to customise
# ============================================================================

PAGE_BG = "linear-gradient(135deg, #e8f7ff 0%, #eefcf3 55%, #f2f5ff 100%)"
SHADOW = "0 10px 26px rgba(15, 23, 42, 0.12)"

base_page_style = {
    "minHeight": "100vh",
    "background": PAGE_BG,
    "padding": "22px 18px",
    "fontFamily": "system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif",
    "color": "#0f172a",
}
container_style = {
    "maxWidth": "1180px",
    "margin": "0 auto",
}
title_style = {
    "fontSize": "46px",
    "fontWeight": "950",
    "margin": "0",
    "display": "flex",
    "alignItems": "center",
    "gap": "12px",
}
card_style = {
    "marginTop": "16px",
    "padding": "20px",
    "borderRadius": "24px",
    "background": "rgba(255,255,255,0.92)",
    "border": "1px solid rgba(15,23,42,0.10)",
    "boxShadow": "0 2px 0 rgba(0,0,0,0.03)",
}
label_style = {
    "fontSize": "22px",
    "fontWeight": "950",
    "marginBottom": "8px",
}
input_style_big = {
    "width": "100%",
    "padding": "18px",
    "fontSize": "24px",
    "borderRadius": "18px",
    "border": "2px solid rgba(15,23,42,0.18)",
}
btn_primary = {
    "padding": "16px 22px",
    "fontSize": "24px",
    "fontWeight": "950",
    "borderRadius": "18px",
    "border": "0",
    "background": "#0ea5e9",
    "color": "white",
    "boxShadow": SHADOW,
    "cursor": "pointer",
    "minHeight": "60px",
}
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
banner_ok = {
    "padding": "14px 16px",
    "borderRadius": "18px",
    "background": "rgba(34,197,94,0.15)",
    "border": "1px solid rgba(34,197,94,0.35)",
    "fontSize": "22px",
    "fontWeight": "950",
    "marginTop": "14px",
}
banner_warn = {
    "padding": "14px 16px",
    "borderRadius": "18px",
    "background": "rgba(239,68,68,0.12)",
    "border": "1px solid rgba(239,68,68,0.35)",
    "fontSize": "22px",
    "fontWeight": "950",
    "marginTop": "14px",
    "color": "#991b1b",
}


# ============================================================================
# PROPERTYGURU LINK HELPERS — MEMBER 8: expand and maintain
# ============================================================================

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
    # MEMBER 8: add remaining towns
}

PG_HDB_CODES_BY_ROOMS = {
    2: ["2A", "2Am", "2I", "2Im", "2S", "2STD"],
    3: ["3A", "3Am", "3I", "3Im", "3NG", "3NGm", "3PA", "3S", "3STD"],
    4: ["4A", "4Am", "4I", "4Im", "4NG", "4NGm", "4PA", "4S", "4STD"],
    5: ["5A", "5Am", "5I", "5Im", "5NG", "5NGm", "5PA", "5S", "5STD"],
}


def build_propertyguru_url(town, rooms, min_price, max_price, distance_to_mrt_km=0.5):
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
# BACKEND / API UTILITIES — MEMBER 5
# ============================================================================

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


# ============================================================================
# MOCK BACKEND — MEMBER 5: replace with real API when ready
# ============================================================================

def mock_predict_price(postal_code, flat_type, floor_area):
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
    return [
        {"town": "Ang Mo Kio", "rooms": 3, "postal": "560123", "buy_price": 480_000,
         "amenity_score": 84, "mrt_dist_km": 0.45, "clinic_dist_m": 220, "hawker_dist_m": 320, "park_dist_m": 380},
        {"town": "Bedok", "rooms": 3, "postal": "460123", "buy_price": 420_000,
         "amenity_score": 78, "mrt_dist_km": 0.35, "clinic_dist_m": 180, "hawker_dist_m": 260, "park_dist_m": 410},
        {"town": "Tampines", "rooms": 3, "postal": "520123", "buy_price": 430_000,
         "amenity_score": 80, "mrt_dist_km": 0.55, "clinic_dist_m": 260, "hawker_dist_m": 290, "park_dist_m": 520},
    ]


def weights_from_sliders(hc, tr, hw, rec):
    raw = {"healthcare": float(hc), "transport": float(tr), "hawker": float(hw), "recreation": float(rec)}
    s = sum(raw.values()) or 1.0
    return {k: raw[k] / s for k in raw}


# ============================================================================
# MAP — MEMBER 6
# ============================================================================

def haversine_km(lat1, lon1, lat2, lon2):
    """Straight-line distance in km between two coordinates."""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def leaflet_map_html(center_lat, center_lon, points, amenities, zoom=14):
    def js_point(p):
        return {
            "name": p["name"],
            "lat": p["lat"],
            "lon": p["lon"],
            "color": p.get("color", "#0ea5e9"),
            "price": p.get("price", "N/A"),
            "distance": p.get("distance", "N/A"),
        }

    def js_am(a):
        return {
            "name": a["name"],
            "lat": a["lat"],
            "lon": a["lon"],
            "kind": a.get("kind", "Amenity"),
            "address": a.get("address", "N/A"),
            "distance": a.get("distance", "N/A"),
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
    .leaflet-popup-content {{ font-size: 16px; font-weight: 700; }}
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
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 19, attribution: '&copy; OpenStreetMap'
    }}).addTo(map);
    const points = {points_js};
    const amenities = {amen_js};
    const homeIcon = L.icon({{
      iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-blue.png',
      iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34],
    }});
    const recommendIcon = L.icon({{
      iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-green.png',
      iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34],
    }});
    points.forEach((p, index) => {{
      const icon = index === 0 ? homeIcon : recommendIcon;
      L.marker([p.lat, p.lon], {{ icon: icon }}).addTo(map).bindPopup(`<b>${{p.name}}</b><br>Estimated price: $${{p.price}}<br>Distance from your flat: ${{p.distance}}`);
    }});
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
        html: iconHtml, className: 'amenity-icon', iconSize: [30, 30], iconAnchor: [15, 15]
      }});
      L.marker([a.lat, a.lon], {{ icon: amenityIcon }}).addTo(map).bindPopup(`<b>${{a.name}}</b><br>Address: ${{a.address}}<br>Distance: ${{a.distance}} from your HDB`);
    }});
    const all = points.map(p => [p.lat, p.lon]).concat(amenities.map(a => [a.lat, a.lon]));
    if (all.length > 1) {{ map.fitBounds(L.latLngBounds(all).pad(0.18)); }}
  </script>
</body>
</html>
"""


# ============================================================================
# LBS HELPERS — MEMBER 5 / MEMBER 8
# ============================================================================

# Maps skeleton flat type strings to LBS bonus tier codes
FLAT_TYPE_TO_LBS_CODE = {
    "2 ROOM": "2R",
    "3 ROOM": "3R",
    "4 ROOM": "4R",
    "5 ROOM": "5Rplus",
    "EXECUTIVE": "5Rplus",
}


def safe_num(x, default=0):
    try:
        if x is None or x == "":
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


def fmt_money(x):
    return f"${x:,.0f}"


def compute_required_ra(age, n):
    """
    Required RA balance for CPF top-up under LBS.
    NOTE: figures are hardcoded estimates — update annually.
    n = number of owners in the household.
    """
    if n == 1:
        if 65 <= age <= 69:
            return 220_400
        if 70 <= age <= 79:
            return 210_400
        return 200_400
    if 65 <= age <= 69:
        return 110_200
    if 70 <= age <= 79:
        return 105_200
    return 100_200


def compute_lbs(mv, remaining_lease, retained_lease, loan, owner_ages, owner_ras, flat_type_skeleton):
    """
    Compute LBS proceeds, CPF top-ups, bonus, and final RA balances.
    flat_type_skeleton: flat type in skeleton format e.g. "4 ROOM"
    Returns dict with all computed fields, or {"error": str}.
    """
    flat_type = FLAT_TYPE_TO_LBS_CODE.get(flat_type_skeleton, "5Rplus")
    n = len(owner_ages)

    if n not in [1, 2]:
        return {"error": "Only 1 or 2 owners are supported."}
    if remaining_lease <= 0:
        return {"error": "Remaining lease must be positive."}
    if retained_lease <= 0:
        return {"error": "Retained lease must be positive."}
    if retained_lease >= remaining_lease:
        return {"error": "Retained lease must be less than remaining lease."}
    if retained_lease < 20:
        return {"error": "HDB requires a minimum retained lease of 20 years."}
    if any(age < 65 for age in owner_ages):
        return {"error": "All owners must be at least 65 to apply for LBS."}

    lease_sold = remaining_lease - retained_lease
    lease_factor = lease_sold / remaining_lease

    gross_lbs = mv * lease_factor
    net_lbs = max(0, gross_lbs - loan)

    required_ras = [compute_required_ra(age, n) for age in owner_ages]
    topups = [max(0, req - bal) for req, bal in zip(required_ras, owner_ras)]
    total_topup_needed = sum(topups)

    cpf_from_lbs = min(net_lbs, total_topup_needed)
    cash_before_bonus = max(0, net_lbs - total_topup_needed)

    ratio = cpf_from_lbs / total_topup_needed if total_topup_needed > 0 else 0
    final_ras = [bal + need * ratio for bal, need in zip(owner_ras, topups)]

    # LBS bonus caps by flat type
    # MEMBER 8: verify against latest HDB circular before release
    if flat_type in ["2R", "3R"]:
        bonus_cap = 30_000
    elif flat_type == "4R":
        bonus_cap = 15_000
    else:
        bonus_cap = 7_500

    if total_topup_needed > 0:
        bonus = bonus_cap if cpf_from_lbs >= total_topup_needed else bonus_cap * (cpf_from_lbs / total_topup_needed)
    else:
        bonus = bonus_cap

    cash_total = cash_before_bonus + bonus

    return {
        "lease_sold": lease_sold,
        "gross_lbs": gross_lbs,
        "net_lbs": net_lbs,
        "cpf_from_lbs": cpf_from_lbs,
        "cash_before_bonus": cash_before_bonus,
        "bonus_lbs": bonus,
        "cash_total": cash_total,
        "ra_household_start": sum(owner_ras),
        "ra_household_final": sum(final_ras),
        "final_ra_balances": final_ras,
        "retained_lease": retained_lease,
        "remaining_lease": remaining_lease,
    }


def lbs_metric_box(label, value, color="#0ea5e9"):
    """Single metric card for LBS results. MEMBER 8: adjust font sizes and colour."""
    return html.Div([
        html.Div(label, style={
            "fontSize": "18px",
            "fontWeight": "900",
            "opacity": "0.72",
            "marginBottom": "4px",
        }),
        html.Div(value, style={
            "fontSize": "28px",
            "fontWeight": "950",
            "color": color,
        }),
    ], style={
        **card_style,
        "marginTop": "0",
        "padding": "14px 18px",
        "flex": "1",
        "minWidth": "180px",
    })


# ============================================================================
# STEP INDICATOR — MEMBER 7: style the progress bar
# ============================================================================

def step_indicator(step):
    """
    1 → 2 → 3 → 4 → 5 progress bar.
    MEMBER 7: adjust circle size, colours, connector style, label fonts.
    """
    steps = [
        ("1", "Price estimate"),
        ("2", "LBS scenario"),      # NEW
        ("3", "What matters"),
        ("4", "Your limits"),
        ("5", "Results"),
    ]
    chips = []
    for i, (num, name) in enumerate(steps, start=1):
        active = (i == step)
        chips.append(
            html.Div([
                html.Div(num, style={
                    "width": "52px",
                    "height": "52px",
                    "borderRadius": "999px",
                    "display": "flex", "alignItems": "center", "justifyContent": "center",
                    "fontSize": "22px",
                    "fontWeight": "950",
                    "background": "#0ea5e9" if active else "rgba(15,23,42,0.08)",
                    "color": "white" if active else "#0f172a",
                    "border": "2px solid rgba(15,23,42,0.12)",
                }),
                html.Div(name, style={
                    "fontSize": "18px",
                    "fontWeight": "950",
                    "opacity": 1 if active else 0.72,
                    "marginTop": "8px",
                    "textAlign": "center",
                    "width": "120px",       # MEMBER 7: slightly narrower to fit 5 chips
                }),
            ], style={"display": "flex", "flexDirection": "column", "alignItems": "center"})
        )
        if i < 5:
            chips.append(html.Div(style={
                "height": "4px", "flex": "1",
                "background": "rgba(15,23,42,0.12)",
                "borderRadius": "999px",
                "margin": "0 8px",          # MEMBER 7: reduced from 12px to fit 5 chips
                "alignSelf": "center",
            }))
    return html.Div(chips, style={"display": "flex", "alignItems": "center", "marginTop": "16px"})


def nav_row(step):
    """Back/Next navigation. MEMBER 7: adjust labels and disabled appearance."""
    labels = {1: "Next →", 2: "Next →", 3: "Next →", 4: "See results →", 5: "Back"}
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

def step_1_estimate():
    return html.Div([
        html.Div("Step 1: Estimate your flat price", style={"fontSize": "36px", "fontWeight": "950"}),
        html.Div([
            html.Div("Postal code", style=label_style),
            dcc.Input(id="sell_postal", type="text", placeholder="Example: 560123", style=input_style_big),
            html.Div(style={"height": "14px"}),

            html.Div("Flat type", style=label_style),
            dcc.Dropdown(
                id="sell_flat_type",
                options=["2 ROOM", "3 ROOM", "4 ROOM", "5 ROOM", "EXECUTIVE"],
                value="4 ROOM", clearable=False,
                style={"fontSize": "22px"},
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


# ── STEP 2: LBS scenario ──────────────────────────────────────────────────
# MEMBER 7: form layout   |   MEMBER 8: result cards   |   MEMBER 5: callback

def step_2_lbs():
    return html.Div([
        html.Div("Step 2: Lease Buyback Scheme scenario", style={"fontSize": "36px", "fontWeight": "950"}),

        html.Div([
            html.Div(
                "If you're considering the Lease Buyback Scheme (LBS), fill in the details below to estimate "
                "how much cash you could unlock. Flat type and market value are pre-filled from Step 1. "
                "Your result will automatically pre-fill your budget in Step 4.",
                style={"fontSize": "20px", "opacity": "0.80", "marginBottom": "18px"},
            ),

            # ── Flat details ──────────────────────────────────────────────
            html.Div("Flat details", style={**label_style, "fontSize": "26px", "marginTop": "0"}),

            html.Div("Flat type", style=label_style),
            dcc.Dropdown(
                id="lbs_flat_type",
                options=["2 ROOM", "3 ROOM", "4 ROOM", "5 ROOM", "EXECUTIVE"],
                value="4 ROOM", clearable=False,
                style={"fontSize": "22px"},
            ),
            html.Div(style={"height": "14px"}),

            html.Div("Market value of flat (SGD)", style=label_style),
            dcc.Input(id="lbs_mv", type="number", value=500_000, min=0, style=input_style_big),
            html.Div(style={"height": "14px"}),

            html.Div("Remaining lease (years)", style=label_style),
            dcc.Input(id="lbs_remaining_lease", type="number", value=60, min=1, style=input_style_big),
            html.Div(style={"height": "14px"}),

            html.Div("Retained lease after LBS (years, min 20)", style=label_style),
            dcc.Input(id="lbs_retained_lease", type="number", value=30, min=20, style=input_style_big),
            html.Div(style={"height": "14px"}),

            html.Div("Outstanding housing loan (SGD)", style=label_style),
            dcc.Input(id="lbs_loan", type="number", value=0, min=0, style=input_style_big),

            html.Hr(style={"margin": "22px 0"}),

            # ── Owner details ─────────────────────────────────────────────
            html.Div("Owners & CPF Retirement Accounts", style={**label_style, "fontSize": "26px"}),

            html.Div("Number of owners", style=label_style),
            dcc.Dropdown(
                id="lbs_num_owners",
                options=[{"label": "1 owner", "value": 1}, {"label": "2 owners", "value": 2}],
                value=2, clearable=False,
                style={"fontSize": "22px"},
            ),
            html.Div(style={"height": "14px"}),

            html.Div(id="lbs_owners_inputs"),

            html.Hr(style={"margin": "22px 0"}),

            html.Button("Calculate LBS outcome", id="btn_lbs_calculate", n_clicks=0, style=btn_primary),

        ], style=card_style),

        # Results render here after button click
        html.Div(id="lbs_output"),
    ])


# ── STEP 3: Priority sliders ──────────────────────────────────────────────

def step_3_preferences():
    slider_style = {"padding": "10px 6px"}
    return html.Div([
        html.Div("Step 3: Tell us what matters to you", style={"fontSize": "36px", "fontWeight": "950"}),
        html.Div([
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


# ── STEP 4: Budget & constraints ──────────────────────────────────────────

def step_4_limits():
    return html.Div([
        html.Div("Step 4: Tell us your limits", style={"fontSize": "36px", "fontWeight": "950"}),
        html.Div([
            html.Div("💵 Maximum budget to buy ($)", style=label_style),
            # MEMBER 5: this field is pre-filled from lbs_result store via prefill_budget_from_lbs()
            dcc.Input(id="lim_budget", type="number", value=550_000, style=input_style_big),
            html.Div(style={"height": "14px"}),

            html.Div("🛏️ Minimum rooms", style=label_style),
            dcc.Dropdown(id="lim_min_rooms", options=[2, 3, 4, 5], value=3, clearable=False,
                         style={"fontSize": "22px"}),
            html.Div(style={"height": "14px"}),

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


# ── STEP 5: Results ───────────────────────────────────────────────────────

def step_5_results():
    return html.Div([
        html.Div("Step 5: Results", style={"fontSize": "36px", "fontWeight": "950"}),
        html.Div([
            html.Div([
                html.Button("Run results", id="btn_run_all", n_clicks=0, style=btn_primary),
                html.Div(id="results_list", style={"marginTop": "16px"}),
                html.Div([
                    html.Button("Start over", id="btn_reset", n_clicks=0, style=btn_reset),
                ], style={"marginTop": "14px"}),
            ], style={"flex": "1", "minWidth": "420px"}),

            html.Div([
                html.Div("Map (zoom and drag)", style={
                    "fontSize": "22px",
                    "fontWeight": "950",
                    "marginBottom": "10px",
                }),
                html.Iframe(
                    id="results_map",
                    srcDoc="<html><body style='font-family:system-ui;padding:16px'>Run results to view map.</body></html>",
                    style={
                        "width": "100%",
                        "height": "720px",
                        "border": "0",
                        "borderRadius": "18px",
                        "boxShadow": SHADOW,
                        "background": "white",
                    },
                ),
            ], style={"flex": "1.2", "minWidth": "520px"}),
        ], style={**card_style, "display": "flex", "gap": "18px", "alignItems": "flex-start"}),
    ])


# ============================================================================
# LAYOUT — MEMBER 5: overall structure
# ============================================================================

app.layout = html.Div([
    # Client-side stores
    dcc.Store(id="step", data=1),
    dcc.Store(id="sell_payload"),
    dcc.Store(id="sell_geo"),
    dcc.Store(id="sell_pred"),
    dcc.Store(id="lbs_result"),         # NEW — holds LBS cash_total for Step 4 pre-fill
    dcc.Store(id="prefs_weights"),
    dcc.Store(id="constraints"),
    dcc.Store(id="recs_data"),

    html.Div([
        html.Div([
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
    pages = {
        1: step_1_estimate,
        2: step_2_lbs,          # NEW
        3: step_3_preferences,  # shifted
        4: step_4_limits,       # shifted
        5: step_5_results,      # shifted
    }
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
        return min(step + 1, 5)     # max step is now 5
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

    pred = safe_post("/predict/sell", sell_payload)
    if not pred:
        pred = mock_predict_price(sell_payload["postal"], sell_payload["flat_type"], sell_payload.get("floor_area_sqm"))

    box = html.Div([
        html.Div("Estimated selling price", style={"fontSize": "22px", "fontWeight": "950", "opacity": "0.85"}),
        html.Div(f"${pred['price']:,.0f}", style={"fontSize": "52px", "fontWeight": "950"}),
        html.Div(f"Range: ${pred['low']:,.0f} – ${pred['high']:,.0f}", style={
            "fontSize": "22px", "fontWeight": "900", "opacity": "0.85",
        }),
        html.Div(f"Town median (rough): ${pred.get('median_town', int(pred['price'] * 0.98)):,.0f}", style={
            "fontSize": "22px", "fontWeight": "900", "opacity": "0.80",
        }),
    ], style={"marginTop": "14px"})
    return pred, box


# ── Step 2: LBS — render owner input blocks ──

@app.callback(
    Output("lbs_owners_inputs", "children"),
    Input("lbs_num_owners", "value"),
)
def render_lbs_owner_inputs(n):
    blocks = []
    for i in range(int(n or 1)):
        blocks.append(html.Div([
            html.Div(f"Owner {i + 1}", style={**label_style, "fontSize": "24px"}),

            html.Div("Age", style=label_style),
            dcc.Input(
                id={"type": "lbs_owner_age", "index": i},
                type="number", value=70, min=65,
                style=input_style_big,
            ),
            html.Div(style={"height": "10px"}),

            html.Div("Existing CPF RA balance (SGD)", style=label_style),
            dcc.Input(
                id={"type": "lbs_owner_ra", "index": i},
                type="number", value=50_000, min=0,
                style=input_style_big,
            ),
        ], style={**card_style, "marginTop": "10px", "background": "rgba(248,250,252,0.95)"}))
    return blocks


# ── Step 2: LBS — compute and display results ──

@app.callback(
    Output("lbs_output", "children"),
    Output("lbs_result", "data"),
    Input("btn_lbs_calculate", "n_clicks"),
    State("lbs_mv", "value"),
    State("lbs_remaining_lease", "value"),
    State("lbs_retained_lease", "value"),
    State("lbs_loan", "value"),
    State("lbs_flat_type", "value"),
    State("lbs_num_owners", "value"),
    State({"type": "lbs_owner_age", "index": ALL}, "value"),
    State({"type": "lbs_owner_ra", "index": ALL}, "value"),
    prevent_initial_call=True,
)
def compute_lbs_output(n_clicks, mv, remaining_lease, retained_lease,
                       loan, flat_type, num_owners, owner_ages, owner_ras):
    num_owners = int(num_owners or 1)
    mv = safe_num(mv)
    remaining_lease = safe_num(remaining_lease)
    retained_lease = safe_num(retained_lease)
    loan = safe_num(loan)

    if mv <= 0:
        return html.Div("Please enter a valid market value.", style=banner_warn), None
    if remaining_lease <= 0 or retained_lease <= 0:
        return html.Div("Please enter valid lease values.", style=banner_warn), None
    if len(owner_ages) < num_owners or len(owner_ras) < num_owners:
        return html.Div("Please fill in all owner details.", style=banner_warn), None

    ages = [safe_num(x) for x in owner_ages[:num_owners]]
    ras = [safe_num(x) for x in owner_ras[:num_owners]]

    result = compute_lbs(
        mv=mv,
        remaining_lease=remaining_lease,
        retained_lease=retained_lease,
        loan=loan,
        owner_ages=ages,
        owner_ras=ras,
        flat_type_skeleton=flat_type,
    )

    if "error" in result:
        return html.Div(result["error"], style=banner_warn), None

    # ── Result cards — MEMBER 8: customise layout and colours ────────────
    metrics_row_1 = html.Div([
        lbs_metric_box("Lease sold", f"{result['lease_sold']:.1f} years"),
        lbs_metric_box("Retained lease", f"{result['retained_lease']:.1f} years"),
    ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginBottom": "12px"})

    metrics_row_2 = html.Div([
        lbs_metric_box("Gross LBS proceeds", fmt_money(result["gross_lbs"])),
        lbs_metric_box("Net after loan repayment", fmt_money(result["net_lbs"])),
    ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginBottom": "12px"})

    metrics_row_3 = html.Div([
        lbs_metric_box("CPF top-up from LBS", fmt_money(result["cpf_from_lbs"])),
        lbs_metric_box("Cash before bonus", fmt_money(result["cash_before_bonus"])),
    ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginBottom": "12px"})

    metrics_row_4 = html.Div([
        lbs_metric_box("LBS bonus (estimate)", fmt_money(result["bonus_lbs"])),
        lbs_metric_box("Total immediate cash", fmt_money(result["cash_total"]), color="#22c55e"),
    ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginBottom": "12px"})

    ra_summary = html.Div([
        html.Div("CPF Retirement Account summary", style={
            "fontSize": "22px", "fontWeight": "950", "marginBottom": "10px",
        }),
        html.Div(f"Household RA before LBS: {fmt_money(result['ra_household_start'])}",
                 style={"fontSize": "20px", "fontWeight": "900", "marginBottom": "6px"}),
        html.Div(f"Household RA after LBS: {fmt_money(result['ra_household_final'])}",
                 style={"fontSize": "20px", "fontWeight": "900"}),
    ], style={**card_style, "marginTop": "12px", "background": "rgba(248,250,252,0.95)"})

    prefill_notice = html.Div(
        f"✅ Your buying budget in Step 4 has been pre-filled with your estimated cash: {fmt_money(result['cash_total'])}",
        style=banner_ok,
    )

    output_block = html.Div([
        html.Div("LBS scenario results", style={
            "fontSize": "28px", "fontWeight": "950", "marginTop": "22px", "marginBottom": "14px",
        }),
        metrics_row_1,
        metrics_row_2,
        metrics_row_3,
        metrics_row_4,
        ra_summary,
        prefill_notice,
    ])

    lbs_result_store = {
        "cash_total": result["cash_total"],
        "net_lbs": result["net_lbs"],
        "bonus_lbs": result["bonus_lbs"],
        "ra_household_final": result["ra_household_final"],
    }

    return output_block, lbs_result_store


# ── Step 4: pre-fill budget from LBS result ──
# MEMBER 5: fires whenever lbs_result store is updated

@app.callback(
    Output("lim_budget", "value"),
    Input("lbs_result", "data"),
    prevent_initial_call=True,
)
def prefill_budget_from_lbs(lbs_result):
    if lbs_result and lbs_result.get("cash_total"):
        return int(lbs_result["cash_total"])
    return dash.no_update


# ── Step 2: pre-fill LBS flat type from sell_payload (Step 1) ──
# MEMBER 5: fires when user selects flat type in Step 1

@app.callback(
    Output("lbs_flat_type", "value"),
    Input("sell_payload", "data"),
    prevent_initial_call=True,
)
def prefill_lbs_flat_type(sell_payload):
    if sell_payload and sell_payload.get("flat_type"):
        return sell_payload["flat_type"]
    return dash.no_update


# ── Step 2: pre-fill LBS market value from sell_pred (Step 1) ──
# MEMBER 5: fires when user clicks "Estimate price" in Step 1

@app.callback(
    Output("lbs_mv", "value"),
    Input("sell_pred", "data"),
    prevent_initial_call=True,
)
def prefill_lbs_mv(sell_pred):
    if sell_pred and sell_pred.get("price"):
        return int(sell_pred["price"])
    return dash.no_update


# ── Step 3: save weights ──

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


# ── Step 4: save constraints ──

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


# ── Step 5: run results ──

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
    if not sell_payload or not sell_payload.get("postal"):
        return html.Div("Please go back to Step 1 and enter your postal code.", style=banner_warn), dash.no_update, None
    if not sell_geo:
        return html.Div("We could not locate your flat. Please check postal code in Step 1.", style=banner_warn), dash.no_update, None
    if not prefs_w:
        return html.Div("Please complete Step 3.", style=banner_warn), dash.no_update, None
    if not constraints:
        return html.Div("Please complete Step 4.", style=banner_warn), dash.no_update, None

    if not sell_pred:
        sell_pred = mock_predict_price(sell_payload["postal"], sell_payload["flat_type"], sell_payload.get("floor_area_sqm"))

    # MEMBER 5: replace mock with real backend call when ready
    recs = mock_recommendations(constraints)

    for r in recs:
        geo = onemap_search(r["postal"]) or onemap_search(f"Singapore {r['postal']}")
        if geo:
            r["lat"], r["lon"], r["address"] = geo["lat"], geo["lon"], geo["address"]
            r["dist_from_home_km"] = haversine_km(sell_geo["lat"], sell_geo["lon"], r["lat"], r["lon"])
        else:
            r["lat"] = sell_geo["lat"] + 0.01
            r["lon"] = sell_geo["lon"] + 0.01
            r["address"] = f"{r['town']} (approx)"
            r["dist_from_home_km"] = 0.01

    for r in recs:
        r["cash_unlocked"] = int(sell_pred["price"] - r["buy_price"])
        r["dist_from_home_km"] = round(haversine_km(sell_geo["lat"], sell_geo["lon"], r["lat"], r["lon"]), 2)

    cards = []
    for i, r in enumerate(recs, start=1):
        pg_url = build_propertyguru_url(
            town=r["town"], rooms=r["rooms"],
            min_price=max(0, int(r["buy_price"] * 0.90)),
            max_price=int(r["buy_price"] * 1.10),
        )
        cards.append(html.Div([
            html.Div(f"#{i} • {r['town']} • {r['rooms']} rooms", style={
                "fontSize": "28px", "fontWeight": "950",
            }),
            html.Div(f"Buy price (estimate): ${r['buy_price']:,.0f}", style={
                "fontSize": "22px", "fontWeight": "900",
            }),
            html.Div(f"Cash unlocked (estimate): ${r['cash_unlocked']:,.0f}", style={
                "fontSize": "22px", "fontWeight": "900",
            }),
            html.Div(f"Distance from your flat: {r['dist_from_home_km']} km", style={
                "fontSize": "20px", "fontWeight": "900", "opacity": "0.88",
            }),
            html.Div(
                f"Amenities nearby: Clinic ~{r['clinic_dist_m']}m • Hawker ~{r['hawker_dist_m']}m • Park ~{r['park_dist_m']}m",
                style={"fontSize": "20px", "fontWeight": "850", "opacity": "0.85"},
            ),
            html.Div(f"MRT distance (approx): {r['mrt_dist_km']:.2f} km", style={
                "fontSize": "20px", "fontWeight": "850", "opacity": "0.85",
            }),
            html.A("🔎 View matching listings on PropertyGuru", href=pg_url, target="_blank", style={
                "display": "inline-block",
                "marginTop": "10px",
                "fontSize": "20px",
                "fontWeight": "950",
                "textDecoration": "none",
                "color": "#0ea5e9",
            }),
        ], style={**card_style, "marginTop": "14px"}))

    points = [
        {"name": f"Your flat ({sell_payload['postal']})", "lat": sell_geo["lat"], "lon": sell_geo["lon"], "color": "#0ea5e9"},
    ]
    for r in recs:
        points.append({
            "name": f"Option: {r['town']} ({r['postal']})",
            "lat": r["lat"], "lon": r["lon"], "color": "#22c55e",
            "price": r["buy_price"],
            "distance": f"{r['dist_from_home_km']} km",
        })

    clinic_names = ["ABC Medical Clinic", "HealthFirst Clinic", "CarePlus Medical Centre", "Unity Medical Clinic", "Wellness Family Clinic", "Singapore Health Clinic", "PrimeCare Clinic", "MediCare Centre", "Family Health Clinic", "Total Health Medical"]
    hawker_names = ["Chinatown Complex Food Centre", "Newton Food Centre", "Lau Pa Sat", "Maxwell Food Centre", "Tiong Bahru Market", "Golden Mile Food Centre", "Tekka Centre", "Amoy Street Food Centre", "Bukit Timah Market", "Commonwealth Crescent Market"]
    park_names = ["East Coast Park", "Bishan Park", "Botanic Gardens", "Marina Bay Sands Park", "Jurong Lake Gardens", "Pasir Ris Park", "Punggol Park", "Sengkang Riverside Park", "Tampines Eco Green", "Woodlands Waterfront Park"]
    transport_names = ["Ang Mo Kio MRT Station", "Bedok MRT Station", "Clementi MRT Station", "Dover MRT Station", "Eunos MRT Station", "Farrer Park MRT Station", "Geylang Bahru MRT Station", "Hougang MRT Station", "Jurong East MRT Station", "Kallang MRT Station"]

    amenities = []
    base_lat, base_lon = sell_geo["lat"], sell_geo["lon"]
    radius_km = 2.0

    for idx, r in enumerate(recs):
        rec_lat, rec_lon = r["lat"], r["lon"]

        for i in range(2):
            offset_lat = (i - 0.5) * 0.005
            offset_lon = (i - 0.5) * 0.005
            lat, lon = rec_lat + offset_lat, rec_lon + offset_lon
            if haversine_km(rec_lat, rec_lon, lat, lon) <= radius_km:
                amenities.append({"name": clinic_names[(idx * 2 + i) % len(clinic_names)], "lat": lat, "lon": lon, "kind": "healthcare", "address": f"{123 + idx*10 + i} Health St, {r['town']}", "distance": f"{haversine_km(base_lat, base_lon, lat, lon):.2f} km"})

        for i in range(2):
            offset_lat = (i % 2 - 0.5) * 0.006
            offset_lon = ((i // 2) - 0.5) * 0.006
            lat, lon = rec_lat + offset_lat, rec_lon + offset_lon
            if haversine_km(rec_lat, rec_lon, lat, lon) <= radius_km:
                amenities.append({"name": hawker_names[(idx * 2 + i) % len(hawker_names)], "lat": lat, "lon": lon, "kind": "hawker centre", "address": f"{456 + idx*10 + i} Food Ave, {r['town']}", "distance": f"{haversine_km(base_lat, base_lon, lat, lon):.2f} km"})

        for i in range(2):
            offset_lat = (i - 0.5) * 0.007
            offset_lon = (i - 0.5) * -0.007
            lat, lon = rec_lat + offset_lat, rec_lon + offset_lon
            if haversine_km(rec_lat, rec_lon, lat, lon) <= radius_km:
                amenities.append({"name": park_names[(idx * 2 + i) % len(park_names)], "lat": lat, "lon": lon, "kind": "nature", "address": f"{789 + idx*10 + i} Green Rd, {r['town']}", "distance": f"{haversine_km(base_lat, base_lon, lat, lon):.2f} km"})

        for i in range(2):
            offset_lat = ((i % 2) * 2 - 1) * 0.004
            offset_lon = ((i // 2) * 2 - 1) * 0.004
            lat, lon = rec_lat + offset_lat, rec_lon + offset_lon
            if haversine_km(rec_lat, rec_lon, lat, lon) <= radius_km:
                amenities.append({"name": transport_names[(idx * 2 + i) % len(transport_names)], "lat": lat, "lon": lon, "kind": "transport", "address": f"{101 + idx*10 + i} Transit Blvd, {r['town']}", "distance": f"{haversine_km(base_lat, base_lon, lat, lon):.2f} km"})

    map_doc = leaflet_map_html(sell_geo["lat"], sell_geo["lon"], points, amenities, zoom=14)
    return html.Div(cards), map_doc, recs


# ── Reset ──

@app.callback(
    Output("step", "data", allow_duplicate=True),
    Output("sell_payload", "data", allow_duplicate=True),
    Output("sell_geo", "data", allow_duplicate=True),
    Output("sell_pred", "data", allow_duplicate=True),
    Output("lbs_result", "data", allow_duplicate=True),     # NEW
    Output("prefs_weights", "data", allow_duplicate=True),
    Output("constraints", "data", allow_duplicate=True),
    Output("recs_data", "data", allow_duplicate=True),
    Input("btn_reset", "n_clicks"),
    prevent_initial_call=True,
)
def reset_all(n):
    return 1, None, None, None, None, None, None, None


# ============================================================================
# RUN
# ============================================================================
if __name__ == "__main__":
    app.run(debug=True)
