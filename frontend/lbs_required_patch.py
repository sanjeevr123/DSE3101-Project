from __future__ import annotations

from typing import Any, Dict, List, Optional

from dash import Input, Output, State, dcc, html

import dash_bootstrap_components as dbc

STEP_META = [
    ("1", "Price estimate"),
    ("2", "What matters"),
    ("3", "Your limits"),
    ("4", "LBS details"),
    ("5", "Results"),
]


DEFAULT_RETAINED_VALUE = 200_000.0
DEFAULT_MONTHLY_PAYOUT_YEARS = 20


def lbs_stores() -> List[dcc.Store]:
    return [
        dcc.Store(id="lbs_inputs"),
        dcc.Store(id="lbs_result"),
    ]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def compute_required_ra(age: Any, num_owners: Any) -> int:
    age = int(_safe_float(age, 0))
    num_owners = int(_safe_float(num_owners, 1))

    if num_owners == 1:
        if 65 <= age <= 69:
            return 220_400
        if 70 <= age <= 79:
            return 210_000
        if age >= 80:
            return 197_760
        return 220_400
    else:
        if 65 <= age <= 69:
            return 110_200
        if 70 <= age <= 79:
            return 105_000
        if age >= 80:
            return 98_880
        return 110_200


def compute_lbs_result(inputs: Dict[str, Any], sell_pred: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not inputs:
        return {"ok": False, "message": "Missing LBS inputs."}

    # fixed internal assumptions for prototype
    FIXED_BONUS_RATE = 0.05
    FIXED_PAYOUT_SHARE = 0.60

    num_owners = int(_safe_float(inputs.get("num_owners"), 1))
    age_owner_1 = int(_safe_float(inputs.get("age_owner_1"), 0))
    age_owner_2 = int(_safe_float(inputs.get("age_owner_2"), 0)) if num_owners == 2 else None

    ra_owner_1 = _safe_float(inputs.get("ra_owner_1"), 0)
    ra_owner_2 = _safe_float(inputs.get("ra_owner_2"), 0) if num_owners == 2 else 0.0

    if age_owner_1 < 65:
        return {"ok": False, "message": "Owner 1 must be at least 65 for LBS."}
    if num_owners == 2 and age_owner_2 < 65:
        return {"ok": False, "message": "Both owners must be at least 65 for the 2-owner LBS scenario."}

    current_value = _safe_float((sell_pred or {}).get("price"), 0)
    if current_value <= 0:
        return {"ok": False, "message": "Current flat value is unavailable. Please complete Step 1 first."}

    remaining_lease = _safe_float(inputs.get("remaining_lease"), 0)

    # New logic: retain value proportional to lease retained (min 20 years assumption)
    if remaining_lease > 0:
        lease_ratio = min(1.0, max(0.2, remaining_lease / 99))
        retained_value = current_value * lease_ratio
    else:
        retained_value = min(DEFAULT_RETAINED_VALUE, current_value)

    req_ra_1 = compute_required_ra(age_owner_1, num_owners)
    req_ra_2 = compute_required_ra(age_owner_2, num_owners) if num_owners == 2 else 0

    topup_needed_1 = max(0.0, req_ra_1 - ra_owner_1)
    topup_needed_2 = max(0.0, req_ra_2 - ra_owner_2) if num_owners == 2 else 0.0
    total_topup_needed = topup_needed_1 + topup_needed_2

    gross_lbs_proceeds = max(0.0, current_value - retained_value)
    cpf_topup = min(gross_lbs_proceeds, total_topup_needed)
    remaining_after_topup = max(0.0, gross_lbs_proceeds - cpf_topup)
    lbs_bonus = cpf_topup * FIXED_BONUS_RATE
    cash_total = remaining_after_topup * FIXED_PAYOUT_SHARE
    net_lbs = cash_total + lbs_bonus
    estimated_monthly_payout = net_lbs / (DEFAULT_MONTHLY_PAYOUT_YEARS * 12)
    ra_household_final = ra_owner_1 + ra_owner_2 + cpf_topup + lbs_bonus

    return {
        "ok": True,
        "inputs": inputs,
        "current_value": round(current_value, 2),
        "retained_value": round(retained_value, 2),
        "gross_lbs_proceeds": round(gross_lbs_proceeds, 2),
        "cpf_topup": round(cpf_topup, 2),
        "cash_total": round(cash_total, 2),
        "net_lbs": round(net_lbs, 2),
        "estimated_monthly_payout": round(estimated_monthly_payout, 2),
        "lbs_bonus": round(lbs_bonus, 2),
        "ra_household_final": round(ra_household_final, 2),
        "required_ra_owner_1": req_ra_1,
        "required_ra_owner_2": req_ra_2,
        "topup_needed_owner_1": round(topup_needed_1, 2),
        "topup_needed_owner_2": round(topup_needed_2, 2),
        "total_topup_needed": round(total_topup_needed, 2),
        "payout_share": FIXED_PAYOUT_SHARE,
        "bonus_rate": FIXED_BONUS_RATE,
        "num_owners": num_owners,
    }

def _metric_box(label: str, value: str) -> html.Div:
    return html.Div(
        [
            html.Div(label, style={"fontSize": "15px", "fontWeight": "800", "opacity": 0.72}),
            html.Div(value, style={"fontSize": "22px", "fontWeight": "950", "marginTop": "6px"}),
        ],
        style={
            "background": "rgba(14,165,233,0.06)",
            "border": "1px solid rgba(14,165,233,0.18)",
            "borderRadius": "14px",
            "padding": "14px 16px",
        },
    )


def step_4_lbs(card_style: Dict[str, Any], label_style: Dict[str, Any], input_style_big: Dict[str, Any]) -> html.Div:
    return html.Div([
        html.Div("Step 4: Lease Buyback Scheme details", style={"fontSize": "36px", "fontWeight": "950"}),

        html.Div([
            html.Div(
                "The Lease Buyback Scheme (LBS) allows elderly homeowners to unlock cash from their flat while continuing to live in it.",
                style={"fontSize": "20px", "fontWeight": "800", "lineHeight": "1.5", "marginBottom": "8px"},
            ),
            html.Div(
                "Instead of moving to a smaller flat, you can retain part of your lease, receive a cash payout, and top up your CPF Retirement Account. "
                "This is useful for households that prefer improving retirement support while staying in their current flat.",
                style={"fontSize": "20px", "fontWeight": "600", "opacity": "0.82", "lineHeight": "1.5", "marginBottom": "18px"},
            ),
            html.Div([
    "Not sure about LBS? ",
    html.A(
        "Click here to learn more about the Lease Buyback Scheme.",
        href="https://www.hdb.gov.sg/managing-my-home/retirement-planning/monetising-flat-for-retirement/lease-buyback-scheme-lbs",
        target="_blank",
        style={"color": "#E2231A", "fontWeight": "800", "fontSize": "20px"}
    ),
], style={"fontSize": "20px", "fontWeight": "600", "marginBottom": "16px"}),

html.Div([
    "Not sure about your CPF Retirement Account balance? ",
    html.A(
        "Click here to log in to the CPF portal to view your balance.",
        href="https://www.cpf.gov.sg/member/ds/",
        target="_blank",
        style={"color": "#00843D", "fontWeight": "800", "fontSize": "20px"}
    ),
], style={"fontSize": "18px", "fontWeight": "600", "marginBottom": "20px"}),
            html.Div(
                "Fill in the details below to estimate the outcome of choosing the Lease Buyback Scheme.",
                style={"fontSize": "20px", "fontWeight": "700", "opacity": "0.78", "marginBottom": "14px"},
            ),

            html.Div("Number of owners", style=label_style),
            dcc.Dropdown(
                id="lbs_num_owners",
                options=[
                    {"label": "1 owner", "value": 1},
                    {"label": "2 owners", "value": 2},
                ],
                value=1,
                clearable=False,
                style={"fontSize": "22px"},
            ),
            html.Div(style={"height": "14px"}),

            html.Div("Owner 1 age", style=label_style),
            dcc.Input(id="lbs_age_owner_1", type="number", min=65, value=65, style=input_style_big),
            html.Div(style={"height": "14px"}),

            html.Div([
                html.Span("Owner 1 CPF Retirement Account (RA) balance ($)", style=label_style),
                html.Span(
                    "ⓘ",
                    id="owner1-ra-info",
                    style={
                        "marginLeft": "8px",
                        "cursor": "pointer",
                        "fontSize": "18px",
                        "color": "#64748b",
                        "fontWeight": "700",
                    },
                ),
            ], style={"display": "flex", "alignItems": "center", "gap": "6px"}),

            dbc.Tooltip(
                "This refers to the amount currently in the CPF Retirement Account (RA). Please check the exact value on the CPF website after logging in with Singpass.",
                target="owner1-ra-info",
                placement="right",
                style={
                    "backgroundColor": "white",
                    "color": "#1f2937",
                    "borderRadius": "8px",
                    "boxShadow": "0 4px 12px rgba(0,0,0,0.1)",
                    "padding": "12px 14px",
                    "fontSize": "16px",
                    "fontWeight": "bold",
                    "maxWidth": "420px",
                    "fontFamily": "Arial, sans-serif",
                    "whiteSpace": "normal",
                    "lineHeight": "1.4",
                    "overflow": "visible",
                    "height": "auto",
                },
            ),

            dcc.Input(id="lbs_ra_owner_1", type="number", min=0, value=80_000, style=input_style_big),
            html.Div(style={"height": "14px"}),

            html.Div(id="lbs_owner_2_block", children=[
                html.Div("Owner 2 age", style=label_style),
                dcc.Input(id="lbs_age_owner_2", type="number", min=65, value=65, style=input_style_big),
                html.Div(style={"height": "14px"}),

                html.Div([
                    html.Span("Owner 2 CPF Retirement Account (RA) balance ($)", style=label_style),
                    html.Span(
                        "ⓘ",
                        id="owner2-ra-info",
                        style={
                            "marginLeft": "8px",
                            "cursor": "pointer",
                            "fontSize": "18px",
                            "color": "#64748b",
                            "fontWeight": "700",
                        },
                    ),
                ], style={"display": "flex", "alignItems": "center", "gap": "6px"}),

                dbc.Tooltip(
                    "This refers to the amount currently in the CPF Retirement Account (RA). Please check the exact value on the CPF website after logging in with Singpass.",
                    target="owner2-ra-info",
                    placement="right",
                    style={
                        "backgroundColor": "white",
                        "color": "#1f2937",
                        "borderRadius": "8px",
                        "boxShadow": "0 4px 12px rgba(0,0,0,0.1)",
                        "padding": "12px 14px",
                        "fontSize": "16px",
                        "fontWeight": "bold",
                        "maxWidth": "420px",
                        "fontFamily": "Arial, sans-serif",
                        "whiteSpace": "normal",
                        "lineHeight": "1.4",
                        "overflow": "visible",
                        "height": "auto",
                    },
                ),

                dcc.Input(id="lbs_ra_owner_2", type="number", min=0, value=80_000, style=input_style_big),
                html.Div(style={"height": "14px"}),
            ], style={"display": "none"}),

            html.Div(id="lbs_saved_banner"),
            html.Div(id="lbs_step_summary", style={"marginTop": "12px"}),
        ], style=card_style),
    ])

def build_results_lbs_summary(lbs_result: Optional[Dict[str, Any]], card_style: Dict[str, Any]) -> html.Div:
    return html.Div()

def build_lbs_card_block(rec: Dict[str, Any], lbs_result: Optional[Dict[str, Any]]) -> html.Div:
    return html.Div()


def build_lbs_result_card(lbs_result: Optional[Dict[str, Any]], card_style: Dict[str, Any]) -> html.Div:
    if not lbs_result or not lbs_result.get("ok"):
        return html.Div()

    return html.Div([
        html.Div("#4 • Stay in current flat • LBS", style={
            "fontSize": "28px",
            "fontWeight": "950",
        }),

        html.Div(f"Cash unlocked (estimate): ${lbs_result['net_lbs']:,.0f}", style={
            "fontSize": "22px",
            "fontWeight": "900",
            "lineHeight": "1.6",
        }),

        html.Div(f"Estimated monthly payout: ${lbs_result.get('estimated_monthly_payout', 0):,.0f}/month", style={
            "fontSize": "22px",
            "fontWeight": "900",
            "lineHeight": "1.5",
            "marginTop": "4px",
        }),

        html.Details([
            html.Summary("LBS Breakdown ▼", style={
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
                html.Ul([
                    html.Li(f"Cash total: ${lbs_result['cash_total']:,.0f}", style={"fontSize": "18px", "fontWeight": "900"}),
                    html.Li(f"CPF top-up: ${lbs_result['cpf_topup']:,.0f}", style={"fontSize": "18px", "fontWeight": "900"}),
                    html.Li(f"LBS bonus: ${lbs_result['lbs_bonus']:,.0f}", style={"fontSize": "18px", "fontWeight": "900"}),
                    html.Li(f"RA household final: ${lbs_result['ra_household_final']:,.0f}", style={"fontSize": "18px", "fontWeight": "900"}),
                ], style={"margin": "8px 0 0 20px"}),
            ]),
        ]),

        html.Div("This option represents staying in the current flat under LBS", style={
            "fontSize": "16px",
            "fontWeight": "700",
            "opacity": 0.72,
            "marginTop": "12px",
        }),

    ], style={**card_style, "marginTop": "14px"})


def register_lbs_callbacks(app, banner_ok: Dict[str, Any], banner_warn: Dict[str, Any], card_style: Optional[Dict[str, Any]] = None):
    @app.callback(
        Output("lbs_owner_2_block", "style"),
        Input("lbs_num_owners", "value"),
    )
    def toggle_owner_2(num_owners):
        return {"display": "block"} if int(_safe_float(num_owners, 1)) == 2 else {"display": "none"}

    @app.callback(
        Output("lbs_inputs", "data"),
        Output("lbs_result", "data"),
        Output("lbs_saved_banner", "children"),
        Output("lbs_step_summary", "children"),
        Input("lbs_num_owners", "value"),
        Input("lbs_age_owner_1", "value"),
        Input("lbs_ra_owner_1", "value"),
        Input("lbs_age_owner_2", "value"),
        Input("lbs_ra_owner_2", "value"),
        State("sell_pred", "data"),
        prevent_initial_call=True,
    )
    def save_and_compute_lbs(num_owners, age_owner_1, ra_owner_1, age_owner_2, ra_owner_2, sell_pred):
        inputs = {
            "num_owners": int(_safe_float(num_owners, 1)),
            "age_owner_1": int(_safe_float(age_owner_1, 0)),
            "ra_owner_1": _safe_float(ra_owner_1, 0),
            "age_owner_2": int(_safe_float(age_owner_2, 0)) if int(_safe_float(num_owners, 1)) == 2 else None,
            "ra_owner_2": _safe_float(ra_owner_2, 0) if int(_safe_float(num_owners, 1)) == 2 else 0,
            "remaining_lease": (sell_pred or {}).get("remaining_lease", 0),
        }
        result = compute_lbs_result(inputs, sell_pred)

        if not result.get("ok"):
            return inputs, result, html.Div(result["message"], style=banner_warn), html.Div()

        return inputs, result, html.Div("✅ LBS details saved.", style=banner_ok), html.Div()


def validate_lbs_for_navigation(step: int, lbs_result: Optional[Dict[str, Any]]):
    step = int(step or 1)
    if step == 4 and (not lbs_result or not lbs_result.get("ok")):
        return False
    return True
