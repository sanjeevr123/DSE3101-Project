from dash import html, dcc, Input, Output, State

FLAT_TYPE_TO_LBS_CODE = {
    "2 ROOM": "2R",
    "3 ROOM": "3R",
    "4 ROOM": "4R",
    "5 ROOM": "5Rplus",
    "EXECUTIVE": "5Rplus",
}


def safe_num(x, default=0.0):
    try:
        if x in (None, ""):
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


def fmt_money(x):
    try:
        return f"${float(x):,.0f}"
    except Exception:
        return "$0"


def compute_required_ra(age, n):
    """
    Hardcoded 2026-style estimates.
    Update these values before final submission if your team has newer figures.
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
        "loan": loan,
        "market_value": mv,
        "required_ras": required_ras,
        "topups": topups,
        "flat_type_bonus_tier": flat_type,
        "owner_count": n,
    }



def lbs_stores():
    return [
        dcc.Store(id="lbs_inputs"),
        dcc.Store(id="lbs_result"),
    ]



def lbs_inputs_card(card_style, label_style, input_style_big, btn_primary):
    field_style = {"marginBottom": "12px"}
    inline_row = {"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "12px"}

    return html.Div([
        html.Div("Optional: Lease Buyback Scheme (LBS)", style={"fontSize": "28px", "fontWeight": "950"}),
        html.Div(
            "Use this only if the current flat owner(s) may take up LBS. This stays on the Results page so you do not have to rework the step flow.",
            style={"fontSize": "16px", "opacity": 0.78, "marginBottom": "14px"},
        ),
        html.Div([
            html.Div([
                html.Div("Number of owners", style=label_style),
                dcc.Dropdown(
                    id="lbs_num_owners",
                    options=[{"label": "1 owner", "value": 1}, {"label": "2 owners", "value": 2}],
                    value=1,
                    clearable=False,
                    style={"fontSize": "18px"},
                ),
            ], style=field_style),
            html.Div([
                html.Div("Outstanding loan (SGD)", style=label_style),
                dcc.Input(id="lbs_loan", type="number", value=0, style=input_style_big),
            ], style=field_style),
            html.Div([
                html.Div("Remaining lease on current flat (years)", style=label_style),
                dcc.Input(id="lbs_remaining_lease", type="number", value=65, style=input_style_big),
            ], style=field_style),
            html.Div([
                html.Div("Retained lease after LBS (years, min 20)", style=label_style),
                dcc.Input(id="lbs_retained_lease", type="number", value=30, style=input_style_big),
            ], style=field_style),
            html.Div([
                html.Div([
                    html.Div("Owner 1 age", style=label_style),
                    dcc.Input(id="lbs_owner1_age", type="number", value=65, style=input_style_big),
                ]),
                html.Div([
                    html.Div("Owner 1 RA balance (SGD)", style=label_style),
                    dcc.Input(id="lbs_owner1_ra", type="number", value=0, style=input_style_big),
                ]),
            ], style={**inline_row, **field_style}),
            html.Div(id="lbs_owner2_row", children=[
                html.Div([
                    html.Div("Owner 2 age", style=label_style),
                    dcc.Input(id="lbs_owner2_age", type="number", value=65, style=input_style_big),
                ]),
                html.Div([
                    html.Div("Owner 2 RA balance (SGD)", style=label_style),
                    dcc.Input(id="lbs_owner2_ra", type="number", value=0, style=input_style_big),
                ]),
            ], style={**inline_row, **field_style, "display": "none"}),
            html.Div([
                html.Button("Calculate LBS outcome", id="btn_lbs_calculate", n_clicks=0, style=btn_primary),
                html.Div(id="lbs_banner", style={"marginTop": "10px"}),
            ]),
            html.Div(id="lbs_metrics", style={"marginTop": "14px"}),
        ])
    ], style={**card_style, "marginBottom": "18px"})



def lbs_metric_box(label, value):
    return html.Div([
        html.Div(label, style={"fontSize": "14px", "fontWeight": "800", "opacity": 0.72}),
        html.Div(value, style={"fontSize": "20px", "fontWeight": "950"}),
    ], style={
        "background": "#f8fafc",
        "border": "1px solid #e2e8f0",
        "borderRadius": "14px",
        "padding": "14px",
    })



def build_lbs_metrics(result):
    if not result:
        return html.Div(
            "LBS not calculated yet. You can still run standard downsizing results.",
            style={"fontSize": "15px", "opacity": 0.72},
        )
    if result.get("error"):
        return html.Div(result["error"], style={"fontSize": "15px", "color": "#b91c1c", "fontWeight": "800"})

    return html.Div([
        html.Div([
            lbs_metric_box("Net LBS proceeds", fmt_money(result["net_lbs"])),
            lbs_metric_box("Cash total after bonus", fmt_money(result["cash_total"])),
            lbs_metric_box("LBS bonus", fmt_money(result["bonus_lbs"])),
            lbs_metric_box("Household RA final", fmt_money(result["ra_household_final"])),
        ], style={"display": "grid", "gridTemplateColumns": "repeat(2, minmax(180px, 1fr))", "gap": "12px"})
    ])



def build_lbs_card_block(rec, lbs_result, card_style=None):
    if not lbs_result or lbs_result.get("error"):
        return None

    total_cash_now = safe_num(rec.get("cash_unlocked", 0)) + safe_num(lbs_result.get("cash_total", 0))

    return html.Div([
        html.Div("If you also use LBS on your current flat", style={"fontSize": "18px", "fontWeight": "900", "marginBottom": "6px"}),
        html.Div(f"Additional LBS cash: {fmt_money(lbs_result['cash_total'])}", style={"fontSize": "17px", "fontWeight": "800"}),
        html.Div(f"Total immediate cash after downsizing + LBS: {fmt_money(total_cash_now)}", style={"fontSize": "18px", "fontWeight": "900"}),
        html.Div(f"Household RA after LBS: {fmt_money(lbs_result['ra_household_final'])}", style={"fontSize": "16px", "fontWeight": "800", "opacity": 0.82}),
    ], style={
        "marginTop": "12px",
        "padding": "12px 14px",
        "background": "#f5f3ff",
        "border": "1px solid #ddd6fe",
        "borderRadius": "14px",
    })



def register_lbs_callbacks(app, banner_ok=None, banner_warn=None):
    ok_style = banner_ok or {"background": "#ecfdf5", "color": "#065f46", "padding": "10px 12px", "borderRadius": "12px", "fontWeight": "800"}
    warn_style = banner_warn or {"background": "#fef2f2", "color": "#991b1b", "padding": "10px 12px", "borderRadius": "12px", "fontWeight": "800"}

    @app.callback(
        Output("lbs_owner2_row", "style"),
        Input("lbs_num_owners", "value"),
    )
    def toggle_owner2_row(num_owners):
        base = {"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "12px", "marginBottom": "12px"}
        if int(num_owners or 1) == 2:
            return base
        return {**base, "display": "none"}

    @app.callback(
        Output("lbs_inputs", "data"),
        Output("lbs_result", "data"),
        Output("lbs_banner", "children"),
        Output("lbs_metrics", "children"),
        Input("btn_lbs_calculate", "n_clicks"),
        State("sell_payload", "data"),
        State("sell_pred", "data"),
        State("lbs_num_owners", "value"),
        State("lbs_loan", "value"),
        State("lbs_remaining_lease", "value"),
        State("lbs_retained_lease", "value"),
        State("lbs_owner1_age", "value"),
        State("lbs_owner1_ra", "value"),
        State("lbs_owner2_age", "value"),
        State("lbs_owner2_ra", "value"),
        prevent_initial_call=True,
    )
    def compute_lbs_callback(_, sell_payload, sell_pred, num_owners, loan, remaining_lease, retained_lease,
                             owner1_age, owner1_ra, owner2_age, owner2_ra):
        num_owners = int(num_owners or 1)
        owner_ages = [safe_num(owner1_age)]
        owner_ras = [safe_num(owner1_ra)]
        if num_owners == 2:
            owner_ages.append(safe_num(owner2_age))
            owner_ras.append(safe_num(owner2_ra))

        mv = safe_num((sell_pred or {}).get("price"), 0)
        flat_type = (sell_payload or {}).get("flat_type", "4 ROOM")

        inputs = {
            "num_owners": num_owners,
            "loan": safe_num(loan),
            "remaining_lease": safe_num(remaining_lease),
            "retained_lease": safe_num(retained_lease),
            "owner_ages": owner_ages,
            "owner_ras": owner_ras,
            "market_value": mv,
            "flat_type": flat_type,
        }

        if mv <= 0:
            msg = html.Div("Please complete Step 1 price estimate first so LBS can use the current flat market value.", style=warn_style)
            return inputs, {"error": "Missing market value from Step 1."}, msg, html.Div()

        result = compute_lbs(
            mv=mv,
            remaining_lease=safe_num(remaining_lease),
            retained_lease=safe_num(retained_lease),
            loan=safe_num(loan),
            owner_ages=owner_ages,
            owner_ras=owner_ras,
            flat_type_skeleton=flat_type,
        )

        if result.get("error"):
            msg = html.Div(result["error"], style=warn_style)
            return inputs, result, msg, build_lbs_metrics(result)

        msg = html.Div("✅ LBS scenario saved. It will now be reflected inside each result card.", style=ok_style)
        return inputs, result, msg, build_lbs_metrics(result)
