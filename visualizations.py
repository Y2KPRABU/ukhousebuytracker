"""
Visualization components for the House Buying Checklist app.
Handles pie/donut charts, progress displays, and related chart utilities.
"""

import colorsys
import streamlit as st
import plotly.graph_objects as go
from streamlit_plotly_events import plotly_events


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


def build_pie_figure(section_data, selected_section):
    """
    Build a donut chart figure showing section progress.
    
    Args:
        section_data: List of dicts with keys: name, color, total, completed, percent
        selected_section: Name of the currently selected section
    
    Returns:
        plotly.graph_objects.Figure configured as a donut chart with center annotation
    """
    section_names = [d['name'] for d in section_data]
    
    # Highlight selected section with pull and brighten effect
    pulls = [0.14 if s == selected_section else 0.02 for s in section_names]
    border_colors = ['#334155' if s == selected_section else '#475569' for s in section_names]
    slice_colors = [
        brighten_hex_color(d['color']) if d['name'] == selected_section else d['color']
        for d in section_data
    ]
    
    # Custom data for hover template
    pie_custom_data = [
        [int(d['completed']), int(d['total']), float(d['percent'])]
        for d in section_data
    ]
    
    # Get metrics for center annotation
    selected_meta = next((d for d in section_data if d['name'] == selected_section), section_data[0])
    
    fig = go.Figure()
    fig.add_trace(go.Pie(
        labels=section_names,
        values=[d['total'] for d in section_data],
        textinfo='label+percent',
        textposition='outside',
        textfont=dict(size=14, color='black', family='Arial', weight='bold'),
        customdata=pie_custom_data,
        hovertemplate=(
            "%{label}<br>"
            "%{customdata[0]} of %{customdata[1]} done "
            "(%{customdata[2]:.0f}% complete)<extra></extra>"
        ),
        marker=dict(
            colors=slice_colors,
            line=dict(color=border_colors, width=5)
        ),
        pull=pulls,
        hole=0.42,
        sort=False,
        direction='clockwise'
    ))
    
    fig.update_layout(
        showlegend=False,
        height=500,
        margin=dict(t=20, b=20, l=30, r=30),
        annotations=[
            dict(
                text=(
                    f"<b>{selected_meta['name']}</b><br>"
                    f"{int(selected_meta['completed'])} of {int(selected_meta['total'])} done<br>"
                    f"{selected_meta['percent']:.0f}% complete"
                ),
                x=0.5,
                y=0.5,
                showarrow=False,
                font=dict(size=14, color='#0F172A')
            )
        ]
    )
    
    return fig


def render_pie_with_progress(fig, section_data, selected_section, section_names):
    """
    Render pie chart with click-to-select and a side progress panel.
    Handles click events and updates session state.
    
    Args:
        fig: plotly Figure object
        section_data: List of section dicts
        selected_section: Currently selected section name
        section_names: List of all section names
    """
    chart_cols = st.columns([1.6, 1])
    
    with chart_cols[0]:
        # Render pie chart with click detection
        if plotly_events:
            clicked = plotly_events(fig, click_event=True, key='pie_click')
            if clicked and isinstance(clicked, list) and len(clicked) > 0:
                first_event = clicked[0]
                point = first_event
                if isinstance(first_event, dict) and 'points' in first_event and first_event['points']:
                    point = first_event['points'][0]
                
                if isinstance(point, dict):
                    candidate = point.get('label') or point.get('x') or point.get('y')
                    selected_from_pie = candidate if candidate in section_names else selected_section
                    
                    if not candidate:
                        point_index = point.get('pointNumber', point.get('pointIndex'))
                        if isinstance(point_index, int) and 0 <= point_index < len(section_names):
                            selected_from_pie = section_names[point_index]
                    
                    if selected_from_pie in section_names and selected_from_pie != selected_section:
                        st.session_state.selected_section = selected_from_pie
                        st.session_state.selected_section_dropdown = selected_from_pie
                        st.rerun()
        else:
            st.plotly_chart(fig, use_container_width=True)
    
    # Right column: Progress panel
    with chart_cols[1]:
        st.markdown("### Section Progress")
        for section in section_data:
            progress_line = f"{int(section['completed'])}/{int(section['total'])} done ({section['percent']:.0f}%)"
            if section['name'] == selected_section:
                st.markdown(f"**{section['name']}**  \\\n{progress_line}")
            else:
                st.markdown(f"{section['name']}  \\\n{progress_line}")
