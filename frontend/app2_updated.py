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
#   Member 8 (Output)   — Step 4 result cards, PropertyGuru links, equity display
#
# Look for comments tagged with your member number, e.g.:
#   # MEMBER 7: adjust font size here
#   # MEMBER 6: change marker colour here
#   # MEMBER 8: update card layout here
#   # MEMBER 5: replace with real backend call
# ============================================================================


import logging
logging.basicConfig(level=logging.DEBUG, force=True)
logger = logging.getLogger("amenity_debug")
logger.setLevel(logging.DEBUG)
logger.debug("[Startup] amenity_debug logger is active.")

# Utility: Print all OneMap themes related to healthcare for QUERYNAME discovery
def print_healthcare_themes(onemap_token):
    """
    Prints all OneMap themes whose name or description contains 'health', 'hospital', or 'clinic'.
    Pass your OneMap API token as the argument.
    """
    url = "https://www.onemap.gov.sg/api/common/thematic/getAllThemesInfo"
    headers = {"Authorization": f"Bearer {onemap_token}"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        print("\n[OneMap] Healthcare-related themes:")
        for theme in data.get("THEMES", []):
            name = theme.get("THEMENAME", "")
            desc = theme.get("DESCRIPTION", "")
            queryname = theme.get("QUERYNAME", "")
            if any(x in (name+desc).lower() for x in ["health", "hospital", "clinic"]):
                print(f"  - Name: {name}\n    Description: {desc}\n    QUERYNAME: {queryname}\n")
        print("[Done] Use the QUERYNAME(s) above in your amenity fetch logic.")
    except Exception as e:
        print(f"[Error] Could not fetch OneMap themes: {e}")

from dash import Dash, html, dcc, Input, Output, State
import dash
import requests
import time
import json as json_module
import csv
import io
from config.settings import (
    BACKEND_URL,
    TIMEOUT_SEC,
    ONEMAP_SEARCH_URL,
    ONEMAP_REVERSE_GEOCODE_URL,
    ONEMAP_TOKEN,
    DATA_GOV_API_KEY,
    TRANSPORT_DATASET_ID,
    AMENITY_CACHE_FILE,
    AMENITY_CACHE_TTL,
    AMENITY_CACHE_VERSION,
    API_REQUEST_DELAY_SEC,
    FALLBACK_AMENITIES,
)
from config.style import (
    PAGE_BG,
    SHADOW,
    base_page_style,
    container_style,
    title_style,
    card_style,
    label_style,
    input_style_big,
    btn_primary,
    btn_back,
    btn_reset,
    banner_ok,
    banner_warn,
)
from services.api import (
    safe_post,
    onemap_search,
    get_nearby_amenity_location,
    onemap_reverse_geocode,
    get_amenities_from_datagov,
)
from services.mock_backend import mock_predict_price, mock_recommendations
from utils.helpers import build_propertyguru_url, weights_from_sliders, haversine_km

app = Dash(__name__, suppress_callback_exceptions=True)
server = app.server

# ============================================================================
# BACKEND / API UTILITIES — imported from services/api.py
# ============================================================================


# ============================================================================
# MAP — MEMBER 6: this is your main section
# ============================================================================


def leaflet_map_html(center_lat, center_lon, points, amenities, zoom=14):
    """
    Generate a complete Leaflet HTML page as a string for iframe injection.
    MEMBER 6: customise tile layer, marker styles, legend, popups, zoom.
    """
    def js_point(p):
        return {
            "name": p["name"], 
            "lat": p["lat"], 
            "lon": p["lon"], 
            "color": p.get("color", "#0ea5e9"),
            "price": p.get("price", "N/A"),        # Adding price information
            "distance": p.get("distance", "N/A")   # Adding distance information
        }

    def js_am(a):
        return {
            "name": a.get("name") or "Unnamed amenity", 
            "lat": a["lat"], 
            "lon": a["lon"], 
            "kind": a.get("kind", "Amenity"),
            "address": a.get("address") or "Address not available",
            "distance": a.get("distance", "N/A")
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
    /* MEMBER 6: adjust popup font styling */
    .leaflet-popup-content {{ font-size: 16px; font-weight: 700; }}
    /* MEMBER 6: adjust legend position, colours, font */
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
  <!-- MEMBER 6: update legend labels and dot colours -->
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


    // MEMBER 6: tile layer — could switch to OneMap tiles
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 19, attribution: '&copy; OpenStreetMap'
    }}).addTo(map);

    const points = {points_js};
    const amenities = {amen_js};
    const homeIcon = L.icon({{
      iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-blue.png',
      iconSize: [25, 41],
      iconAnchor: [12, 41],
      popupAnchor: [1, -34],
    }});
    const recommendIcon = L.icon({{
      iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-green.png',
      iconSize: [25, 41],
      iconAnchor: [12, 41],
      popupAnchor: [1, -34],
    }});
    const amenityIcon = L.icon({{
      iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-orange.png',
      iconSize: [25, 41],
      iconAnchor: [12, 41],
      popupAnchor: [1, -34],
    }});

    // Add markers for points
    points.forEach((p, index) => {{
      const icon = index === 0 ? homeIcon : recommendIcon;
      L.marker([p.lat, p.lon], {{ icon: icon }}).addTo(map).bindPopup(`<b>${{p.name}}</b><br>Estimated price: $${{p.price}}<br>Distance from your flat: ${{p.distance}}`);
    }});

    // Add markers for amenities
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
        html: iconHtml,
        className: 'amenity-icon',
        iconSize: [30, 30],
        iconAnchor: [15, 15]
      }});
      L.marker([a.lat, a.lon], {{ icon: amenityIcon }}).addTo(map).bindPopup(`<b>${{a.name}}</b><br>Address: ${{a.address}}<br>Distance: ${{a.distance}} from your HDB`);
    }});

    // MEMBER 6: adjust fit-bounds padding
    const all = points.map(p => [p.lat, p.lon]).concat(amenities.map(a => [a.lat, a.lon]));
    if (all.length > 1) {{ map.fitBounds(L.latLngBounds(all).pad(0.18)); }}
  </script>
