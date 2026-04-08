"""
To run locally:
pip install -r ../requirements.txt 
python app.py
Open http://127.0.0.1:8050

"""
# 
# Imports and app configuration
# 

import csv
import io
import json as json_module
import logging
import os
import re
import time

import dash
import dash_bootstrap_components as dbc
import requests
from dash import Dash, Input, Output, State, dcc, html

logging.basicConfig(level=logging.DEBUG, force=True)
logger = logging.getLogger("amenity_debug")
logger.setLevel(logging.DEBUG)
logger.debug("[Startup] amenity_debug logger is active.")

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

# 
# Backend and API utilities
# 

# 
# Map rendering helpers
# 

def leaflet_map_html(center_lat, center_lon, points, amenities, zoom=14):
    def js_point(p):
        return {
            "name": p["name"], 
            "lat": p["lat"], 
            "lon": p["lon"], 
            "color": p.get("color", "#0ea5e9"),
            "price": p.get("price", "N/A"),
            "distance": p.get("distance", "N/A"),
            "rec_index": p.get("rec_index", -1),
        }

    def js_am(a):
        return {
            "name": a.get("name") or "Unnamed amenity", 
            "lat": a["lat"], 
            "lon": a["lon"], 
            "kind": a.get("kind", "Amenity"),
            "address": a.get("address"),  # None for transport amenities
            "distance": a.get("distance", "N/A"),
            "rec_index": a.get("rec_index", -1),
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
    /* Popup styling */
    .leaflet-popup-content {{ font-size: 16px; font-weight: 700; }}
    /* Legend styling */
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
  <!-- Legend and layer controls -->
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

    // Base tile layer
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 19, attribution: '&copy; OpenStreetMap'
    }}).addTo(map);

    const points = {points_js};
    const amenities = {amen_js};
    
    // Amenity layers are grouped by recommendation and amenity type.
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
    
    //Separate marker layer for each recommended flat.
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

    //Add markers for points (your flat n recommendations)
    points.forEach((p, index) => {{
      const icon = index === 0 ? homeIcon : recommendIcon;
    const marker = L.marker([p.lat, p.lon], {{ icon: icon, opacity: 1.0 }}).bindPopup(`<b>${{p.name}}</b><br>Estimated price: $${{p.price}}<br>Distance from your flat: ${{p.distance}}`);
      
      // Keep the current flat always visible; recommendations live in toggleable layers.
      if (p.rec_index === -1) {{
        marker.addTo(map);  // Your flat always visible
      }} else {{
        marker.addTo(recLayers[p.rec_index]);  // Recommendation on layer
      }}
    }});

    //Add markers for amenities 
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
      
      //Amenities attached to corresponding recommendation layer.
      if (a.rec_index >= 0 && recAmenityLayers[a.rec_index]) {{
        const layer = recAmenityLayers[a.rec_index][a.kind];
        if (layer) {{
          marker.addTo(layer);
        }}
      }}
    }});
    
    //Build recommendation toggles from the plotted points.
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

    //Event listeners for recommendation toggles
    //When a recommendation is toggled, can toggle both the marker and respective amenities
    document.querySelectorAll('#layer-controls input[data-rec-index]').forEach(cb => {{
        cb.addEventListener('change', (event) => {{
            const recIdx = parseInt(event.target.getAttribute('data-rec-index'));
            const recMarkerLayer = recLayers[recIdx];
            const recAmenities = recAmenityLayers[recIdx];
            
            if (event.target.checked) {{
                // show flat marker + amenities (if toggle enabled)
                if (recMarkerLayer && !map.hasLayer(recMarkerLayer)) {{
                    recMarkerLayer.addTo(map);
                }}
                // Add amenity layer if global toggle is enabled
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
                // hide flat marker + all amenities
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
    // can toggle amenities for all recommendations
    document.querySelectorAll('#layer-controls input[data-kind]').forEach(cb => {{
        cb.addEventListener('change', (event) => {{
            const amenityKind = event.target.getAttribute('data-kind');
            
            //Toggle amenity type for all the recommendations
            uniqueRecIndices.forEach(recIdx => {{
                const amenityLayer = recAmenityLayers[recIdx][amenityKind];
                if (!amenityLayer) return;
                
                if (event.target.checked) {{
                    // show it if the recommendation is visible
                    const recMarkerLayer = recLayers[recIdx];
                    if (map.hasLayer(recMarkerLayer) && !map.hasLayer(amenityLayer)) {{
                        amenityLayer.addTo(map);
                    }}
                }} else {{
                    // hide it everywhere
                    if (map.hasLayer(amenityLayer)) {{
                        map.removeLayer(amenityLayer);
                    }}
                }}
            }});
        }});
    }});

    //give more breathing room
    const all = points.map(p => [p.lat, p.lon]).concat(amenities.map(a => [a.lat, a.lon]));
    if (all.length > 1) {{ map.fitBounds(L.latLngBounds(all).pad(0.18)); }}
  </script>
</body>
</html>
"""

# 
# Wizard UI implementation at top of page
#

def step_indicator(step):
    steps = STEP_META
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
                    "width": "140px",
                }),
            ], style={"display": "flex", "flexDirection": "column", "alignItems": "center"})
        )
        if i < len(steps):
            chips.append(html.Div(style={
                "height": "4px", "flex": "1",
                "background": "rgba(15,23,42,0.12)",
                "borderRadius": "999px",
                "margin": "0 12px",
                "alignSelf": "center",
            }))
    return html.Div(chips, style={"display": "flex", "alignItems": "center", "marginTop": "16px"})


# show corresponding step once render next or the back button
def nav_row(step):
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

#
# Step by step architecture of app
#

# Step 1 Estimate your flat

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

# Step 2 on what matters to you, which is just sliders for the 4 key amenities 

def step_2_preferences():
    slider_style = {"padding": "8px 6px 4px 6px"}
    label_with_sub_style = {"marginBottom": "18px"}
    return html.Div([
        html.Div("Step 2: What matters to you?", style={"fontSize": "36px", "fontWeight": "950"}),
        html.Div("Move each slider to show how important each amenity is to you. 1 = Not important, 10 = Very important.", style={
            "fontSize": "20px", "fontWeight": "600", "opacity": "0.7", "marginTop": "8px", "marginBottom": "20px"
        }),
        html.Div([
            # Healthcare
            html.Div([
                html.Div("🏥  Clinics and healthcare", style={**label_style, "fontSize": "26px"}),
                html.Div("How important is it to have clinics or hospitals close to home?", style={
                    "fontSize": "17px", "opacity": "0.65", "marginBottom": "6px", "fontWeight": "600"
                }),
                html.Div(dcc.Slider(id="pref_healthcare", min=1, max=10, step=1, value=8,
                                    marks={i: str(i) for i in range(1, 11)}), style=slider_style),
            ], style=label_with_sub_style),
            html.Hr(style={"margin": "10px 0 20px 0"}),

            # Transport
            html.Div([
                html.Div("🚇  MRT", style={**label_style, "fontSize": "26px"}),
                html.Div("How important is it to have an MRT station nearby?", style={
                    "fontSize": "17px", "opacity": "0.65", "marginBottom": "6px", "fontWeight": "600"
                }),
                html.Div(dcc.Slider(id="pref_transport", min=1, max=10, step=1, value=7,
                                    marks={i: str(i) for i in range(1, 11)}), style=slider_style),
            ], style=label_with_sub_style),
            html.Hr(style={"margin": "10px 0 20px 0"}),

            # Hawker
            html.Div([
                html.Div("🍜  Hawker centres", style={**label_style, "fontSize": "26px"}),
                html.Div("How important is it to have hawker centres nearby?", style={
                    "fontSize": "17px", "opacity": "0.65", "marginBottom": "6px", "fontWeight": "600"
                }),
                html.Div(dcc.Slider(id="pref_hawker", min=1, max=10, step=1, value=6,
                                    marks={i: str(i) for i in range(1, 11)}), style=slider_style),
            ], style=label_with_sub_style),
            html.Hr(style={"margin": "10px 0 20px 0"}),

            # Parks
            html.Div([
                html.Div("🌳  Parks and green spaces", style={**label_style, "fontSize": "26px"}),
                html.Div("How important is it to have parks or gardens nearby?", style={
                    "fontSize": "17px", "opacity": "0.65", "marginBottom": "6px", "fontWeight": "600"
                }),
                html.Div(dcc.Slider(id="pref_recreation", min=1, max=10, step=1, value=6,
                                    marks={i: str(i) for i in range(1, 11)}), style=slider_style),
            ], style=label_with_sub_style),

            html.Div(id="pref_saved_banner"),
        ], style=card_style),
    ])

# Step 3: set the limits for /recommend (budget -> shd change from min to max, changed no of rooms to flat type, and preferred towns is optional now)

def step_3_limits():
    return html.Div([
        html.Div("Step 3: Your new home preferences", style={"fontSize": "36px", "fontWeight": "950"}),
        html.Div("This helps us find flats that match your budget and preferences.", style={
            "fontSize": "20px", "fontWeight": "600", "opacity": "0.7", "marginTop": "8px", "marginBottom": "20px"
        }),
        html.Div([
            html.Div("💵 What is the maximum budget for a new home ($)?", style=label_style),
            dcc.Input(id="lim_budget", type="number", value=550000, style=input_style_big),
            html.Div(style={"height": "14px"}),

            html.Div("🛏️ What flat type do you need? (eg. 3 = 3-room flat)", style=label_style),
            dcc.Dropdown(id="lim_min_rooms", options=[2, 3, 4, 5], value=3, clearable=False,
                         style={"fontSize": "22px"}),

            html.Div("📍 Do you have a preferred area to move to? (Optional)", style=label_style),
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

# Step 4 - LBS page    -lbs patch
def step_4_lbs_page():

    return step_4_lbs(
        card_style= card_style,
        label_style= label_style,
        input_style_big= input_style_big,
    )

###Step 5: Results page - results card, map and comparison modal 
def step_5_results():
    return html.Div([
        html.Div("Step 5: Results", style={"fontSize": "36px", "fontWeight": "950"}),
        html.Div('Compare units in detail by selecting the checkbox for each flat and then click the "Compare Units" button at the bottom of the page.', style={
            "fontSize": "18px",
            "fontWeight": "700",
            "opacity": "0.8",
            "marginTop": "8px",
            "marginBottom": "14px",
        }),
        html.Div([
            #Left column is the recommendation cards and reset action
            html.Div([
                html.Div(id="results_list", style={"marginTop": "16px"}),
                html.Div([
                    html.Button("Start over", id="btn_reset", n_clicks=0, style=btn_reset),
                ], style={"marginTop": "14px"}),
            ], style={
                "flex": "1",
                "minWidth": "420px",
                "position": "relative",
            }),

            #Right column is the interactive map
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
            ], style={
                "flex": "1.2",
                "minWidth": "520px",
                "position": "relative",
            }),
        ], style={
            **card_style,
            "display": "flex",
            "gap": "18px",
            "alignItems": "flex-start",
        }),
        #Loading overlay to deal w waiting time and prevent user from thinking it crashed 
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
                # Spinner using Unicode https://unicode-table.com
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

# 
# App layout n stores 
# 

app.layout = html.Div([
    # Client-side stores to keep the user inputs available across the steps and callbacks.

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
    *lbs_stores(),       #lbs patch

    
#### app logo from canva: changed from centre to left 
    html.Div([
        html.Div([
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
                html.Div("⏳", style={        #loading for the step 1 created to showcase that result is being generated same as step 5, step 1 result is fast
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

    #Comparison modal for selected recommendations 
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

# 
# Callbacks (impt for integration)
# 

# Render the current step

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

#Step 1 callbacks --  autosave the inputs and geocode the postal code from onemap (validate that is 6 digit and also validate that it is correct)


#check that postal is valid
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


#autosave and geocode (changed to display the exact address after estimate price - to validate that its correct, added trust i guess)
def autosave_step1(postal, flat_type, area, lease):
    postal = (postal or "").strip()
    flat_type = flat_type or "4 ROOM"
    
    payload = {
        "postal": postal,
        "flat_type": flat_type,
        "floor_area_sqm": float(area) if area not in (None, "") else None,
        "remaining_lease": int(lease) if lease not in (None, "") else None,
    }
    
    #Validation checks: UX so they rmb to fill all the inputs 
    if not postal:
        msg = html.Div("📍 Please enter your postal code.", style=banner_warn)
        return payload, None, msg
    
    if not is_valid_sg_postal(postal):
        msg = html.Div("⚠️ Invalid postal code. Must be 6 digits (e.g., 560123).", style=banner_warn)
        return payload, None, msg
    
    if not flat_type:
        msg = html.Div("🏠 Please choose your flat type from the dropdown menu.", style=banner_warn)
        return payload, None, msg
    
    if not area:
        msg = html.Div("⚠️ Please enter your floor area.", style=banner_warn)
        return payload, None, msg
    
    if not lease:
        msg = html.Div("⚠️ Please enter your remaining lease.", style=banner_warn)
        return payload, None, msg
    
    
    #Try to geocode
    geo = None
    try:
        logger.info(f"[Geocoding] Searching for postal code: {postal}")
        geo = onemap_search(postal)
        if not geo:
            geo = onemap_search(f"Singapore {postal}")
        
        if geo:
            logger.info(f"[Geocoding] Found: {geo}")
            msg = html.Div("✅ Saved. Please click estimate price before you go to the next page", style=banner_ok)
            return payload, geo, msg
        else:
            logger.warning(f"[Geocoding] Could not find postal code: {postal}")
            msg = html.Div("⚠️ Postal code saved, but location not found on map (API error). You can still proceed.", style=banner_warn)
            #Return payload even if geocoding fails, just for flow of app in case cannot find but not possible i guess
            return payload, None, msg
    
    except Exception as e:
        logger.error(f"[Geocoding Error] {str(e)}", exc_info=True)
        msg = html.Div(f"⚠️ Postal code saved. Map lookup failed: check your connection.", style=banner_warn)
        #Return payload even on error
        return payload, None, msg




#####Backend Integration parts#################    #use the mock values till integrate and also as fallback if backend fail to load


# Step 1 callback to request an estimated selling price (sell side)

@app.callback(
    Output("sell_pred", "data"),
    Output("sell_pred_box", "children"),
    Input("btn_estimate", "n_clicks"),
    State("sell_payload", "data"),
    State("sell_geo", "data"),
    prevent_initial_call=True,
)


#return sell price and output price in a box below the main inputs
def estimate_price(n, sell_payload, sell_geo):

    if not sell_payload or not sell_payload.get("postal"):
        return None, ""

    pred = safe_post("/predict/sell", sell_payload)
    if not pred:
        pred = mock_predict_price(sell_payload["postal"], sell_payload["flat_type"], sell_payload.get("floor_area_sqm"))

    address_str = sell_geo.get("address", "") if sell_geo else ""
    box = html.Div([
        html.Div("Estimated selling price", style={"fontSize": "22px", "fontWeight": "950", "opacity": "0.85"}),  ##alrdy made both big enough to see 
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

## Show loading overlay while estimate price is running on Step 1, in case cuz its pretty fast
def show_loading_on_estimate(n_clicks, step):
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

##remove after callback done and output
def hide_loading_when_estimate_ready(sell_pred, step):
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




#Step 2 callback to store user preference weights for healthcare, mrt, hawker and park 

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

# Step 3 callback to store budget, flat type and preffered town 

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



#Step 5 callback to generate recommendations, cards, and map output.

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

##
## Generate the Step 5 recommendation view.
##
## This callback validates the stored inputs, requests or mocks recommendations (our fallback),
## geocodes each unit for recommendations with nearest amenities,
## also build the result cards, and render the Leaflet map HTML.
##

def run_results(main_content, step, sell_payload, sell_geo, sell_pred, prefs_w, constraints, lbs_result):

    if int(step or 1) != 5:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    print(f"DEBUG prefs_w: {prefs_w}")
    print(f"DEBUG constraints: {constraints}")   #####added debug so can see whats the inputs on terminal when testing
    
    #Ensure all thr earlier steps produce whats needed for recommendations --- the logic here is a bit weak maybe can amend step 1 next bttn to not show if nvr click estimate
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


### fallback (impt)
    if not sell_pred:
        sell_pred = mock_predict_price(sell_payload["postal"], sell_payload["flat_type"], sell_payload.get("floor_area_sqm"))



    #   payload = {"sell_payload": sell_payload, "sell_pred": sell_pred,
    #              "weights": prefs_w, "constraints": constraints}
    #   recs = safe_post("/recommend", payload)
    #   if not recs:
    #       recs = mock_recommendations(constraints)

    payload = {"constraints": constraints, "weights": prefs_w}
    recs = safe_post("/recommend", payload)
    if not recs:
        recs = mock_recommendations(constraints)
    

    # Geocode each recommended flat so cards and the map share the same coordinates.
    for r in recs:
        geo = onemap_search(r["postal"]) or onemap_search(f"Singapore {r['postal']}")
        if geo:
            r["lat"], r["lon"], r["address"] = geo["lat"], geo["lon"], geo["address"]
            
            #Calculate the distance from the user's current flat (sell_geo) to this recommended flat  --- haversine refer to helper.py
            r["dist_from_home_km"] = haversine_km(sell_geo["lat"], sell_geo["lon"], r["lat"], r["lon"])
        else:
            #Fallback for geocoding fail
            r["lat"] = sell_geo["lat"] + 0.01
            r["lon"] = sell_geo["lon"] + 0.01
            r["address"] = f"{r['town']} (approx)"
            r["dist_from_home_km"] = 0.01

    #Compute values derived from the sell estimate and geocoded location
    for r in recs:
        r["cash_unlocked"] = int(sell_pred["price"] - r["buy_price"])
        r["dist_from_home_km"] = round(haversine_km(sell_geo["lat"], sell_geo["lon"], r["lat"], r["lon"]), 2)

    #Build map markers and amenity overlays for the current result set
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
            "rec_index": i,
        })

    #Fetch the nearby amenities for each recommendation and keep the nearest item of each type for the card view (open to see nearby amenities)
    amenities = []
    base_lat, base_lon = sell_geo["lat"], sell_geo["lon"]
    radius_km = 2.0
    hawker_debug_rows = []
    for idx, r in enumerate(recs):
        rec_lat, rec_lon = r["lat"], r["lon"]
        
        #Capture the nearest amenity 
        nearest_amenities = {
            "healthcare": None,
            "hawker": None,
            "transport": None,
            "nature": None,
        }

        #Healthcare amenities 
        healthcare_amenities = get_nearby_amenities("healthcare", rec_lat, rec_lon, radius_km=1.0, limit=9999)
        healthcare_with_dist = []
        for amenity in healthcare_amenities:
            dist = haversine_km(rec_lat, rec_lon, amenity["lat"], amenity["lon"])
            healthcare_with_dist.append({**amenity, "distance_km": dist})
        healthcare_with_dist.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 9999)
        logger.info(f"DEBUG: Found {len(healthcare_with_dist)} clinics for rec #{idx+1} at ({rec_lat}, {rec_lon})")
        
        #Keep the closest healthcare option for the results card
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
                "rec_index": idx,
            })

        #Hawker centres and food court
        hawker_amenities = get_nearby_amenities("hawker", rec_lat, rec_lon, radius_km=1.0, limit=100)
        hawker_with_dist = []
        for amenity in hawker_amenities:
            dist = haversine_km(rec_lat, rec_lon, amenity["lat"], amenity["lon"])
            if dist is not None and dist <= 1.0:
                hawker_with_dist.append({**amenity, "distance_km": dist})
        hawker_with_dist.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 9999)
        logger.info(f"DEBUG: Found {len(hawker_with_dist)} hawker/food courts within 2km for rec #{idx+1} at ({rec_lat}, {rec_lon})")
        
        #Keep the closest option for the results card.
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
                "rec_index": idx,
            })
            hawker_debug_rows.append([
                amenity["name"], amenity.get("address", ""), amenity["lat"], amenity["lon"], dist_str
            ])

        #Transport amenities (mrt)
        transport_amenities = get_nearby_amenities("transport", rec_lat, rec_lon, radius_km=1.0, limit=100)
        transport_with_dist = []
        for amenity in transport_amenities:
            dist = haversine_km(rec_lat, rec_lon, amenity["lat"], amenity["lon"])
            if dist is not None and dist <= 1.0:
                transport_with_dist.append({**amenity, "distance_km": dist})
        transport_with_dist.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 9999)
        logger.info(f"DEBUG: Found {len(transport_with_dist)} transport points within 2km for rec #{idx+1} at ({rec_lat}, {rec_lon})")
        
        #Keep the closest option for the results card
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
                "rec_index": idx,
            })

        #Nature and park amenities --- sometimes gets like fitness corners also 
        park_amenities = get_nearby_amenities("parks", rec_lat, rec_lon, radius_km=1.0, limit=100)
        park_with_dist = []
        for park in park_amenities:
            dist = haversine_km(rec_lat, rec_lon, park["lat"], park["lon"])
            if dist is not None and dist <= 1.0:
                park_with_dist.append({**park, "distance_km": dist})
        park_with_dist.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 9999)
        logger.info(f"DEBUG: Found {len(park_with_dist)} parks within 2km for rec #{idx+1} at ({rec_lat}, {rec_lon})")
        
        #Keep the closest option 
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
                "rec_index": idx,
            })
            hawker_debug_rows.append([
                park["name"], park.get("address", ""), park["lat"], park["lon"], dist_str
            ])

                #nearest amenity summaries on the recommendation
        r["nearest_healthcare"] = nearest_amenities["healthcare"]
        r["nearest_hawker"] = nearest_amenities["hawker"]
        r["nearest_transport"] = nearest_amenities["transport"]
        r["nearest_nature"] = nearest_amenities["nature"]




#### results card - after get all the nearest amenities

    cards = []
    for i, r in enumerate(recs, start=1):
        pg_url = r.get("listing_url", "https://www.propertyguru.com.sg")



        ###from backend pred model, just added at the top of card to display whether its a fair deal or not, also added the small info icon. colour shd be good to visualise
        ### 
        valuation = r.get("valuation_label", "N/A")   ## mock (fallback) will show NA
        predicted = r.get("predicted_price", 0)
        actual = r.get("buy_price", 0)
        diff = actual - predicted
        direction = "above" if diff > 0 else "below"
        info_tooltip = f"Our model estimates this flat's value at ${predicted:,.0f}. The listed price is ${actual:,.0f}, which is {direction} our estimate."
        valuation_color = {"Fair Value": "#22c55e", "Above Market": "#f97316", "Below Market": "#0ea5e9"}.get(valuation, "#94a3b8")       
        valuation_emoji = {"Fair Value": "✅ Fair Value", "Above Market": "⚠️ Above Market", "Below Market": "💰 Below Market"}.get(valuation, valuation)

        #Nearest amenity description texts
        hc = r.get("nearest_healthcare")
        hw = r.get("nearest_hawker")
        tr = r.get("nearest_transport")
        na = r.get("nearest_nature")
        health_str = f"{hc['name']} ~{hc['dist_m']}m" if hc else "No healthcare within 1km"
        hawker_str = f"{hw['name']} ~{hw['dist_m']}m" if hw else "No hawker within 1km"
        transport_str = f"{tr['name']} ~{tr['dist_m']}m" if tr else "No transport within 1km"
        nature_str = f"{na['name']} ~{na['dist_m']}m" if na else "No nature within 1km"

        cards.append(html.Div([
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
    dbc.Tooltip(   ##info icon (same as lbs one)
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
            html.Div(f"#{i} • {r.get('address_from_url', r['town'])}", style={
                "fontSize": "28px",
                "fontWeight": "950",
                "lineHeight": "1.2",
            }),
            html.Div(f"Cash unlocked (estimate): ${r['cash_unlocked']:,.0f}", style={
                "fontSize": "22px", "fontWeight": "900", "lineHeight": "1.6",
            }),
            html.Div(f"Listed Price: ${r['buy_price']:,.0f}", style={
                "fontSize": "22px", "fontWeight": "900", "lineHeight": "1.5", "marginTop": "4px",
            }),
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
                "fontSize": "18px",
                "fontWeight": "950",
                "textDecoration": "none",
                "color": "#0ea5e9",
            }),
        ], style={**card_style, "marginTop": "14px"}))
    if lbs_result and lbs_result.get("ok"):
        cards.append(build_lbs_result_card(lbs_result, card_style))
    map_doc = leaflet_map_html(sell_geo["lat"], sell_geo["lon"], points, amenities, zoom=14)

    return html.Div([*cards]), map_doc, recs, lbs_result

#Step 5 loading overlay callbacks

@app.callback(
    Output("results_loading_overlay", "style"),
    Input("main_content", "children"),
    State("step", "data"),
    prevent_initial_call=True,
)
def show_loading_on_step5(main_content, step):
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
    if int(step or 1) != 5:
        return {"display": "none", "position": "fixed", "top": "0", "left": "0", "right": "0", "bottom": "0", "backgroundColor": "rgba(0, 0, 0, 0.4)", "zIndex": "2000", "justifyContent": "center", "alignItems": "center", "flexDirection": "column"}

    if results_list_children:
        return {"display": "none", "position": "fixed", "top": "0", "left": "0", "right": "0", "bottom": "0", "backgroundColor": "rgba(0, 0, 0, 0.4)", "zIndex": "2000", "justifyContent": "center", "alignItems": "center", "flexDirection": "column"}
    
    #Show loading if no content yet
    return {"display": "flex", "position": "fixed", "top": "0", "left": "0", "right": "0", "bottom": "0", "backgroundColor": "rgba(0, 0, 0, 0.4)", "zIndex": "2000", "justifyContent": "center", "alignItems": "center", "flexDirection": "column"}






# Reset all stored state and return to Step 1.

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

####Clear all stored app state and send the user back to step 1
def reset_all(n):
    return 1, None, None, None, None, None, None, None, None, None

#Comparison modal callbacks

@app.callback(
    Output("results_map", "srcDoc", allow_duplicate=True),
    Input("selected_recommendation", "data"),
    State("recs_data", "data"),
    State("sell_geo", "data"),
    State("sell_payload", "data"),
    prevent_initial_call=True,
)



def update_map_for_focused_flat(focused_index, recs_data, sell_geo, sell_payload):
    
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
    
    #Fetch only the amenities for the focused recommendation
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
            "rec_index": 0,  
        })
    
    #Hawker centres & food court
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
            "rec_index": 0,  
        })
    
    #Transport (MRT n LRT)
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
            "rec_index": 0,  
        })
    
    #Nature parks n fitness corners (recreation)
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
    
    #Generate and return the updated map
    map_doc = leaflet_map_html(rec_lat, rec_lon, points, amenities, zoom=14)
    return map_doc

@app.callback(
    Output("selected_units", "data"),
    Input({"type": "unit_checkbox", "index": dash.ALL}, "value"),
    prevent_initial_call=True,
)

##for comparison modal
def update_selected_units(checkbox_values):
    if not checkbox_values:
        return []
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

    #Always close modal when navigating steps or showing results
    if trig in ["step", "recs_data"]:
        return False

    if trig == "btn_close_modal":
        return False

    if trig == "btn_compare":
        #only open if user has selected at least one of the units
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


#### comparison model main tabular form
def render_comparison_modal(is_open, selected_indices, recs_data, results_lbs_result):

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

        #normalise selected indices
        normalised_indices = []
        for raw_idx in selected_indices:
            try:
                idx = int(raw_idx)
            except (TypeError, ValueError):
                continue
            if idx not in normalised_indices:
                normalised_indices.append(idx)

        selected_items = []
        for idx in normalised_indices:
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

        # 
        # detailed comparison table
        # 
    
        headers = ["Metric", *[item["label"] for item in selected_items]]

        metrics = [
            ("Town", "town", None),
            ("Rooms", "rooms", None),
            ("Listed Price", "buy_price", "min"),
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


#####  for comparison part to display the best of the metric
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

        # 
        # summary section
        # selected flats + LBS stay  (smaller table - to show lbs also)
        # 
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


##### insights box bside to show the best option based on cash unlocked
        insight_box = html.Div([
            html.Div("Recommendation Insight", style={"fontSize": "22px", "fontWeight": "900", "marginBottom": "10px"}),
            html.Ul([
                html.Li(
                    f"{best_cash_option['label']} provides the highest immediate cash unlocked.",
                    style={"marginBottom": "10px", "fontSize": "16px"}
                ),
                html.Li(
                    "Use the comparison above to weigh the amenities nearby and cash unlocked. You may visit the HDB website for more information on Silver Housing Bonus Scheme and LBS",
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
            normalised_indices,
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

# 
# App entry point port
# 
import os
port = int(os.environ.get("PORT", 8050))
app.run(host="0.0.0.0", port=port, debug=False)