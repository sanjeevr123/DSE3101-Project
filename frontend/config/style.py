from email.policy import default


PAGE_BG = "linear-gradient(135deg, #e8f7ff 0%, #eefcf3 55%, #f2f5ff 100%)"
SHADOW = "0 10px 26px rgba(15, 23, 42, 0.12)"

base_page_style = {
    "minHeight": "100vh",
    "background": PAGE_BG,
    "padding": "22px 18px",
    "fontFamily": "Arial, sans-serif",
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
    "padding": "14px 18px",
    "fontSize": "24px",
    "lineHeight": "1.25",
    "minHeight": "62px",
    "height": "auto",
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
