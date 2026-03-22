"""
Visualization components for the House Buying Checklist app.
Handles donut charts and progress displays using streamlit-echarts.
"""

import colorsys
import streamlit as st
from streamlit_echarts import st_echarts


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
        "legend": {"type": "scroll", "orient": "vertical", "right": "1%", "top": "middle"},
        "graphic": [{
            "type": "text",
            "left": "center",
            "top": "middle",
            "style": {
                "text": f"{selected_meta['name']}\n{int(selected_meta['completed'])} of {int(selected_meta['total'])} done",
                "textAlign": "center",
                "font": "bold 14px Arial",
                "fill": "#0F172A"
            }
        }],
        "series": [{
            "name": "Progress",
            "type": "pie",
            "radius": ["40%", "70%"],
            "center": ["48%", "50%"],
            "avoidLabelOverlap": True,
            "label": {
                "show": True,
                "position": "outside",
                "formatter": "{b}",
                "fontSize": 16,
                "fontWeight": "bold",
                "overflow": "break",
                "width": 120,
                "color": "#0F172A",
                "textShadowColor": "rgba(255,255,255,0.8)",
                "textShadowBlur": 8,
                "textShadowOffsetY": 1
            },
            "emphasis": {
                "label": {"show": True, "fontSize": 14, "fontWeight": "bold"},
                "itemStyle": {"shadowBlur": 20, "shadowColor": "rgba(0,0,0,0.5)"}
            },
            "labelLine": {"show": True},
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

    clicked = st_echarts(options=fig_options, events=click_events, height="600px")

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

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(f"""
        <div style="text-align:center; padding:16px; background:#f0f8ff; border-radius:10px; margin-top:-10px">
            <h3 style="margin:0; color:#0F172A;">{selected_meta['name']}</h3>
            <p style="margin:8px 0; font-size:18px; color:#333;">
                <strong>{int(selected_meta['completed'])} of {int(selected_meta['total'])} done</strong>
            </p>
            <p style="margin:0; color:#666;">{selected_meta['percent']:.0f}% complete</p>
        </div>
        """, unsafe_allow_html=True)
