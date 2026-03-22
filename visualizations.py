"""
Visualization components for the House Buying Checklist app.
Handles 3D pie/donut charts, progress displays, and related chart utilities using PyEcharts.
"""

import colorsys
import streamlit as st
from pyecharts import options as opts
from pyecharts.charts import Pie
from streamlit_echarts import st_echarts


def brighten_hex_color(hex_color, lightness_boost=0.16, saturation_boost=0.08):
    """
    Brighten a hex color by adjusting HSL values.
    
    Args:
        hex_color: Color in #RRGGBB format
        lightness_boost: Amount to increase lightness (0-1)
        saturation_boost: Amount to increase saturation (0-1)
    
    Returns:
        Brightened color in #RRGGBB format
    """
    hex_color = hex_color.lstrip('#')
    r, g, b = tuple(int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l = min(1, l + lightness_boost)
    s = min(1, s + saturation_boost)
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"


def darken_hex_color(hex_color, lightness_reduction=0.25):
    """
    Darken a hex color by reducing lightness.
    
    Args:
        hex_color: Color in #RRGGBB format
        lightness_reduction: Amount to reduce lightness (0-1)
    
    Returns:
        Darkened color in #RRGGBB format
    """
    hex_color = hex_color.lstrip('#')
    r, g, b = tuple(int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l = max(0, l - lightness_reduction)
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"


def build_pie_figure(section_data, selected_section):
    """
    Build a 3D donut chart figure showing section progress using PyEcharts.
    
    Args:
        section_data: List of dicts with keys: name, color, total, completed, percent
        selected_section: Name of the currently selected section
    
    Returns:
        dict: PyEcharts options dict configured as a 3D donut chart
    """
    section_names = [d['name'] for d in section_data]
    
    # Prepare data as tuples (name, value)
    data_pairs = [
        (f"{d['name']}\n({int(d['completed'])}/{int(d['total'])})", d['total'])
        for d in section_data
    ]
    
    # Prepare colors list for each slice
    colors = [
        brighten_hex_color(d['color']) if d['name'] == selected_section else d['color']
        for d in section_data
    ]
    
    # Build pie chart
    pie = Pie()
    pie.add(
        "",
        data_pairs,
        radius=["35%", "75%"],  # Donut hole
    )
    
    # Apply colors to the pie series
    pie.set_colors(colors)
    
    # Configure layout with tooltip and legend
    pie.set_global_opts(
        tooltip_opts=opts.TooltipOpts(
            formatter="{b}: items"
        ),
        legend_opts=opts.LegendOpts(
            type_="scroll",
            pos_right="0",
            orient="vertical"
        )
    )
    
    pie.set_series_opts(
        label_opts=opts.LabelOpts(
            position="outside",
            formatter="{b|}{per|}",
            background_color="#fff",
            border_color="#ccc",
            border_width=1,
            rich={
                "b": {"color": "#000", "font_weight": "bold", "font_size": 12},
                "per": {"color": "#666", "padding": [2, 4]}
            }
        ),
        itemstyle_opts=opts.ItemStyleOpts(
            border_width=3,
            border_color="#333"
        )
    )
    
    return pie.dump_options()


def render_pie_with_progress(fig_options, section_data, selected_section, section_names):
    """
    Render 3D pie chart with section progress.
    
    Args:
        fig_options: PyEcharts options dict
        section_data: List of section dicts
        selected_section: Currently selected section name
        section_names: List of all section names
    """
    selected_meta = next((d for d in section_data if d['name'] == selected_section), section_data[0])
    
    # Render 3D chart with streamlit-echarts
    st_echarts(
        options=fig_options,
        height="700px"
    )
    
    # Display center info below chart
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.write("")
    with col2:
        st.markdown(f"""
        <div style="text-align: center; padding: 20px; background-color: #f0f8ff; border-radius: 10px;">
            <h3 style="margin: 0; color: #0F172A;">{selected_meta['name']}</h3>
            <p style="margin: 10px 0; font-size: 18px; color: #333;">
                <strong>{int(selected_meta['completed'])} of {int(selected_meta['total'])} done</strong>
            </p>
            <p style="margin: 0; color: #666;">
                {selected_meta['percent']:.0f}% complete
            </p>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.write("")
