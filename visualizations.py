"""
Visualization components for the House Buying Checklist app.
Handles donut charts and progress displays using streamlit-echarts.
"""

import colorsys
import html as _html
import os

import streamlit as st
from streamlit_echarts import st_echarts

_CSS_PATH = os.path.join(os.path.dirname(__file__), "styles.css")


def brighten_hex_color(hex_color, lightness_boost=0.16, saturation_boost=0.08):
    hex_color = hex_color.lstrip('#')
    r, g, b = tuple(int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l = min(1, l + lightness_boost)
    s = min(1, s + saturation_boost)
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"


def darken_hex_color(hex_color, lightness_reduction=0.25):
    hex_color = hex_color.lstrip('#')
    r, g, b = tuple(int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l = max(0, l - lightness_reduction)
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"


def build_pie_figure(section_data, selected_section):
    """
    Build an ECharts donut chart options dict.

    Returns:
        dict: echarts options dict ready for st_echarts()
    """
    data_items = []
    for d in section_data:
        color = brighten_hex_color(d['color']) if d['name'] == selected_section else d['color']
        data_items.append({
            "name": f"{d['name']} ({int(d['completed'])}/{int(d['total'])})",
            "value": d['total'],
            "selected": d['name'] == selected_section,
            "itemStyle": {
                "color": color,
                "borderColor": darken_hex_color(d['color'], lightness_reduction=0.35),
                "borderWidth": 3,
                "shadowBlur": 10,
                "shadowColor": "rgba(0,0,0,0.3)"
            }
        })

    selected_meta = next((d for d in section_data if d['name'] == selected_section), section_data[0])

    options = {
        "tooltip": {"trigger": "item", "formatter": "{b}: {c} items"},
        "legend": {"type": "scroll", "orient": "vertical", "right": "5px", "top": "middle", "bottom": "10px"},
        "graphic": [{
            "type": "text",
            "left": "45%",
            "top": "middle",
            "style": {
                "text": f"{selected_meta['name']}\n{int(selected_meta['completed'])} of {int(selected_meta['total'])} done",
                "textAlign": "left",
                "font": "bold 14px Arial",
                "fill": "#0F172A"
            }
        }],
        "series": [{
            "name": "Progress",
            "type": "pie",
            "selectedMode": "single",
            "selectedOffset": 12,
            "radius": ["30%", "60%"],
            "center": ["50%", "50%"],
            "avoidLabelOverlap": False,
            "label": {
                "show": True,
                "position": "outside",
                "formatter": "{b}",
                "fontSize": 14,
                "fontWeight": "bold",
                "color": "#0F172A",
                "textShadowColor": "rgba(255,255,255,0.8)",
                "textShadowBlur": 8,
                "textShadowOffsetY": 1,
                "overflow": "break",
                "width": 90,
                "height": 150,
                "margin": 2
            },
            "labelLine": {
                "show": True,
                "length": 5,
                "length2": 3,
            },
            "emphasis": {
                "label": {"show": True, "fontSize": 14, "fontWeight": "bold"},
                "itemStyle": {"shadowBlur": 20, "shadowColor": "rgba(0,0,0,0.5)"}
            },
            "data": data_items
        }]
    }
    return options


def render_pie_with_progress(fig_options, section_data, selected_section, section_names):
    """
    Render donut chart and section progress card.
    """
    selected_meta = next((d for d in section_data if d['name'] == selected_section), section_data[0])

    # Click event: extract section name (strip the "(x/y)" suffix)
    click_events = {"click": "function(params) { return params.name; }"}

    clicked = st_echarts(
        options=fig_options,
        events=click_events,
        height="600px",
        key="section-progress-donut",
    )

    # Handle slice click — value is BidiComponentResult with 'chart_event' key
    if clicked:
        name = None
        if isinstance(clicked, str):
            name = clicked
        elif hasattr(clicked, 'get'):
            name = clicked.get("chart_event") or clicked.get("name")
        if name:
            raw = name.split(" (")[0]
            if raw in section_names and raw != selected_section:
                st.session_state.selected_section = raw
                st.session_state.selected_section_dropdown = raw
                st.rerun(scope="fragment")


def render_checklist_html_table(df) -> None:
    """Render checklist DataFrame as a styled HTML table with full text wrapping."""
    TABLE_CSS = """
    <style>
    body { margin:0; padding:0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }
    .cl-table { width:100%; border-collapse:collapse; font-size:13px; }
    .cl-table thead th {
        background:#3b82f6; color:#fff; font-weight:700;
        padding:10px 12px; text-align:left;
    }
    .cl-table tbody td {
        padding:8px 12px; border-bottom:1px solid #e2e8f0;
        vertical-align:top; word-break:break-word; white-space:normal;
    }
    .cl-table tbody tr:hover td { background:#f0f9ff; }
    .cl-table tbody tr.done td { background:#d1fae5; }
    .cl-table .col-section { min-width:160px; font-weight:600; color:#1e40af; }
    .cl-table .col-item    { min-width:280px; }
    .cl-table .col-done    { text-align:center; width:50px; }
    .cl-table .col-cert    { text-align:center; width:90px; }
    .cl-table .col-pending { min-width:120px; }
    .cl-table .col-date    { min-width:100px; }
    .cl-table .col-notes   { min-width:150px; }
    </style>
    """
    rows = []
    for _, row in df.iterrows():
        done = bool(row.get('Done', False))
        cert = bool(row.get('Tested certificate available', False))
        done_icon = "\u2705" if done else "\u2610"
        cert_icon = "\u2705" if cert else "\u2014"
        row_class = ' class="done"' if done else ''
        section  = _html.escape(str(row.get('Section', '')))
        item     = _html.escape(str(row.get('Item', '')))
        pending  = _html.escape(str(row.get('Pending With', '') or ''))
        date_c   = _html.escape(str(row.get('Date Completed', '') or ''))
        notes    = _html.escape(str(row.get('Notes', '') or ''))
        rows.append(
            f'<tr{row_class}>'
            f'<td class="col-section">{section}</td>'
            f'<td class="col-item">{item}</td>'
            f'<td class="col-done">{done_icon}</td>'
            f'<td class="col-pending">{pending}</td>'
            f'<td class="col-date">{date_c}</td>'
            f'<td class="col-notes">{notes}</td>'
            f'<td class="col-cert">{cert_icon}</td>'
            '</tr>'
        )
    header = (
        '<thead><tr>'
        '<th>Section</th><th>Item</th><th>Done</th>'
        '<th>Pending With</th><th>Date Completed</th>'
        '<th>Notes</th><th>Certificate</th>'
        '</tr></thead>'
    )
    html_body = TABLE_CSS + f'<table class="cl-table">{header}<tbody>{"".join(rows)}</tbody></table>'
    st.html(html_body)


def apply_glass_effect_styling():
    """Inject styles.css into the Streamlit page."""
    with open(_CSS_PATH, "r", encoding="utf-8") as f:
        st.html(f"<style>{f.read()}</style>")