</body>
</html>
"""




# ============================================================================
# STEP INDICATOR — MEMBER 7: style the progress bar
# ============================================================================

def step_indicator(step):
    """
    The 1 → 2 → 3 → 4 progress bar at the top of every page.
    MEMBER 7: adjust circle size, colours, connector style, label fonts.
    """
    steps = [("1", "Price estimate"), ("2", "What matters"), ("3", "Your limits"), ("4", "Results")]
    chips = []
    for i, (num, name) in enumerate(steps, start=1):
        active = (i == step)
        chips.append(
            html.Div([
                html.Div(num, style={
                    "width": "52px",             # MEMBER 7: circle diameter
                    "height": "52px",
                    "borderRadius": "999px",
                    "display": "flex", "alignItems": "center", "justifyContent": "center",
                    "fontSize": "22px",          # MEMBER 7: number font size
                    "fontWeight": "950",
                    "background": "#0ea5e9" if active else "rgba(15,23,42,0.08)",  # MEMBER 7: active vs inactive
                    "color": "white" if active else "#0f172a",
                    "border": "2px solid rgba(15,23,42,0.12)",
                }),
                html.Div(name, style={
                    "fontSize": "18px",          # MEMBER 7: label font size
                    "fontWeight": "950",
                    "opacity": 1 if active else 0.72,
                    "marginTop": "8px",
                    "textAlign": "center",
                    "width": "140px",
                }),
            ], style={"display": "flex", "flexDirection": "column", "alignItems": "center"})
        )
        if i < 4:
            # MEMBER 7: connector line between steps
            chips.append(html.Div(style={
                "height": "4px", "flex": "1",
                "background": "rgba(15,23,42,0.12)",  # MEMBER 7: connector colour
                "borderRadius": "999px",
                "margin": "0 12px",
                "alignSelf": "center",
            }))
    return html.Div(chips, style={"display": "flex", "alignItems": "center", "marginTop": "16px"})


def nav_row(step):
    """Back/Next navigation buttons. MEMBER 7: adjust labels and disabled appearance."""
    labels = {1: "Next →", 2: "Next →", 3: "See results →", 4: "Back"}
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
# MEMBER 7: form layout   |   MEMBER 5: callback wiring

def step_1_estimate():
    return html.Div([
        # MEMBER 7: step heading — adjust fontSize, fontWeight
        html.Div("Step 1: Estimate your flat price", style={"fontSize": "36px", "fontWeight": "950"}),
        html.Div([
            html.Div("Postal code", style=label_style),
            dcc.Input(id="sell_postal", type="text", placeholder="Example: 560123", style=input_style_big),
            html.Div(style={"height": "14px"}),  # MEMBER 7: spacing between fields

            html.Div("Flat type", style=label_style),
            dcc.Dropdown(
                id="sell_flat_type",
                options=["2 ROOM", "3 ROOM", "4 ROOM", "5 ROOM", "EXECUTIVE"],
                value="4 ROOM", clearable=False,
                style={"fontSize": "22px"},  # MEMBER 7: dropdown font size
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


# ── STEP 2: Priority sliders ──────────────────────────────────────────────
# MEMBER 7: slider layout and styling

def step_2_preferences():
    slider_style = {"padding": "10px 6px"}  # MEMBER 7: slider container padding
    return html.Div([
        html.Div("Step 2: Tell us what matters to you", style={"fontSize": "36px", "fontWeight": "950"}),
        html.Div([
            # MEMBER 7: adjust emoji, label text, default value for each slider
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


# ── STEP 3: Budget & constraints ──────────────────────────────────────────
# MEMBER 7: form layout   |   MEMBER 8: expand town list

def step_3_limits():
    return html.Div([
        html.Div("Step 3: Tell us your limits", style={"fontSize": "36px", "fontWeight": "950"}),
        html.Div([
            html.Div("💵 Maximum budget to buy ($)", style=label_style),
            dcc.Input(id="lim_budget", type="number", value=550000, style=input_style_big),
            html.Div(style={"height": "14px"}),

            html.Div("🛏️ Minimum rooms", style=label_style),
            dcc.Dropdown(id="lim_min_rooms", options=[2, 3, 4, 5], value=3, clearable=False,
                         style={"fontSize": "22px"}),
            html.Div(style={"height": "14px"}),

            # MEMBER 8: verify this covers all 26 HDB towns
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


# ── STEP 4: Results ───────────────────────────────────────────────────────
# MEMBER 8: result cards + layout   |   MEMBER 6: map

def step_4_results():
    return html.Div([
        html.Div("Step 4: Results", style={"fontSize": "36px", "fontWeight": "950"}),
        html.Div([
            # Left column: results — MEMBER 8: owns this section
            html.Div([
                html.Button("Run results", id="btn_run_all", n_clicks=0, style=btn_primary),
                html.Div(id="results_list", style={"marginTop": "16px"}),
                html.Div([
                    html.Button("Start over", id="btn_reset", n_clicks=0, style=btn_reset),
                ], style={"marginTop": "14px"}),
            ], style={
                "flex": "1",
                "minWidth": "420px",  # MEMBER 8: min width of results column
            }),

            # Right column: map — MEMBER 6: owns this section
            html.Div([
                html.Div("Map (zoom and drag)", style={
                    "fontSize": "22px",   # MEMBER 6: map header font size
                    "fontWeight": "950",
                    "marginBottom": "10px",
                }),
                html.Iframe(
                    id="results_map",
                    srcDoc="<html><body style='font-family:system-ui;padding:16px'>Run results to view map.</body></html>",
                    style={
                        "width": "100%",
                        "height": "720px",     # MEMBER 6: map height
                        "border": "0",
                        "borderRadius": "18px",  # MEMBER 6: map corner rounding
                        "boxShadow": SHADOW,
                        "background": "white",
                    },
                ),
            ], style={
                "flex": "1.2",
                "minWidth": "520px",  # MEMBER 6: min width of map column
            }),
        ], style={
            **card_style,
            "display": "flex",
            "gap": "18px",            # MEMBER 7: gap between results and map columns
            "alignItems": "flex-start",
        }),
    ])


# ============================================================================
# LAYOUT — MEMBER 5: overall structure
# ============================================================================

app.layout = html.Div([
    # Client-side stores — MEMBER 5: data persists across steps
    dcc.Store(id="step", data=1),
    dcc.Store(id="sell_payload"),
    dcc.Store(id="sell_geo"),
    dcc.Store(id="sell_pred"),
    dcc.Store(id="prefs_weights"),
    dcc.Store(id="constraints"),
    dcc.Store(id="recs_data"),

    html.Div([
        html.Div([
            # MEMBER 7: title emoji and text
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
    pages = {1: step_1_estimate, 2: step_2_preferences, 3: step_3_limits, 4: step_4_results}
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
        return min(step + 1, 4)
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

    # MEMBER 5: try real backend first, fall back to mock
    pred = safe_post("/predict/sell", sell_payload)
    if not pred:
        pred = mock_predict_price(sell_payload["postal"], sell_payload["flat_type"], sell_payload.get("floor_area_sqm"))

    # MEMBER 7: style price display — large number, confidence range
    box = html.Div([
        html.Div("Estimated selling price", style={"fontSize": "22px", "fontWeight": "950", "opacity": "0.85"}),
        html.Div(f"${pred['price']:,.0f}", style={
            "fontSize": "52px",           # MEMBER 7: main price font size
            "fontWeight": "950",
        }),
        html.Div(f"Range: ${pred['low']:,.0f} – ${pred['high']:,.0f}", style={
            "fontSize": "22px", "fontWeight": "900", "opacity": "0.85",
        }),
        html.Div(f"Town median (rough): ${pred.get('median_town', int(pred['price'] * 0.98)):,.0f}", style={
            "fontSize": "22px", "fontWeight": "900", "opacity": "0.80",
        }),
    ], style={"marginTop": "14px"})
    return pred, box


# ── Step 2: save weights ──

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


# ── Step 3: save constraints ──

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


# ── Step 4: run results ──
# MEMBER 5: orchestration | MEMBER 8: cards | MEMBER 6: map

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
    # Validation
    if not sell_payload or not sell_payload.get("postal"):
        return html.Div("Please go back to Step 1 and enter your postal code.", style=banner_warn), dash.no_update, None
    if not sell_geo:
        return html.Div("We could not locate your flat. Please check postal code in Step 1.", style=banner_warn), dash.no_update, None
    if not prefs_w:
        return html.Div("Please complete Step 2.", style=banner_warn), dash.no_update, None
    if not constraints:
        return html.Div("Please complete Step 3.", style=banner_warn), dash.no_update, None

    if not sell_pred:
        sell_pred = mock_predict_price(sell_payload["postal"], sell_payload["flat_type"], sell_payload.get("floor_area_sqm"))

    # MEMBER 5: replace mock with real backend call when ready:
    #   payload = {"sell_payload": sell_payload, "sell_pred": sell_pred,
    #              "weights": prefs_w, "constraints": constraints}
    #   recs = safe_post("/recommend", payload)
    #   if not recs:
    #       recs = mock_recommendations(constraints)
    recs = mock_recommendations(constraints)

    # Geocode each recommendation
    for r in recs:
        geo = onemap_search(r["postal"]) or onemap_search(f"Singapore {r['postal']}")
        if geo:
            r["lat"], r["lon"], r["address"] = geo["lat"], geo["lon"], geo["address"]
            
            # Calculate the distance from the user's current flat (sell_geo) to this recommended flat
            r["dist_from_home_km"] = haversine_km(sell_geo["lat"], sell_geo["lon"], r["lat"], r["lon"])
        else:
            # Fallback for geocoding failure
            r["lat"] = sell_geo["lat"] + 0.01  # Default to slightly different coordinates
            r["lon"] = sell_geo["lon"] + 0.01
            r["address"] = f"{r['town']} (approx)"
            r["dist_from_home_km"] = 0.01  # Default distance if geocoding fails

    # Derived fields
    for r in recs:
        r["cash_unlocked"] = int(sell_pred["price"] - r["buy_price"])
        dist = haversine_km(sell_geo["lat"], sell_geo["lon"], r["lat"], r["lon"])
        r["dist_from_home_km"] = round(dist, 2) if dist is not None else 0.0

    # ── Result cards — MEMBER 8: customise everything in this block ──
    cards = []
    for i, r in enumerate(recs, start=1):
        pg_url = build_propertyguru_url(
            town=r["town"], rooms=r["rooms"],
            min_price=max(0, int(r["buy_price"] * 0.90)),
            max_price=int(r["buy_price"] * 1.10),
        )
        cards.append(html.Div([
            # MEMBER 8: card title
            html.Div(f"#{i} • {r['town']} • {r['rooms']} rooms", style={
                "fontSize": "28px",           # MEMBER 8: title size
                "fontWeight": "950",
            }),
            # MEMBER 8: buy price
            html.Div(f"Buy price (estimate): ${r['buy_price']:,.0f}", style={
                "fontSize": "22px", "fontWeight": "900",
            }),
            # MEMBER 8: cash unlocked
            html.Div(f"Cash unlocked (estimate): ${r['cash_unlocked']:,.0f}", style={
                "fontSize": "22px", "fontWeight": "900",
            }),
            # MEMBER 8: distance
            html.Div(f"Distance from your flat: {r['dist_from_home_km']} km", style={
                "fontSize": "20px", "fontWeight": "900", "opacity": "0.88",
            }),
            # MEMBER 8: amenity distances
            html.Div(
                f"Amenities nearby: Clinic ~{r['clinic_dist_m']}m • Hawker ~{r['hawker_dist_m']}m • Park ~{r['park_dist_m']}m",
                style={"fontSize": "20px", "fontWeight": "850", "opacity": "0.85"},
            ),
            # MEMBER 8: MRT distance
            html.Div(f"MRT distance (approx): {r['mrt_dist_km']:.2f} km", style={
                "fontSize": "20px", "fontWeight": "850", "opacity": "0.85",
            }),
            # MEMBER 8: PropertyGuru link
            html.A("🔎 View matching listings on PropertyGuru", href=pg_url, target="_blank", style={
                "display": "inline-block",
                "marginTop": "10px",
                "fontSize": "20px",           # MEMBER 8: link size
                "fontWeight": "950",
                "textDecoration": "none",
                "color": "#0ea5e9",           # MEMBER 8: link colour
            }),
        ], style={**card_style, "marginTop": "14px"}))

    # ── Map — MEMBER 6: customise markers and amenities ──
    points = [
        {"name": f"Your flat ({sell_payload['postal']})", "lat": sell_geo["lat"], "lon": sell_geo["lon"], "color": "#0ea5e9"},
    ]
    for r in recs:
        points.append({
            "name": f"Option: {r['town']} ({r['postal']})",
            "lat": r["lat"], 
            "lon": r["lon"], 
            "color": "#22c55e", 
            "price": r["buy_price"],
            "distance": f"{r['dist_from_home_km']} km"
        })

    # Fetch real amenities from data.gov.sg — MEMBER 6: customize collection IDs
    amenities = []
    base_lat, base_lon = sell_geo["lat"], sell_geo["lon"]
    radius_km = 2.0
    hawker_debug_rows = []
    for idx, r in enumerate(recs):
        rec_lat, rec_lon = r["lat"], r["lon"]

        # Healthcare (CHAS clinics, sorted by distance)
        healthcare_amenities = get_amenities_from_datagov("healthcare", rec_lat, rec_lon, radius_km=2.0, limit=9999)
        healthcare_with_dist = []
        for amenity in healthcare_amenities:
            dist = haversine_km(rec_lat, rec_lon, amenity["lat"], amenity["lon"])
            healthcare_with_dist.append({**amenity, "distance_km": dist})
        healthcare_with_dist.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 9999)
        logger.info(f"DEBUG: Found {len(healthcare_with_dist)} clinics for rec #{idx+1} at ({rec_lat}, {rec_lon})")
        for amenity in healthcare_with_dist:
            dist_from_home = amenity["distance_km"]
            dist_str = f"{dist_from_home:.2f} km" if dist_from_home is not None else "N/A"
            amenities.append({
                "name": amenity["name"],
                "lat": amenity["lat"],
                "lon": amenity["lon"],
                "kind": "healthcare",
                "address": amenity.get("address", ""),
                "distance": dist_str
            })

        # Hawker centres (API, fallback if needed)
        hawker_amenities = get_amenities_from_datagov("hawker", rec_lat, rec_lon, radius_km=2.0, limit=100)
        hawker_with_dist = []
        for amenity in hawker_amenities:
            dist = haversine_km(rec_lat, rec_lon, amenity["lat"], amenity["lon"])
            if dist is not None and dist <= 2.0:
                hawker_with_dist.append({**amenity, "distance_km": dist})
        hawker_with_dist.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 9999)
        logger.info(f"DEBUG: Found {len(hawker_with_dist)} hawker centres within 2km for rec #{idx+1} at ({rec_lat}, {rec_lon})")
        for amenity in hawker_with_dist:
            dist_from_home = amenity["distance_km"]
            dist_str = f"{dist_from_home:.2f} km" if dist_from_home is not None else "N/A"
            amenities.append({
                "name": amenity["name"],
                "lat": amenity["lat"],
                "lon": amenity["lon"],
                "kind": "hawker centre",
                "address": amenity.get("address", ""),
                "distance": dist_str
            })
            hawker_debug_rows.append([
                amenity["name"], amenity.get("address", ""), amenity["lat"], amenity["lon"], dist_str
            ])

        # Transport (API dataset linked by TRANSPORT_DATASET_ID)
        transport_amenities = get_amenities_from_datagov("transport", rec_lat, rec_lon, radius_km=2.0, limit=100)
        transport_with_dist = []
        for amenity in transport_amenities:
            dist = haversine_km(rec_lat, rec_lon, amenity["lat"], amenity["lon"])
            if dist is not None and dist <= 2.0:
                transport_with_dist.append({**amenity, "distance_km": dist})
        transport_with_dist.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 9999)
        logger.info(f"DEBUG: Found {len(transport_with_dist)} transport points within 2km for rec #{idx+1} at ({rec_lat}, {rec_lon})")
        for amenity in transport_with_dist:
            dist_from_home = amenity["distance_km"]
            dist_str = f"{dist_from_home:.2f} km" if dist_from_home is not None else "N/A"
            amenities.append({
                "name": amenity["name"],
                "lat": amenity["lat"],
                "lon": amenity["lon"],
                "kind": "transport",
                "address": amenity.get("address", ""),
                "distance": dist_str
            })

        # Nature parks (API, fallback if needed)
        park_amenities = get_amenities_from_datagov("parks", rec_lat, rec_lon, radius_km=2.0, limit=100)
        park_with_dist = []
        for park in park_amenities:
            dist = haversine_km(rec_lat, rec_lon, park["lat"], park["lon"])
            if dist is not None and dist <= 2.0:
                park_with_dist.append({**park, "distance_km": dist})
        park_with_dist.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 9999)
        logger.info(f"DEBUG: Found {len(park_with_dist)} parks within 2km for rec #{idx+1} at ({rec_lat}, {rec_lon})")
        for park in park_with_dist:
            dist_from_home = park["distance_km"]
            dist_str = f"{dist_from_home:.2f} km" if dist_from_home is not None else "N/A"
            amenities.append({
                "name": park["name"],
                "lat": park["lat"],
                "lon": park["lon"],
                "kind": "nature",
                "address": park.get("address", ""),
                "distance": dist_str
            })
            hawker_debug_rows.append([
                park["name"], park.get("address", ""), park["lat"], park["lon"], dist_str
            ])

        # NOTE: We intentionally skip healthcare/parks/mrt for now to reduce API load.

    map_doc = leaflet_map_html(sell_geo["lat"], sell_geo["lon"], points, amenities, zoom=14)

    # Display hawker centre debug table
    hawker_table = html.Table([
        html.Tr([html.Th("Name"), html.Th("Address"), html.Th("Lat"), html.Th("Lon"), html.Th("Distance from home")])
    ] + [html.Tr([html.Td(x) for x in row]) for row in hawker_debug_rows], style={"marginTop": "18px", "fontSize": "16px", "background": "#f9fafb", "borderRadius": "12px", "padding": "8px"})

    return html.Div([*cards, hawker_table]), map_doc, recs


# ── Reset ──

@app.callback(
    Output("step", "data", allow_duplicate=True),
    Output("sell_payload", "data", allow_duplicate=True),
    Output("sell_geo", "data", allow_duplicate=True),
    Output("sell_pred", "data", allow_duplicate=True),
    Output("prefs_weights", "data", allow_duplicate=True),
    Output("constraints", "data", allow_duplicate=True),
    Output("recs_data", "data", allow_duplicate=True),
    Input("btn_reset", "n_clicks"),
    prevent_initial_call=True,
)
def reset_all(n):
    return 1, None, None, None, None, None, None


# ============================================================================
# RUN
# ============================================================================
if __name__ == "__main__":
    app.run(debug=True)