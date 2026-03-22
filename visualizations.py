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
    # Display pie chart with click detection
    if plotly_events:
        st.write("DEBUG: Using plotly_events (no st.plotly_chart call)")
        clicked = plotly_events(fig, click_event=True, key="pie_click_handler", override_height=500)
        st.write(f"DEBUG: clicked = {clicked}, type = {type(clicked)}")
        
        # Process clicks if any occurred
        if clicked and len(clicked) > 0:
            st.write(f"DEBUG: Got {len(clicked)} clicks")
            event = clicked[0]
            st.write(f"DEBUG: event = {event}")
            
            # The event should have a label directly
            if isinstance(event, dict):
                label = event.get('label')
                st.write(f"DEBUG: label = {label}, section_names = {section_names}")
                
                if label and label in section_names:
                    if label != selected_section:
                        st.write(f"DEBUG: Setting selected_section to {label}")
                        st.session_state.selected_section = label
                        st.session_state.selected_section_dropdown = label
                        st.rerun()
    else:
        st.write("DEBUG: plotly_events not available, using fallback")
        st.plotly_chart(fig, use_container_width=True)
    
    # Display progress below chart
    st.markdown("### Section Progress")
    cols = st.columns(2)
    for idx, section in enumerate(section_data):
        progress_line = f"{int(section['completed'])}/{int(section['total'])} done ({section['percent']:.0f}%)"
        with cols[idx % 2]:
            if section['name'] == selected_section:
                st.markdown(f"**{section['name']}**  \n{progress_line}")
            else:
                st.markdown(f"{section['name']}  \n{progress_line}")
