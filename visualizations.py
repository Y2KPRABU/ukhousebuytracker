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
    Build a donut chart figure showing section progress with 3D visual effects.
    Includes gradient-like effects, drop shadows, and depth styling.
    
    Args:
        section_data: List of dicts with keys: name, color, total, completed, percent
        selected_section: Name of the currently selected section
    
    Returns:
        plotly.graph_objects.Figure configured as a donut chart with visual depth effects
    """
    section_names = [d['name'] for d in section_data]
    
    # Slice colors with opacity for depth
    slice_colors = []
    for d in section_data:
        base_color = brighten_hex_color(d['color']) if d['name'] == selected_section else d['color']
        hex_color = base_color.lstrip('#')
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        opacity = 1.0 if d['name'] == selected_section else 0.85
        slice_colors.append(f"rgba({r}, {g}, {b}, {opacity})")
    
    # Create layered border effect: dark color + slate/grey accent
    border_colors = []
    for d in section_data:
        # Darken the base color
        dark_color = darken_hex_color(d['color'], lightness_reduction=0.35)
        border_colors.append(dark_color)
    
    # Slate/grey accent colors for enhanced contrast
    slate_accents = ['#64748b', '#475569', '#334155', '#1e293b', '#0f172a', '#020617']
    
    # Custom data for hover template and labels
    pie_custom_data = [
        [int(d['completed']), int(d['total'])]
        for d in section_data
    ]
    
    # Create multiline labels with progress info
    labels_with_progress = [
        f"{d['name']}<br>({int(d['completed'])}/{int(d['total'])})"
        for d in section_data
    ]
    
    # Get metrics for center annotation
    selected_meta = next((d for d in section_data if d['name'] == selected_section), section_data[0])
    
    fig = go.Figure()
    
    # Add shadow trace for depth effect
    fig.add_trace(go.Pie(
        labels=labels_with_progress,
        values=[d['total'] for d in section_data],
        textinfo='none',
        customdata=pie_custom_data,
        marker=dict(
            colors=['rgba(50, 50, 50, 0.15)' for _ in section_data],
            line=dict(color=['rgba(30, 41, 59, 0.2)' for _ in section_data], width=2)
        ),
        hole=0.42,
        sort=False,
        direction='clockwise',
        hoverinfo='skip'
    ))
    
    # Add main pie trace with enhanced borders
    fig.add_trace(go.Pie(
        labels=labels_with_progress,
        values=[d['total'] for d in section_data],
        textinfo='label+percent',
        textposition='outside',
        textfont=dict(size=12, color='black', family='Arial', weight='bold'),
        customdata=pie_custom_data,
        hovertemplate="%{customdata[0]} of %{customdata[1]} done<extra></extra>",
        marker=dict(
            colors=slice_colors,
            line=dict(
                color=border_colors,
                width=8
            )
        ),
        pull=[0.15 if s == selected_section else 0.02 for s in section_names],
        hole=0.42,
        sort=False,
        direction='clockwise'
    ))
    
    fig.update_layout(
        showlegend=False,
        height=700,
        margin=dict(t=40, b=40, l=80, r=80),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(250,250,252,0.5)',
        annotations=[
            dict(
                text=(
                    f"<b>{selected_meta['name']}</b><br>"
                    f"{int(selected_meta['completed'])} of {int(selected_meta['total'])} done"
                ),
                x=0.5,
                y=0.5,
                showarrow=False,
                font=dict(size=14, color='#0F172A', family='Arial')
            )
        ]
    )
    
    return fig


def render_pie_with_progress(fig, section_data, selected_section, section_names):
    """
    Render pie chart with click-to-select functionality.
    Progress info is embedded in the pie labels and center annotation.
    
    Args:
        fig: plotly Figure object
        section_data: List of section dicts
        selected_section: Currently selected section name
        section_names: List of all section names
    """
    # Display pie chart with click detection
    if plotly_events:
        clicked = plotly_events(fig, click_event=True, key="pie_click_handler", override_height=700)
        
        # Process clicks if any occurred
        if clicked and len(clicked) > 0:
            event = clicked[0]
            
            # Extract pointNumber which is the index into section_names
            if isinstance(event, dict):
                point_number = event.get('pointNumber')
                
                if point_number is not None and isinstance(point_number, int):
                    if 0 <= point_number < len(section_names):
                        label = section_names[point_number]
                        if label != selected_section:
                            st.session_state.selected_section = label
                            st.session_state.selected_section_dropdown = label
                            st.rerun()
    else:
        st.plotly_chart(fig, use_container_width=True)
