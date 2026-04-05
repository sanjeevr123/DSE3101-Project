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
from dash import Dash, html, dcc, Input, Output, State
import dash
import requests
import time
import json as json_module
import csv
import io
import re
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
def _fetch_onemap_healthcare(lat, lon, radius_km=1.0, limit=9999):
    return get_nearby_amenities("healthcare", lat, lon, radius_km=radius_km, limit=limit)

import dash_bootstrap_components as dbc
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
    get_nearby_amenities,
)
from services.mock_backend import mock_predict_price, mock_recommendations
from utils.helpers import build_propertyguru_url, weights_from_sliders, haversine_km

try:
    from frontend.lbs_required_patch import (
        STEP_META,
        lbs_stores,
        step_4_lbs,
        register_lbs_callbacks,
        build_lbs_result_card,
        validate_lbs_for_navigation,
    )
except ImportError:
    from lbs_required_patch import (
        STEP_META,
        lbs_stores,
        step_4_lbs,
        register_lbs_callbacks,
        build_lbs_result_card,
        validate_lbs_for_navigation,
    )

app = Dash(__name__, suppress_callback_exceptions=True, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server

register_lbs_callbacks(app, banner_ok=banner_ok, banner_warn=banner_warn, card_style=card_style)

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
    
    Points format: each point can have optional 'rec_index' to group recommendations into layers
    """
    def js_point(p):
        return {
            "name": p["name"], 
            "lat": p["lat"], 
            "lon": p["lon"], 
            "color": p.get("color", "#0ea5e9"),
            "price": p.get("price", "N/A"),        # Adding price information
            "distance": p.get("distance", "N/A"),  # Adding distance information
            "rec_index": p.get("rec_index", -1),   # MEMBER 6: -1 for your flat, >=0 for recommendations
        }

    def js_am(a):
        return {
            "name": a.get("name") or "Unnamed amenity", 
            "lat": a["lat"], 
            "lon": a["lon"], 
            "kind": a.get("kind", "Amenity"),
            "address": a.get("address"),  # None for transport amenities
            "distance": a.get("distance", "N/A"),
            "rec_index": a.get("rec_index", -1),   # MEMBER 6: which recommendation this amenity belongs to
        }

    points_js = json_module.dumps([js_point(p) for p in points])
    amen_js = json_module.dumps([js_am(a) for a in amenities])

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
    .legend-columns {{ display: flex; gap: 16px; align-items: flex-start; }}
    .legend-col {{ display: flex; flex-direction: column; }}
    .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 999px; margin-right: 8px; }}
    .amenity-icon {{ font-size: 18px; background: none; border: none; opacity: 1.0; }}
        .legend-title {{ font-size: 15px; font-weight: 900; margin-bottom: 8px; }}
        .legend-note {{ font-size: 12px; font-weight: 700; opacity: 0.75; margin-bottom: 8px; }}
        .toggle-row {{ display: flex; align-items: center; justify-content: space-between; gap: 10px; margin: 6px 0; }}
        .switch {{ position: relative; display: inline-block; width: 42px; height: 24px; }}
        .switch input {{ opacity: 0; width: 0; height: 0; }}
        .slider {{ position: absolute; cursor: pointer; inset: 0; background-color: #cbd5e1; transition: .2s; border-radius: 999px; }}
        .slider:before {{ position: absolute; content: ""; height: 18px; width: 18px; left: 3px; bottom: 3px; background-color: white; transition: .2s; border-radius: 50%; }}
        .switch input:checked + .slider {{ background-color: #0ea5e9; }}
        .switch input:checked + .slider:before {{ transform: translateX(18px); }}
  </style>
</head>
<body>
  <div id="map"></div>
  <!-- MEMBER 6: update legend labels and dot colours -->
    <div class="legend" id="layer-controls">
        <div class="legend-columns">
          <div class="legend-col">
            <div style="margin-bottom:8px; font-size:13px; font-weight:900;">🏠 Your flat</div>
            <div id="recommendation-toggles"></div>
          </div>
          <div style="border-left: 1px solid #e2e8f0; margin: 0 4px;"></div>
          <div class="legend-col">
            <div style="margin-bottom:8px; font-size:13px; font-weight:900;">Amenities</div>
            <div class="toggle-row">
                <span>🏥 Healthcare</span>
                <label class="switch"><input type="checkbox" data-kind="healthcare" checked><span class="slider"></span></label>
            </div>
            <div class="toggle-row">
                <span>🚇 MRT</span>
                <label class="switch"><input type="checkbox" data-kind="transport" checked><span class="slider"></span></label>
            </div>
            <div class="toggle-row">
                <span>🍜 Hawker / Food</span>
                <label class="switch"><input type="checkbox" data-kind="hawker / food" checked><span class="slider"></span></label>
            </div>
            <div class="toggle-row">
                <span>🌳 Parks</span>
                <label class="switch"><input type="checkbox" data-kind="nature" checked><span class="slider"></span></label>
            </div>
          </div>
        </div>
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
    
    // MEMBER 6: Create nested layer groups for amenities within each recommendation
    const recAmenityLayers = {{}};  // recAmenityLayers[recIdx][amenityKind] = layer
    const uniqueRecIndices = [...new Set(points.filter(p => p.rec_index >= 0).map(p => p.rec_index))];
    
    uniqueRecIndices.forEach(idx => {{
        recAmenityLayers[idx] = {{
            'healthcare': L.layerGroup().addTo(map),
            'transport': L.layerGroup().addTo(map),
            'hawker / food': L.layerGroup().addTo(map),
            'nature': L.layerGroup().addTo(map)
        }};
    }});
    
    // MEMBER 6: Create layer groups for each recommendation (flat markers)
    const recLayers = {{}};
    uniqueRecIndices.forEach(idx => {{
        recLayers[idx] = L.layerGroup().addTo(map);
    }});
    
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

    // Add markers for points (your flat + recommendations)
    points.forEach((p, index) => {{
      const icon = index === 0 ? homeIcon : recommendIcon;
    const marker = L.marker([p.lat, p.lon], {{ icon: icon, opacity: 1.0 }}).bindPopup(`<b>${{p.name}}</b><br>Estimated price: $${{p.price}}<br>Distance from your flat: ${{p.distance}}`);
      
      // MEMBER 6: Add to appropriate layer
      if (p.rec_index === -1) {{
        marker.addTo(map);  // Your flat always visible
      }} else {{
        marker.addTo(recLayers[p.rec_index]);  // Recommendation on its layer
      }}
    }});

    // Add markers for amenities (tied to specific recommendations)
    amenities.forEach(a => {{
      let iconHtml = '';
      switch(a.kind) {{
        case 'healthcare': iconHtml = '🏥'; break;
        case 'transport': iconHtml = '🚇'; break;
        case 'hawker / food': iconHtml = '🍜'; break;
        case 'nature': iconHtml = '🌳'; break;
        default: iconHtml = '📍';
      }}
      const amenityIcon = L.divIcon({{
        html: iconHtml,
        className: 'amenity-icon',
        iconSize: [22, 22],
        iconAnchor: [11, 11]
      }});
      const marker = L.marker([a.lat, a.lon], {{ icon: amenityIcon, opacity: 1.0 }}).bindPopup(`<b>${{a.name}}</b>${{a.address ? '<br>Address: ' + a.address : ''}}<br>Distance: ${{a.distance}} from your HDB`);
      
      // MEMBER 6: Add amenity to the nested layer group for its recommendation
      if (a.rec_index >= 0 && recAmenityLayers[a.rec_index]) {{
        const layer = recAmenityLayers[a.rec_index][a.kind];
        if (layer) {{
          marker.addTo(layer);
        }}
      }}
    }});
    
    // MEMBER 6: Generate toggles for recommendations in legend
    const recToggleContainer = document.getElementById('recommendation-toggles');
    points.forEach((p, idx) => {{
        if (p.rec_index >= 0) {{
            const toggleHtml = `
                <div class="toggle-row">
                    <span>🏢 ${{p.name.split(' • ')[0]}}</span>
                    <label class="switch"><input type="checkbox" data-rec-index="${{p.rec_index}}" checked><span class="slider"></span></label>
                </div>
            `;
            recToggleContainer.innerHTML += toggleHtml;
        }}
    }});

    // Event listeners for recommendation toggles
    // When a recommendation is toggled, toggle BOTH its marker AND its amenities
    document.querySelectorAll('#layer-controls input[data-rec-index]').forEach(cb => {{
        cb.addEventListener('change', (event) => {{
            const recIdx = parseInt(event.target.getAttribute('data-rec-index'));
            const recMarkerLayer = recLayers[recIdx];
            const recAmenities = recAmenityLayers[recIdx];
            
            if (event.target.checked) {{
                // Turn ON: show flat marker + amenities (if their toggles are enabled)
                if (recMarkerLayer && !map.hasLayer(recMarkerLayer)) {{
                    recMarkerLayer.addTo(map);
                }}
                // Add amenity layers if their global toggles are enabled
                if (recAmenities) {{
                    document.querySelectorAll('#layer-controls input[data-kind]').forEach(amenityToggle => {{
                        if (amenityToggle.checked) {{
                            const amenityKind = amenityToggle.getAttribute('data-kind');
                            const amenityLayer = recAmenities[amenityKind];
                            if (amenityLayer && !map.hasLayer(amenityLayer)) {{
                                amenityLayer.addTo(map);
                            }}
                        }}
                    }});
                }}
            }} else {{
                // Turn OFF: hide flat marker + all its amenities
                if (recMarkerLayer && map.hasLayer(recMarkerLayer)) {{
                    map.removeLayer(recMarkerLayer);
                }}
                if (recAmenities) {{
                    Object.values(recAmenities).forEach(amenityLayer => {{
                        if (amenityLayer && map.hasLayer(amenityLayer)) {{
                            map.removeLayer(amenityLayer);
                        }}
                    }});
                }}
            }}
        }});
    }});
    
    // Event listeners for amenity toggles
    // These toggle amenities across ALL active recommendations
    document.querySelectorAll('#layer-controls input[data-kind]').forEach(cb => {{
        cb.addEventListener('change', (event) => {{
            const amenityKind = event.target.getAttribute('data-kind');
            
            // Toggle this amenity type for all recommendations
            uniqueRecIndices.forEach(recIdx => {{
                const amenityLayer = recAmenityLayers[recIdx][amenityKind];
                if (!amenityLayer) return;
                
                if (event.target.checked) {{
                    // Turn ON amenity: show it if its recommendation is visible
                    const recMarkerLayer = recLayers[recIdx];
                    if (map.hasLayer(recMarkerLayer) && !map.hasLayer(amenityLayer)) {{
                        amenityLayer.addTo(map);
                    }}
                }} else {{
                    // Turn OFF amenity: hide it everywhere
                    if (map.hasLayer(amenityLayer)) {{
                        map.removeLayer(amenityLayer);
                    }}
                }}
            }});
        }});
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
    steps = STEP_META
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
        if i < len(steps):
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
    labels = {1: "Next →", 2: "Next →", 3: "Next →", 4: "See results →", 5: "Back"}
    next_label = labels.get(step, "Next →")

    back_style = dict(btn_back)
    if step == 1:
        back_style.update({"opacity": "0.45", "cursor": "not-allowed", "boxShadow": "none"})

    compare_style = {**btn_primary, "marginLeft": "10px", "backgroundColor": "#8b5cf6"} if step == 5 else {"display": "none"}

    return html.Div([
        html.Button("← Back", id="btn_back", n_clicks=0, style=back_style, disabled=(step == 1)),
        html.Div([
            html.Button(next_label, id="btn_next", n_clicks=0, style=btn_primary),
            html.Button("Compare Units", id="btn_compare", n_clicks=0, style=compare_style),
        ], style={"display": "flex", "gap": "10px"}),
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

            html.Div("Floor area (sqm)", style=label_style),
            dcc.Input(id="sell_area", type="number", placeholder="e.g. 93", style=input_style_big),
            html.Div(style={"height": "16px"}),

            html.Div("Remaining lease (years)", style=label_style),
            dcc.Input(id="sell_lease", type="number", placeholder="e.g. 72", style=input_style_big),
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

            html.Div("🚆 MRT", style=label_style),
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

            html.Div("🛏️ Flat Type", style=label_style),
            dcc.Dropdown(id="lim_min_rooms", options=[2, 3, 4, 5], value=3, clearable=False,
                         style={"fontSize": "22px"}),
            html.Div(style={"height": "14px"}),

            # MEMBER 8: verify this covers all 26 HDB towns
            html.Div("📍 Preferred towns (optional)", style=label_style),
            dcc.Dropdown(
                id="lim_towns",
                options=[
                    "Ang Mo Kio", "Bedok", "Bishan", "Bukit Batok", "Bukit Merah",
                    "Bukit Panjang", "Bukit Timah", "Central Area", "Choa Chu Kang", "Clementi", "Geylang",
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
def step_4_lbs_page():
    return step_4_lbs(
        card_style= card_style,
        label_style= label_style,
        input_style_big= input_style_big,
    )

def step_5_results():
    return html.Div([
        html.Div("Step 5: Results", style={"fontSize": "36px", "fontWeight": "950"}),
        html.Div('Compare units in detail by selecting and clicking the "Compare Units" button at the bottom of the page.', style={
            "fontSize": "18px",
            "fontWeight": "700",
            "opacity": "0.8",
            "marginTop": "8px",
            "marginBottom": "14px",
        }),
        html.Div([
            # Left column: results — MEMBER 8: owns this section
            # amanda: 2 html.button() added
            html.Div([
                html.Div(id="results_list", style={"marginTop": "16px"}),
                html.Div([
                    html.Button("Start over", id="btn_reset", n_clicks=0, style=btn_reset),
                ], style={"marginTop": "14px"}),
            ], style={
                "flex": "1",
                "minWidth": "420px",  # MEMBER 8: min width of results column
                "position": "relative",
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
                "position": "relative",
            }),
        ], style={
            **card_style,
            "display": "flex",
            "gap": "18px",            # MEMBER 7: gap between results and map columns
            "alignItems": "flex-start",
        }),
        # Loading overlay
        html.Div(id="results_loading_overlay", style={
            "position": "fixed",
            "top": "0",
            "left": "0",
            "right": "0",
            "bottom": "0",
            "backgroundColor": "rgba(0, 0, 0, 0.4)",
            "display": "none",
            "zIndex": "2000",
            "justifyContent": "center",
            "alignItems": "center",
            "flexDirection": "column",
        }, children=[
            html.Div([
                # Spinner using Unicode
                html.Div("⏳", style={
                    "fontSize": "64px",
                    "marginBottom": "24px",
                    "animation": "pulse 1s ease-in-out infinite",
                }),
                html.Div("Generating results...", style={
                    "fontSize": "24px",
                    "fontWeight": "900",
                    "color": "white",
                    "fontFamily": "Arial, sans-serif",
                }),
            ], style={
                "textAlign": "center",
            }),
        ]),
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
    dcc.Store(id="selected_units", data=[]),
    dcc.Store(id="modal_open", data=False),
    dcc.Store(id="selected_recommendation", data=None),  # MEMBER 5: track focused flat (index or None)
    dcc.Store(id="results_lbs_result"),
    *lbs_stores(),


    

    html.Div([
        html.Div([
            # MEMBER 7: title emoji and text
            html.Img(src="/assets/HomeCompass.png", style={
    "height": "175px",
    "marginBottom": "2px"
}),
            html.Div(id="step_indicator"),
        ], style=container_style),
        html.Div(id="main_content", style=container_style),
        html.Div(id="nav_area", style=container_style),
        html.Div(id="results_list", style={"display": "none"}),
        html.Iframe(id="results_map", style={"display": "none"}),
        html.Div(id="results_loading_overlay", style={"display": "none"}),
        html.Div(id="estimate_loading_overlay", style={"display": "none"}, children=[
            html.Div([
                html.Div("⏳", style={
                    "fontSize": "64px",
                    "marginBottom": "24px",
                    "animation": "pulse 1s ease-in-out infinite",
                }),
                html.Div("Estimating price...", style={
                    "fontSize": "24px",
                    "fontWeight": "900",
                    "color": "white",
                    "fontFamily": "Arial, sans-serif",
                }),
            ], style={"textAlign": "center"}),
        ]),
    ], style=base_page_style),

    # Comparison modal — MEMBER 8: Compare Units popup
    html.Div(id="comparison_modal", style={
        "display": "none",
        "position": "fixed",
        "top": "0",
        "left": "0",
        "width": "100%",
        "height": "100%",
        "backgroundColor": "rgba(0, 0, 0, 0.5)",
        "zIndex": "1000",
        "justifyContent": "center",
        "alignItems": "center",
        "overflow": "auto",
    }, children=[
        html.Div([
            html.Div([
                html.Span("Compare Selected Units", style={"fontSize": "28px", "fontWeight": "950"}),
                html.Button("✕", id="btn_close_modal", n_clicks=0, style={
                    "position": "absolute",
                    "top": "20px",
                    "right": "20px",
                    "background": "none",
                    "border": "none",
                    "fontSize": "32px",
                    "cursor": "pointer",
                    "color": "#64748b",
                }),
            ], style={"position": "relative", "marginBottom": "20px"}),
            html.Div(id="comparison_table_container"),
        ], style={
            **card_style,
            "position": "relative",
            "maxWidth": "1000px",
            "maxHeight": "80vh",
            "overflow": "auto",
            "width": "90%",
            "margin": "0 auto",
        }),
    ]),
])

app.validation_layout = html.Div([
    dcc.Store(id="step", data=1),
    dcc.Store(id="sell_payload"),
    dcc.Store(id="sell_geo"),
    dcc.Store(id="sell_pred"),
    dcc.Store(id="prefs_weights"),
    dcc.Store(id="constraints"),
    dcc.Store(id="recs_data"),
    dcc.Store(id="selected_units", data=[]),
    dcc.Store(id="modal_open", data=False),
    dcc.Store(id="selected_recommendation", data=None),
    dcc.Store(id="results_lbs_result"),
    *lbs_stores(),

    html.Div(id="step_indicator"),
    html.Div(id="main_content"),
    html.Div(id="nav_area"),
    html.Button("← Back", id="btn_back"),
    html.Button("Next →", id="btn_next"),
    html.Button("Compare Units", id="btn_compare"),
    html.Div(
        id="comparison_modal",
        children=[
            html.Button("✕", id="btn_close_modal"),
            html.Div(id="comparison_table_container"),
        ],
    ),

    html.Div(id="results_list", style= {"display": "none"}),
    html.Iframe(id="results_map", style= {"display": "none"}),
    html.Div(id="results_loading_overlay", style= {"display": "none"}),

    step_1_estimate(),
    step_2_preferences(),
    step_3_limits(),
    step_4_lbs_page(),
    step_5_results(),
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
    pages = {1: step_1_estimate, 2: step_2_preferences, 3: step_3_limits, 4: step_4_lbs_page, 5: step_5_results,}
    return pages[step](), nav_row(step), step_indicator(step)


# ── Navigation ──

@app.callback(
    Output("step", "data"),
    Input("btn_next", "n_clicks"),
    Input("btn_back", "n_clicks"),
    State("step", "data"),
    State("lbs_result", "data"),
    prevent_initial_call=True,
)
def go_next_back(n_next, n_back, step, lbs_result):
    trig = dash.callback_context.triggered_id
    step = int(step or 1)
    if trig == "btn_next":
        if not validate_lbs_for_navigation(step, lbs_result):
            return step
        return min(step + 1, 5)
    if trig == "btn_back":
        return max(step - 1, 1)
    return step


# ── Step 1: auto-save + geocode ──

def is_valid_sg_postal(postal):
    return bool(re.fullmatch(r"\d{6}", postal))

@app.callback(
    Output("sell_payload", "data"),
    Output("sell_geo", "data"),
    Output("step1_saved_banner", "children"),
    Input("sell_postal", "value"),
    Input("sell_flat_type", "value"),
    Input("sell_area", "value"),
    Input("sell_lease", "value"),
    prevent_initial_call=True,
)

# amanda: fixing autosave postal code between steps. (added the autosave_step1 function)
def autosave_step1(postal, flat_type, area, lease):
    """Auto-save Step 1 form data and geocode the postal code."""
    postal = (postal or "").strip()
    flat_type = flat_type or "4 ROOM"
    
    # Always create the payload with provided data
    payload = {
        "postal": postal,
        "flat_type": flat_type,
        "floor_area_sqm": float(area) if area not in (None, "") else None,
        "remaining_lease": int(lease) if lease not in (None, "") else None,
    }
    
    # Validation checks
    if not postal:
        msg = html.Div("📍 Please enter your postal code.", style=banner_warn)
        return payload, None, msg
    
    if not is_valid_sg_postal(postal):
        msg = html.Div("⚠️ Invalid postal code. Must be 6 digits (e.g., 560123).", style=banner_warn)
        return payload, None, msg
    
    if not area:
        msg = html.Div("⚠️ Please enter your floor area.", style=banner_warn)
        return payload, None, msg
    
    # Try to geocode
    geo = None
    try:
        logger.info(f"[Geocoding] Searching for postal code: {postal}")
        geo = onemap_search(postal)
        if not geo:
            geo = onemap_search(f"Singapore {postal}")
        
        if geo:
            logger.info(f"[Geocoding] Found: {geo}")
            msg = html.Div("✅ Postal code saved. Location found.", style=banner_ok)
            return payload, geo, msg
        else:
            logger.warning(f"[Geocoding] Could not find postal code: {postal}")
            msg = html.Div("⚠️ Postal code saved, but location not found on map (API error). You can still proceed.", style=banner_warn)
            # Return payload even if geocoding fails - let user proceed
            return payload, None, msg
    
    except Exception as e:
        logger.error(f"[Geocoding Error] {str(e)}", exc_info=True)
        msg = html.Div(f"⚠️ Postal code saved. Map lookup failed: check your connection.", style=banner_warn)
        # Return payload even on error - important!
        return payload, None, msg

# ── Step 1: estimate price ──

@app.callback(
    Output("sell_pred", "data"),
    Output("sell_pred_box", "children"),
    Input("btn_estimate", "n_clicks"),
    State("sell_payload", "data"),
    State("sell_geo", "data"),
    prevent_initial_call=True,
)
def estimate_price(n, sell_payload, sell_geo):
    if not sell_payload or not sell_payload.get("postal"):
        return None, ""

    # MEMBER 5: try real backend first, fall back to mock
    pred = safe_post("/predict/sell", sell_payload)
    if not pred:
        pred = mock_predict_price(sell_payload["postal"], sell_payload["flat_type"], sell_payload.get("floor_area_sqm"))

    # MEMBER 7: style price display — large number, confidence range
    address_str = sell_geo.get("address", "") if sell_geo else ""
    box = html.Div([
        html.Div("Estimated selling price", style={"fontSize": "22px", "fontWeight": "950", "opacity": "0.85"}),
        html.Div(f"${pred['price']:,.0f}", style={
            "fontSize": "52px",
            "fontWeight": "950",
        }),
        html.Div(address_str, style={"fontSize": "28px", "opacity": "0.7", "marginTop": "4px"}),
    ], style={"marginTop": "14px"})

    return pred, box


@app.callback(
    Output("estimate_loading_overlay", "style"),
    Input("btn_estimate", "n_clicks"),
    State("step", "data"),
    prevent_initial_call=True,
)
def show_loading_on_estimate(n_clicks, step):
    """Show loading overlay while estimate price is running on Step 1."""
    if int(step or 1) == 1 and n_clicks:
        return {
            "display": "flex",
            "position": "fixed",
            "top": "0",
            "left": "0",
            "right": "0",
            "bottom": "0",
            "backgroundColor": "rgba(0, 0, 0, 0.4)",
            "zIndex": "2000",
            "justifyContent": "center",
            "alignItems": "center",
            "flexDirection": "column",
        }
    return {
        "display": "none",
        "position": "fixed",
        "top": "0",
        "left": "0",
        "right": "0",
        "bottom": "0",
        "backgroundColor": "rgba(0, 0, 0, 0.4)",
        "zIndex": "2000",
        "justifyContent": "center",
        "alignItems": "center",
        "flexDirection": "column",
    }


@app.callback(
    Output("estimate_loading_overlay", "style", allow_duplicate=True),
    Input("sell_pred", "data"),
    State("step", "data"),
    prevent_initial_call=True,
)
def hide_loading_when_estimate_ready(sell_pred, step):
    """Hide estimate loading overlay once estimate callback returns."""
    return {
        "display": "none",
        "position": "fixed",
        "top": "0",
        "left": "0",
        "right": "0",
        "bottom": "0",
        "backgroundColor": "rgba(0, 0, 0, 0.4)",
        "zIndex": "2000",
        "justifyContent": "center",
        "alignItems": "center",
        "flexDirection": "column",
    }


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
        "max_rooms": int(min_rooms or 3),
        "preferred_towns": towns or [],
    }, html.Div("✅ Saved.", style=banner_ok)


# ── Step 4: run results ──
# MEMBER 5: orchestration | MEMBER 8: cards | MEMBER 6: map

@app.callback(
    Output("results_list", "children"),
    Output("results_map", "srcDoc"),
    Output("recs_data", "data"),
    Output("results_lbs_result", "data"),
    Input("main_content", "children"),
    State("step", "data"),
    State("sell_payload", "data"),
    State("sell_geo", "data"),
    State("sell_pred", "data"),
    State("prefs_weights", "data"),
    State("constraints", "data"),
    State("lbs_result", "data"),
    prevent_initial_call=True,
)

def run_results(main_content, step, sell_payload, sell_geo, sell_pred, prefs_w, constraints, lbs_result):
    if int(step or 1) != 5:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    print(f"DEBUG prefs_w: {prefs_w}")
    print(f"DEBUG constraints: {constraints}")
    
    # Validation
    if not lbs_result or not lbs_result.get("ok"):
        return html.Div("Please complete Step 4: LBS details", style=banner_warn), dash.no_update, None, None
    if not sell_payload or not sell_payload.get("postal"):
        return html.Div("Please go back to Step 1 and enter your postal code.", style=banner_warn), dash.no_update, None, None
    if not sell_geo:
        return html.Div("We could not locate your flat. Please check postal code in Step 1.", style=banner_warn), dash.no_update, None, None
    if not prefs_w:
        return html.Div("Please complete Step 2.", style=banner_warn), dash.no_update, None, None
    if not constraints:
        return html.Div("Please complete Step 3.", style=banner_warn), dash.no_update, None, None

    if not sell_pred:
        sell_pred = mock_predict_price(sell_payload["postal"], sell_payload["flat_type"], sell_payload.get("floor_area_sqm"))

    # MEMBER 5: replace mock with real backend call when ready:
    #   payload = {"sell_payload": sell_payload, "sell_pred": sell_pred,
    #              "weights": prefs_w, "constraints": constraints}
    #   recs = safe_post("/recommend", payload)
    #   if not recs:
    #       recs = mock_recommendations(constraints)

    payload = {"constraints": constraints, "weights": prefs_w}
    recs = safe_post("/recommend", payload)
    if not recs:
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
        r["dist_from_home_km"] = round(haversine_km(sell_geo["lat"], sell_geo["lon"], r["lat"], r["lon"]), 2)

    # ── Map — MEMBER 6: customise markers and amenities ──
    points = [
        {"name": f"Your flat ({sell_payload['postal']})", "lat": sell_geo["lat"], "lon": sell_geo["lon"], "color": "#0ea5e9", "rec_index": -1},
    ]
    for i, r in enumerate(recs):
        points.append({
            "name": f"Option #{i+1}: {r['town']} ({r['postal']})",
            "lat": r["lat"], 
            "lon": r["lon"], 
            "color": "#22c55e", 
            "price": r["buy_price"],
            "distance": f"{r['dist_from_home_km']} km",
            "rec_index": i,  # MEMBER 6: index for toggle layer grouping
        })

    # Fetch real amenities from OneMap — MEMBER 6: customize themes
    amenities = []
    base_lat, base_lon = sell_geo["lat"], sell_geo["lon"]
    radius_km = 2.0
    hawker_debug_rows = []
    for idx, r in enumerate(recs):
        rec_lat, rec_lon = r["lat"], r["lon"]
        
        # Track nearest amenity of each type for display in the card
        nearest_amenities = {
            "healthcare": None,
            "hawker": None,
            "transport": None,
            "nature": None,
        }

        # Healthcare (CHAS clinics, sorted by distance)
        healthcare_amenities = get_nearby_amenities("healthcare", rec_lat, rec_lon, radius_km=1.0, limit=9999)
        healthcare_with_dist = []
        for amenity in healthcare_amenities:
            dist = haversine_km(rec_lat, rec_lon, amenity["lat"], amenity["lon"])
            healthcare_with_dist.append({**amenity, "distance_km": dist})
        healthcare_with_dist.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 9999)
        logger.info(f"DEBUG: Found {len(healthcare_with_dist)} clinics for rec #{idx+1} at ({rec_lat}, {rec_lon})")
        
        # Store nearest healthcare for card display
        if healthcare_with_dist:
            nearest = healthcare_with_dist[0]
            nearest_amenities["healthcare"] = {
                "name": nearest["name"],
                "dist_m": int(nearest["distance_km"] * 1000),
            }
        
        for amenity in healthcare_with_dist:
            dist_from_home = amenity["distance_km"]
            dist_str = f"{dist_from_home:.2f} km" if dist_from_home is not None else "N/A"
            amenities.append({
                "name": amenity["name"],
                "lat": amenity["lat"],
                "lon": amenity["lon"],
                "kind": "healthcare",
                "address": amenity.get("address", ""),
                "distance": dist_str,
                "rec_index": idx,  # MEMBER 6: tie amenity to its recommendation
            })

        # Hawker centres & food courts
        hawker_amenities = get_nearby_amenities("hawker", rec_lat, rec_lon, radius_km=1.0, limit=100)
        hawker_with_dist = []
        for amenity in hawker_amenities:
            dist = haversine_km(rec_lat, rec_lon, amenity["lat"], amenity["lon"])
            if dist is not None and dist <= 1.0:
                hawker_with_dist.append({**amenity, "distance_km": dist})
        hawker_with_dist.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 9999)
        logger.info(f"DEBUG: Found {len(hawker_with_dist)} hawker/food courts within 2km for rec #{idx+1} at ({rec_lat}, {rec_lon})")
        
        # Store nearest hawker for card display
        if hawker_with_dist:
            nearest = hawker_with_dist[0]
            nearest_amenities["hawker"] = {
                "name": nearest["name"],
                "dist_m": int(nearest["distance_km"] * 1000),
            }
        
        for amenity in hawker_with_dist:
            dist_from_home = amenity["distance_km"]
            dist_str = f"{dist_from_home:.2f} km" if dist_from_home is not None else "N/A"
            amenities.append({
                "name": amenity["name"],
                "lat": amenity["lat"],
                "lon": amenity["lon"],
                "kind": "hawker / food",
                "address": amenity.get("address", ""),
                "distance": dist_str,
                "rec_index": idx,  # MEMBER 6: tie amenity to its recommendation
            })
            hawker_debug_rows.append([
                amenity["name"], amenity.get("address", ""), amenity["lat"], amenity["lon"], dist_str
            ])

        # Transport (MRT/LRT stations via OneMap search)
        transport_amenities = get_nearby_amenities("transport", rec_lat, rec_lon, radius_km=1.0, limit=100)
        transport_with_dist = []
        for amenity in transport_amenities:
            dist = haversine_km(rec_lat, rec_lon, amenity["lat"], amenity["lon"])
            if dist is not None and dist <= 1.0:
                transport_with_dist.append({**amenity, "distance_km": dist})
        transport_with_dist.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 9999)
        logger.info(f"DEBUG: Found {len(transport_with_dist)} transport points within 2km for rec #{idx+1} at ({rec_lat}, {rec_lon})")
        
        # Store nearest transport for card display
        if transport_with_dist:
            nearest = transport_with_dist[0]
            nearest_amenities["transport"] = {
                "name": nearest["name"],
                "dist_m": int(nearest["distance_km"] * 1000),
            }
        
        for amenity in transport_with_dist:
            dist_from_home = amenity["distance_km"]
            dist_str = f"{dist_from_home:.2f} km" if dist_from_home is not None else "N/A"
            amenities.append({
                "name": amenity["name"],
                "lat": amenity["lat"],
                "lon": amenity["lon"],
                "kind": "transport",
                "address": amenity.get("address", ""),
                "distance": dist_str,
                "rec_index": idx,  # MEMBER 6: tie amenity to its recommendation
            })

        # Nature parks (API, fallback if needed)
        park_amenities = get_nearby_amenities("parks", rec_lat, rec_lon, radius_km=1.0, limit=100)
        park_with_dist = []
        for park in park_amenities:
            dist = haversine_km(rec_lat, rec_lon, park["lat"], park["lon"])
            if dist is not None and dist <= 1.0:
                park_with_dist.append({**park, "distance_km": dist})
        park_with_dist.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 9999)
        logger.info(f"DEBUG: Found {len(park_with_dist)} parks within 2km for rec #{idx+1} at ({rec_lat}, {rec_lon})")
        
        # Store nearest park for card display
        if park_with_dist:
            nearest = park_with_dist[0]
            nearest_amenities["nature"] = {
                "name": nearest["name"],
                "dist_m": int(nearest["distance_km"] * 1000),
            }
        
        for park in park_with_dist:
            dist_from_home = park["distance_km"]
            dist_str = f"{dist_from_home:.2f} km" if dist_from_home is not None else "N/A"
            amenities.append({
                "name": park["name"],
                "lat": park["lat"],
                "lon": park["lon"],
                "kind": "nature",
                "address": park.get("address", ""),
                "distance": dist_str,
                "rec_index": idx,  # MEMBER 6: tie amenity to its recommendation
            })
            hawker_debug_rows.append([
                park["name"], park.get("address", ""), park["lat"], park["lon"], dist_str
            ])

        # NOTE: We intentionally skip healthcare/parks/mrt for now to reduce API load.
        # Store nearest amenities in recommendation for card display
        r["nearest_healthcare"] = nearest_amenities["healthcare"]
        r["nearest_hawker"] = nearest_amenities["hawker"]
        r["nearest_transport"] = nearest_amenities["transport"]
        r["nearest_nature"] = nearest_amenities["nature"]

    # ── Result cards — MEMBER 8: customise everything in this block ──
    # (built AFTER amenity fetching so nearest_* data is available)
    cards = []
    for i, r in enumerate(recs, start=1):
        pg_url = r.get("listing_url", "https://www.propertyguru.com.sg")

        valuation = r.get("valuation_label", "N/A")
        predicted = r.get("predicted_price", 0)
        actual = r.get("buy_price", 0)
        diff = actual - predicted
        direction = "above" if diff > 0 else "below"
        info_tooltip = f"Our model estimates this flat's value at ${predicted:,.0f}. The listed price is ${actual:,.0f}, which is {direction} our estimate."
        valuation_color = {"Fair Value": "#22c55e", "Above Market": "#f97316", "Below Market": "#0ea5e9"}.get(valuation, "#94a3b8")
        valuation_emoji = {"Fair Value": "✅ Good Value", "Above Market": "⚠️ Above Market", "Below Market": "💰 Below Market"}.get(valuation, valuation)

        # Build amenity description strings
        hc = r.get("nearest_healthcare")
        hw = r.get("nearest_hawker")
        tr = r.get("nearest_transport")
        na = r.get("nearest_nature")
        health_str = f"{hc['name']} ~{hc['dist_m']}m" if hc else "No healthcare within 1km"
        hawker_str = f"{hw['name']} ~{hw['dist_m']}m" if hw else "No hawker within 1km"
        transport_str = f"{tr['name']} ~{tr['dist_m']}m" if tr else "No transport within 1km"
        nature_str = f"{na['name']} ~{na['dist_m']}m" if na else "No nature within 1km"

        cards.append(html.Div([
            # MEMBER 8: selection checkbox
            dcc.Checklist(
                id={"type": "unit_checkbox", "index": i - 1},
                options=[{"label": "Compare this unit", "value": i - 1}],
                value=[],
                style={
                    "marginBottom": "12px",
                    "transform": "scale(1.4)",
                    "transformOrigin": "left",
                    "display": "inline-block",
                },
                labelStyle={
                    "fontSize": "18px",
                    "fontWeight": "700",
                    "marginLeft": "4px",
                    "cursor": "pointer",
                },
                inline=True,
            ),
             html.Div([
    html.Span(valuation_emoji, style={
        "display": "inline-flex",
        "alignItems": "center",
        "padding": "6px 16px",
        "borderRadius": "999px",
        "backgroundColor": valuation_color,
        "color": "white",
        "fontSize": "16px",
        "fontWeight": "800",
        "marginRight": "10px",
    }),
    html.Span(f"~${abs(diff):,.0f} {direction} market estimate", style={
        "fontSize": "16px",
        "fontWeight": "700",
        "color": valuation_color,
        "marginRight": "6px",
    }),
    html.Span("ⓘ", id=f"valuation_info_{i}", style={
        "cursor": "pointer",
        "fontSize": "16px",
        "color": "#94a3b8",
        "fontWeight": "900",
    }),
    dbc.Tooltip(
        info_tooltip,
        target=f"valuation_info_{i}",
        placement="top",
        style={
            "backgroundColor": "white",
            "color": "#1f2937",
            "borderRadius": "8px",
            "boxShadow": "0 4px 12px rgba(0,0,0,0.1)",
            "padding": "12px 14px",
            "fontSize": "14px",
            "fontWeight": "600",
            "maxWidth": "300px",
            "lineHeight": "1.5",
        },
    ),
], style={
    "display": "flex",
    "alignItems": "center",
    "marginBottom": "12px",
    "flexWrap": "wrap",
    "gap": "4px",
}),
            # MEMBER 8: card title (address only)
            html.Div(f"#{i} • {r.get('address_from_url', r['town'])}", style={
                "fontSize": "28px",           # MEMBER 8: title size
                "fontWeight": "950",
                "lineHeight": "1.2",
            }),
            # MEMBER 8: cash unlocked
            html.Div(f"Cash unlocked (estimate): ${r['cash_unlocked']:,.0f}", style={
                "fontSize": "22px", "fontWeight": "900", "lineHeight": "1.6",
            }),
            # MEMBER 8: buy price (always visible)
            html.Div(f"Buy price (estimate): ${r['buy_price']:,.0f}", style={
                "fontSize": "22px", "fontWeight": "900", "lineHeight": "1.5", "marginTop": "4px",
            }),
            # MEMBER 8: dropdown for additional details
            html.Details([
                html.Summary("Nearby Amenities ▼", style={
                    "fontSize": "20px",
                    "fontWeight": "900",
                    "cursor": "pointer",
                    "marginTop": "8px",
                    "display": "inline-block",
                    "padding": "6px 12px",
                    "border": "1.5px solid #94a3b8",
                    "borderRadius": "10px",
                    "backgroundColor": "rgba(148, 163, 184, 0.1)",
                }),
                html.Div([
                    html.Div(f"Distance from your flat: {r['dist_from_home_km']} km", style={
                        "fontSize": "18px", "fontWeight": "900", "opacity": "0.88", "lineHeight": "1.6", "marginTop": "10px",
                    }),
                    html.Div("Nearest Amenities within 1km:", style={
                        "fontSize": "18px", "fontWeight": "850", "opacity": "0.85",
                        "marginTop": "6px",
                    }),
                    html.Ul([
                        html.Li(f"🏥 {health_str}", style={"fontSize": "16px", "fontWeight": "800"}),
                        html.Li(f"🍜 {hawker_str}", style={"fontSize": "16px", "fontWeight": "800"}),
                        html.Li(f"🚆 {transport_str}", style={"fontSize": "16px", "fontWeight": "800"}),
                        html.Li(f"🌳 {nature_str}", style={"fontSize": "16px", "fontWeight": "800"}),
                    ], style={"margin": "4px 0 0 20px", "padding": "0", "opacity": "0.85"}),
                ]),
            ]),
            html.A("🔎 Click here to view the listing on PropertyGuru", href=pg_url, target="_blank", style={
                "display": "inline-block",
                "marginTop": "10px",
                "fontSize": "18px",           # MEMBER 8: link size
                "fontWeight": "950",
                "textDecoration": "none",
                "color": "#0ea5e9",           # MEMBER 8: link colour
            }),
        ], style={**card_style, "marginTop": "14px"}))
    if lbs_result and lbs_result.get("ok"):
        cards.append(build_lbs_result_card(lbs_result, card_style))
    map_doc = leaflet_map_html(sell_geo["lat"], sell_geo["lon"], points, amenities, zoom=14)

    return html.Div([*cards]), map_doc, recs, lbs_result


# ── Loading indicator for Step 5 ──

@app.callback(
    Output("results_loading_overlay", "style"),
    Input("main_content", "children"),
    State("step", "data"),
    prevent_initial_call=True,
)
def show_loading_on_step5(main_content, step):
    """Show loading overlay when entering Step 5."""
    if int(step or 1) == 5:
        return {"display": "flex", "position": "fixed", "top": "0", "left": "0", "right": "0", "bottom": "0", "backgroundColor": "rgba(0, 0, 0, 0.4)", "zIndex": "2000", "justifyContent": "center", "alignItems": "center", "flexDirection": "column"}
    return {"display": "none", "position": "fixed", "top": "0", "left": "0", "right": "0", "bottom": "0", "backgroundColor": "rgba(0, 0, 0, 0.4)", "zIndex": "2000", "justifyContent": "center", "alignItems": "center", "flexDirection": "column"}


@app.callback(
    Output("results_loading_overlay", "style", allow_duplicate=True),
    Input("results_list", "children"),
    State("step", "data"),
    prevent_initial_call=True,
)
def hide_loading_when_results_ready(results_list_children, step):
    """Hide loading overlay once results are populated."""
    if int(step or 1) != 5:
        return {"display": "none", "position": "fixed", "top": "0", "left": "0", "right": "0", "bottom": "0", "backgroundColor": "rgba(0, 0, 0, 0.4)", "zIndex": "2000", "justifyContent": "center", "alignItems": "center", "flexDirection": "column"}
    
    # Hide loading if results_list has content
    if results_list_children:
        return {"display": "none", "position": "fixed", "top": "0", "left": "0", "right": "0", "bottom": "0", "backgroundColor": "rgba(0, 0, 0, 0.4)", "zIndex": "2000", "justifyContent": "center", "alignItems": "center", "flexDirection": "column"}
    
    # Show loading if no content yet
    return {"display": "flex", "position": "fixed", "top": "0", "left": "0", "right": "0", "bottom": "0", "backgroundColor": "rgba(0, 0, 0, 0.4)", "zIndex": "2000", "justifyContent": "center", "alignItems": "center", "flexDirection": "column"}


# ── Reset ──

@app.callback(
    Output("step", "data", allow_duplicate=True),
    Output("sell_payload", "data", allow_duplicate=True),
    Output("sell_geo", "data", allow_duplicate=True),
    Output("sell_pred", "data", allow_duplicate=True),
    Output("prefs_weights", "data", allow_duplicate=True),
    Output("constraints", "data", allow_duplicate=True),
    Output("recs_data", "data", allow_duplicate=True),
    Output("lbs_inputs", "data", allow_duplicate=True),
    Output("lbs_result", "data", allow_duplicate=True),
    Output("results_lbs_result", "data", allow_duplicate=True),
    Input("btn_reset", "n_clicks"),
    prevent_initial_call=True,
)
def reset_all(n):
    return 1, None, None, None, None, None, None, None, None, None


# amanda: added this whole compare units segment for the comparison selection and panels
# ── Compare Units — MEMBER 8: comparison logic ──

@app.callback(
    Output("results_map", "srcDoc", allow_duplicate=True),
    Input("selected_recommendation", "data"),
    State("recs_data", "data"),
    State("sell_geo", "data"),
    State("sell_payload", "data"),
    prevent_initial_call=True,
)
def update_map_for_focused_flat(focused_index, recs_data, sell_geo, sell_payload):
    """
    When a recommendation is focused, regenerate the map to show:
    - Current flat (your home)
    - Selected recommendation flat
    - Amenities only around the selected flat
    MEMBER 6: map updates based on focus | MEMBER 5: callback logic
    """
    
    if focused_index is None or not recs_data or not sell_geo or not sell_payload:
        return dash.no_update
    
    if focused_index >= len(recs_data):
        return dash.no_update
    
    focused_rec = recs_data[focused_index]
    
    # ── Points: your flat + focused recommendation ──
    points = [
        {"name": f"Your flat ({sell_payload['postal']})", "lat": sell_geo["lat"], "lon": sell_geo["lon"], "color": "#0ea5e9", "rec_index": -1},
        {
            "name": f"Option #{focused_index + 1}: {focused_rec['town']} ({focused_rec['postal']})",
            "lat": focused_rec["lat"],
            "lon": focused_rec["lon"],
            "color": "#22c55e",
            "price": focused_rec["buy_price"],
            "distance": f"{focused_rec['dist_from_home_km']} km",
            "rec_index": 0,  # Only one recommendation shown when focused
        }
    ]
    
    # ── Amenities: only around focused flat ──
    amenities = []
    rec_lat, rec_lon = focused_rec["lat"], focused_rec["lon"]
    
    logger.info(f"[Focus] Generating amenities for rec #{focused_index + 1} at ({rec_lat}, {rec_lon})")
    
    # Healthcare (CHAS clinics)
    healthcare_amenities = get_nearby_amenities("healthcare", rec_lat, rec_lon, radius_km=1.0, limit=9999)
    healthcare_with_dist = []
    for amenity in healthcare_amenities:
        dist = haversine_km(rec_lat, rec_lon, amenity["lat"], amenity["lon"])
        healthcare_with_dist.append({**amenity, "distance_km": dist})
    healthcare_with_dist.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 9999)
    for amenity in healthcare_with_dist:
        dist_from_home = amenity["distance_km"]
        dist_str = f"{dist_from_home:.2f} km" if dist_from_home is not None else "N/A"
        amenities.append({
            "name": amenity["name"],
            "lat": amenity["lat"],
            "lon": amenity["lon"],
            "kind": "healthcare",
            "address": amenity.get("address", ""),
            "distance": dist_str,
            "rec_index": 0,  # Focused flat index
        })
    
    # Hawker centres & food courts
    hawker_amenities = get_nearby_amenities("hawker", rec_lat, rec_lon, radius_km=1.0, limit=100)
    hawker_with_dist = []
    for amenity in hawker_amenities:
        dist = haversine_km(rec_lat, rec_lon, amenity["lat"], amenity["lon"])
        if dist is not None and dist <= 1.0:
            hawker_with_dist.append({**amenity, "distance_km": dist})
    hawker_with_dist.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 9999)
    for amenity in hawker_with_dist:
        dist_from_home = amenity["distance_km"]
        dist_str = f"{dist_from_home:.2f} km" if dist_from_home is not None else "N/A"
        amenities.append({
            "name": amenity["name"],
            "lat": amenity["lat"],
            "lon": amenity["lon"],
            "kind": "hawker / food",
            "address": amenity.get("address", ""),
            "distance": dist_str,
            "rec_index": 0,  # Focused flat index
        })
    
    # Transport (MRT/LRT)
    transport_amenities = get_nearby_amenities("transport", rec_lat, rec_lon, radius_km=1.0, limit=100)
    transport_with_dist = []
    for amenity in transport_amenities:
        dist = haversine_km(rec_lat, rec_lon, amenity["lat"], amenity["lon"])
        if dist is not None and dist <= 1.0:
            transport_with_dist.append({**amenity, "distance_km": dist})
    transport_with_dist.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 9999)
    for amenity in transport_with_dist:
        dist_from_home = amenity["distance_km"]
        dist_str = f"{dist_from_home:.2f} km" if dist_from_home is not None else "N/A"
        amenities.append({
            "name": amenity["name"],
            "lat": amenity["lat"],
            "lon": amenity["lon"],
            "kind": "transport",
            "address": amenity.get("address", ""),
            "distance": dist_str,
            "rec_index": 0,  # Focused flat index
        })
    
    # Nature parks
    park_amenities = get_nearby_amenities("parks", rec_lat, rec_lon, radius_km=1.0, limit=100)
    park_with_dist = []
    for park in park_amenities:
        dist = haversine_km(rec_lat, rec_lon, park["lat"], park["lon"])
        if dist is not None and dist <= 1.0:
            park_with_dist.append({**park, "distance_km": dist})
    park_with_dist.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 9999)
    for park in park_with_dist:
        dist_from_home = park["distance_km"]
        dist_str = f"{dist_from_home:.2f} km" if dist_from_home is not None else "N/A"
        amenities.append({
            "name": park["name"],
            "lat": park["lat"],
            "lon": park["lon"],
            "kind": "nature",
            "address": park.get("address", ""),
            "distance": dist_str,
            "rec_index": 0,  # Focused flat index
        })
    
    logger.info(f"[Focus] Found {len(amenities)} total amenities for focused flat")
    
    # Generate and return the updated map
    map_doc = leaflet_map_html(rec_lat, rec_lon, points, amenities, zoom=14)
    return map_doc


@app.callback(
    Output("selected_units", "data"),
    Input({"type": "unit_checkbox", "index": dash.ALL}, "value"),
    prevent_initial_call=True,
)
def update_selected_units(checkbox_values):
    """Track which units are selected for comparison"""
    if not checkbox_values:
        return []
    # checkbox_values is a list of lists, where each inner list contains the selected values
    selected_indices = []
    for values in checkbox_values:
        if values:
            selected_indices.extend(values)
    return selected_indices


@app.callback(
    Output("modal_open", "data"),
    Input("step", "data"),
    Input("recs_data", "data"),
    Input("btn_compare", "n_clicks"),
    Input("btn_close_modal", "n_clicks"),
    State("selected_units", "data"),
    prevent_initial_call=True,
)
def control_comparison_modal(step, recs_data, n_compare, n_close, selected_indices):
    trig = dash.callback_context.triggered_id

    # Always close modal when navigating steps or regenerating results
    if trig in ["step", "recs_data"]:
        return False

    if trig == "btn_close_modal":
        return False

    if trig == "btn_compare":
        # Only open if user has selected at least one unit
        return bool(selected_indices)

    return dash.no_update

@app.callback(
    Output("comparison_modal", "style"),
    Output("comparison_table_container", "children"),
    Input("modal_open", "data"),
    State("selected_units", "data"),
    State("recs_data", "data"),
    State("results_lbs_result", "data"),
    prevent_initial_call=True,
)
def render_comparison_modal(is_open, selected_indices, recs_data, results_lbs_result):
    """Render comparison modal content."""

    modal_style_hidden = {
        "display": "none",
        "position": "fixed",
        "top": "0",
        "left": "0",
        "width": "100%",
        "height": "100%",
        "backgroundColor": "rgba(0, 0, 0, 0.5)",
        "zIndex": "1000",
        "justifyContent": "center",
        "alignItems": "center",
        "overflow": "auto",
    }

    modal_style_open = {
        "display": "flex",
        "position": "fixed",
        "top": "0",
        "left": "0",
        "width": "100%",
        "height": "100%",
        "backgroundColor": "rgba(0, 0, 0, 0.5)",
        "zIndex": "1000",
        "justifyContent": "center",
        "alignItems": "center",
        "overflow": "auto",
    }

    if not is_open:
        return modal_style_hidden, dash.no_update

    try:
        if not selected_indices:
            return modal_style_open, html.Div(
                "Please select at least one unit to compare.",
                style={"fontSize": "16px", "color": "#ef4444"},
            )

        # normalize selected indices
        normalized_indices = []
        for raw_idx in selected_indices:
            try:
                idx = int(raw_idx)
            except (TypeError, ValueError):
                continue
            if idx not in normalized_indices:
                normalized_indices.append(idx)

        selected_items = []
        for idx in normalized_indices:
            if recs_data and 0 <= idx < len(recs_data):
                rec = recs_data[idx]
                selected_items.append({
                    "label": f"Option #{idx + 1}",
                    "data": rec,
                })

        if not selected_items:
            return modal_style_open, html.Div(
                "No valid units selected. Please try again.",
                style={"fontSize": "16px", "color": "#ef4444"},
            )

        print("COMPARE MODAL results_lbs_result:", results_lbs_result)

        if not results_lbs_result or not isinstance(results_lbs_result, dict) or not results_lbs_result.get("ok"):
            return modal_style_open, html.Div(
                "LBS result is missing from the Results snapshot. Please rerun results.",
                style={"fontSize": "16px", "color": "#ef4444"},
            )

        net_lbs_value = results_lbs_result.get("net_lbs")

        if net_lbs_value is None:
            return modal_style_open, html.Div(
                "LBS value could not be read from the Results snapshot. Please rerun results.",
                style={"fontSize": "16px", "color": "#ef4444"},
            )

        # ----------------------------
        # detailed comparison table
        # selected flats only
        # ----------------------------
        headers = ["Metric", *[item["label"] for item in selected_items]]

        metrics = [
            ("Town", "town", None),
            ("Rooms", "rooms", None),
            ("Buy Price (est.)", "buy_price", "min"),
            ("Cash Unlocked (est.)", "cash_unlocked", "max"),
            ("Distance from Your Flat", "dist_from_home_km", "min"),
            ("Nearest Healthcare", "nearest_healthcare_name", None),
            ("Nearest Hawker", "nearest_hawker_name", None),
            ("Nearest Transport", "nearest_transport_name", None),
            ("Nearest Park", "nearest_nature_name", None),
            ("MRT Distance (approx)", "mrt_dist_km", "min"),
        ]

        def _metric_value(rec, metric_key):
            if metric_key == "nearest_healthcare_name":
                return rec.get("nearest_healthcare", None)
            if metric_key == "nearest_hawker_name":
                return rec.get("nearest_hawker", None)
            if metric_key == "nearest_transport_name":
                return rec.get("nearest_transport", None)
            if metric_key == "nearest_nature_name":
                return rec.get("nearest_nature", None)
            return rec.get(metric_key, None)

        def format_value(metric_key, value):
            if metric_key in ["buy_price", "cash_unlocked"]:
                return f"${value:,.0f}" if isinstance(value, (int, float)) else "N/A"
            if metric_key in ["dist_from_home_km", "mrt_dist_km"]:
                return f"{value:.2f} km" if isinstance(value, (int, float)) else "N/A"
            if metric_key in [
                "nearest_healthcare_name",
                "nearest_hawker_name",
                "nearest_transport_name",
                "nearest_nature_name",
            ]:
                if value and isinstance(value, dict) and "name" in value and "dist_m" in value:
                    return f"{value['name']} (~{value['dist_m']}m)"
                return "N/A"
            return str(value) if value not in (None, "") else "N/A"

        metric_perf = {}
        for _, metric_key, prefer in metrics:
            values = [_metric_value(item["data"], metric_key) for item in selected_items]
            numeric_pairs = [(j, v) for j, v in enumerate(values) if isinstance(v, (int, float))]
            if prefer and numeric_pairs:
                if prefer == "max":
                    best_idx = max(numeric_pairs, key=lambda pair: pair[1])[0]
                    worst_idx = min(numeric_pairs, key=lambda pair: pair[1])[0]
                else:
                    best_idx = min(numeric_pairs, key=lambda pair: pair[1])[0]
                    worst_idx = max(numeric_pairs, key=lambda pair: pair[1])[0]
                metric_perf[metric_key] = {"best": best_idx, "worst": worst_idx}
            else:
                metric_perf[metric_key] = None

        rows = []
        for metric_label, metric_key, _ in metrics:
            row = [
                html.Td(
                    metric_label,
                    style={
                        "fontWeight": "700",
                        "padding": "10px",
                        "borderRight": "1px solid #e2e8f0",
                    },
                )
            ]

            for idx, item in enumerate(selected_items):
                value = _metric_value(item["data"], metric_key)
                display = format_value(metric_key, value)
                cell_style = {"padding": "10px", "textAlign": "center"}

                perf = metric_perf.get(metric_key)
                if perf and isinstance(value, (int, float)):
                    if idx == perf["best"]:
                        cell_style.update({
                            "backgroundColor": "#dcfce7",
                            "color": "#166534",
                            "fontWeight": "700",
                        })
                    elif idx == perf["worst"]:
                        cell_style.update({
                            "backgroundColor": "#fee2e2",
                            "color": "#991b1b",
                        })

                row.append(html.Td(display, style=cell_style))

            rows.append(html.Tr(row))

        detailed_table = html.Table(
            [
                html.Thead(
                    html.Tr(
                        [
                            html.Th(
                                h,
                                style={
                                    "padding": "12px",
                                    "textAlign": "center",
                                    "fontWeight": "700",
                                    "borderBottom": "2px solid #0ea5e9",
                                },
                            )
                            for h in headers
                        ]
                    )
                ),
                html.Tbody(rows),
            ],
            style={
                "width": "100%",
                "borderCollapse": "collapse",
                "marginTop": "20px",
                "fontSize": "16px",
            },
        )

        # ----------------------------
        # summary section
        # selected flats + LBS stay
        # ----------------------------
        summary_options = []

        for item in selected_items:
            rec = item["data"]
            summary_options.append({
                "label": item["label"],
                "immediate_cash": rec.get("cash_unlocked"),
                "change_of_home": "Yes",
                "distance_from_current_flat": rec.get("dist_from_home_km"),
            })

        summary_options.append({
            "label": "LBS (Stay)",
            "immediate_cash": float(net_lbs_value or 0),
            "change_of_home": "No",
            "distance_from_current_flat": 0.0,
        })

        def fmt_money(x):
            return f"${x:,.0f}" if isinstance(x, (int, float)) else "N/A"

        def fmt_km(x):
            return f"{x:.2f} km" if isinstance(x, (int, float)) else "N/A"

        numeric_cash_values = [
            opt["immediate_cash"]
            for opt in summary_options
            if isinstance(opt["immediate_cash"], (int, float))
        ]
        max_cash = max(numeric_cash_values) if numeric_cash_values else None

        summary_rows = [
            html.Tr(
                [html.Td("Immediate Cash", style={"fontWeight": "700", "padding": "10px"})] +
                [
                    html.Td(
                        fmt_money(opt["immediate_cash"]),
                        style={
                            "padding": "10px",
                            "textAlign": "center",
                            "backgroundColor": "#dcfce7" if opt["immediate_cash"] == max_cash else "white",
                            "fontWeight": "700" if opt["immediate_cash"] == max_cash else "400",
                            "color": "#166534" if opt["immediate_cash"] == max_cash else "#111827",
                        }
                    )
                    for opt in summary_options
                ]
            ),
            html.Tr(
                [html.Td("Change of Home", style={"fontWeight": "700", "padding": "10px"})] +
                [
                    html.Td(opt["change_of_home"], style={"padding": "10px", "textAlign": "center"})
                    for opt in summary_options
                ]
            ),
            html.Tr(
                [html.Td("Distance from Current Flat", style={"fontWeight": "700", "padding": "10px"})] +
                [
                    html.Td(
                        fmt_km(opt["distance_from_current_flat"]),
                        style={"padding": "10px", "textAlign": "center"}
                    )
                    for opt in summary_options
                ]
            ),
        ]

        summary_table = html.Div([
            html.Div("At-a-Glance Summary", style={"fontSize": "22px", "fontWeight": "900", "marginBottom": "10px"}),
            html.Table(
                [
                    html.Thead(
                        html.Tr(
                            [html.Th("Outcome", style={"padding": "10px", "textAlign": "left"})] +
                            [html.Th(opt["label"], style={"padding": "10px", "textAlign": "center"}) for opt in summary_options]
                        )
                    ),
                    html.Tbody(summary_rows),
                ],
                style={
                    "width": "100%",
                    "borderCollapse": "collapse",
                    "fontSize": "15px",
                    "border": "1px solid #d1d5db",
                    "borderRadius": "10px",
                    "overflow": "hidden",
                    "backgroundColor": "white",
                },
            ),
        ], style={
            "flex": "1.4",
            "padding": "16px",
            "border": "1px solid #d1d5db",
            "borderRadius": "14px",
            "backgroundColor": "white",
        })

        best_cash_option = max(
            summary_options,
            key=lambda x: x["immediate_cash"] if isinstance(x["immediate_cash"], (int, float)) else -1
        )

        insight_box = html.Div([
            html.Div("Recommendation Insight", style={"fontSize": "22px", "fontWeight": "900", "marginBottom": "10px"}),
            html.Ul([
                html.Li(
                    f"{best_cash_option['label']} provides the highest immediate cash unlocked.",
                    style={"marginBottom": "10px", "fontSize": "16px"}
                ),
                html.Li(
                    "Use the detailed comparison above to weigh amenities and distance against cash outcomes.",
                    style={"fontSize": "16px"}
                ),
            ], style={"paddingLeft": "20px", "margin": "0"}),
        ], style={
            "flex": "1",
            "padding": "16px",
            "border": "1px solid #d1d5db",
            "borderRadius": "14px",
            "backgroundColor": "white",
        })

        summary_section = html.Div(
            [summary_table, insight_box],
            style={
                "display": "flex",
                "gap": "16px",
                "marginTop": "24px",
                "alignItems": "stretch",
            },
        )

        logger.info(
            "[Compare Modal FINAL] selected=%s | lbs_net=%s | headers=%s",
            normalized_indices,
            net_lbs_value,
            headers,
        )

        return modal_style_open, html.Div([
            detailed_table,
            summary_section,
        ])

    except Exception as exc:
        logger.exception("[Compare Modal] Crashed while rendering comparison table")
        return modal_style_open, html.Div(
            f"Comparison table error: {exc}",
            style={"fontSize": "16px", "color": "#ef4444"},
        )


# ============================================================================
# RUN
# ============================================================================
import os
port = int(os.environ.get("PORT", 8050))
app.run(host="0.0.0.0", port=port, debug=False)

