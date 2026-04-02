import os

import pandas as pd
import streamlit as st

try:
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
    AGGRID_AVAILABLE = True
except Exception:
    AGGRID_AVAILABLE = False
    AgGrid = None
    GridOptionsBuilder = None
    GridUpdateMode = None

from checklist_data import (
    load_checklist_json,
    build_df_from_json,
    reorder_by_json,
    dataframe_signature,
    enforce_ta_forms_order,
)
from cloud_storage import build_store_from_env, load_for_user, save_for_user
from visualizations import build_pie_figure, render_pie_with_progress, apply_glass_effect_styling
from sidebar_config import render_sidebar


def bootstrap_env_from_streamlit_secrets():
    """Map Streamlit secrets to environment variables for cloud storage setup."""
    try:
        secrets_map = dict(st.secrets)
    except Exception:
        # Local runs may not have a secrets file yet; skip bootstrap quietly.
        return

    keys = [
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_ANON_KEY",
        "SUPABASE_CHECKLIST_TABLE",
        "USER_ID",
    ]
    for key in keys:
        if not os.getenv(key) and key in secrets_map:
            os.environ[key] = str(secrets_map[key])


bootstrap_env_from_streamlit_secrets()


st.set_page_config(
    page_title="UK Resale House Buying Checklist",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": "https://docs.streamlit.io/",
        "Report a bug": "https://github.com/streamlit/streamlit/issues",
        "About": (
            "UK House Buying Checklist\n"
            "Track your home-buying journey from offer to keys, including searches,"
            " exchange, and completion milestones."
        ),
    },
)

# Apply glass effect styling
apply_glass_effect_styling()

st.html(
    "<h1 style='margin:0 0 2px 0; padding:0; font-size:1.6rem; line-height:1.2;'>"
    "\U0001f3e0 UK Resale House Buying Checklist</h1>"
    "<p style='margin:0 0 8px 0; padding:0; color:#64748b; font-size:0.9rem;'>"
    "Track your journey from offer to keys.</p>"
)

DATA_FILE = "housebuy_checklist.json"
DEFAULT_SHEET_NAME = "Checklist"

data = load_checklist_json(DATA_FILE)
if not os.path.exists(DATA_FILE):
    st.warning(f"Checklist file '{DATA_FILE}' not found. Using default checklist.")


cloud_store = build_store_from_env()
default_checklist_df = build_df_from_json(data)

if "checklist_df" not in st.session_state:
    st.session_state.checklist_df = default_checklist_df

if "active_user_id" not in st.session_state:
    st.session_state.active_user_id = os.getenv("USER_ID", "").strip()

if "autosave_cloud" not in st.session_state:
    st.session_state.autosave_cloud = False

if "last_saved_signature" not in st.session_state:
    st.session_state.last_saved_signature = dataframe_signature(st.session_state.checklist_df)

if "cloud_status" not in st.session_state:
    st.session_state.cloud_status = ""

# Google Sheets helpers
try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    gspread = None

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_gsheet_client(service_account_info):
    if gspread is None:
        raise RuntimeError("Missing gspread/google-auth package. Install via requirements.")

    credentials = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
    return gspread.authorize(credentials)


def get_or_create_worksheet(spreadsheet, title):
    try:
        worksheet = spreadsheet.worksheet(title)
    except Exception:
        worksheet = spreadsheet.add_worksheet(title=title, rows=1000, cols=20)
    return worksheet


def load_sheet_to_df(spreadsheet_id, sheet_name, client):
    spreadsheet = client.open_by_key(spreadsheet_id)
    worksheet = get_or_create_worksheet(spreadsheet, sheet_name)
    records = worksheet.get_all_records()
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    expected = ["Section", "Item", "Initiator", "Done", "Pending With", "Date Completed", "Notes", "Tested certificate available"]
    missing = [col for col in expected if col not in df.columns]
    if missing:
        # Backward compatibility for older sheets that predate Initiator.
        if missing == ["Initiator"]:
            df["Initiator"] = "NA"
        else:
            st.warning(f"Google Sheet missing columns: {missing}. Using JSON default schema.")
            return pd.DataFrame()
    return df[expected]


def write_df_to_sheet(df, spreadsheet_id, sheet_name, client):
    spreadsheet = client.open_by_key(spreadsheet_id)
    worksheet = get_or_create_worksheet(spreadsheet, sheet_name)

    headers = df.columns.tolist()
    values = [headers] + df.fillna("").astype(str).values.tolist()
    worksheet.clear()
    worksheet.update(values)


# Render sidebar with cloud and Google Sheets configuration
render_sidebar(
    cloud_store,
    default_checklist_df,
    DATA_FILE,
    DEFAULT_SHEET_NAME,
    dataframe_signature,
    get_gsheet_client,
    load_sheet_to_df,
    write_df_to_sheet,
)

# Main interactive editor hidden as per request

# Reorder rows to always match the JSON definition order before displaying
st.session_state.checklist_df = reorder_by_json(st.session_state.checklist_df, data)

# Calculate section statistics
processed_df = enforce_ta_forms_order(st.session_state.checklist_df.copy())
st.session_state.checklist_df = processed_df

section_data = []
section_colors = ['#E6F3FF', '#E6FFE6', '#FFFFE6', '#FFE6F3', '#F3E6FF', '#FFF3E6']  # light blue, green, yellow, pink, purple, orange
color_map = {}
for i, section_name in enumerate(data.keys()):
    color_map[section_name] = section_colors[i % len(section_colors)]

# Ensure section order exactly follows the JSON definition
section_order = list(data.keys())
for section_name in section_order:
    section_df = processed_df[processed_df["Section"] == section_name]
    if not section_df.empty:
        total = len(section_df)
        completed = section_df["Done"].sum()
        percent = (completed / total * 100) if total > 0 else 0
        section_data.append({
            'name': section_name,
            'total': total,
            'completed': completed,
            'percent': percent,
            'color': color_map[section_name]
        })

# Fallback: if incoming data has section names that don't match JSON keys,
# still render a table and section selector from the data itself.
if not section_data and not processed_df.empty and "Section" in processed_df.columns:
    dynamic_sections = [s for s in processed_df["Section"].dropna().astype(str).unique().tolist() if s]
    for i, section_name in enumerate(dynamic_sections):
        section_df = processed_df[processed_df["Section"] == section_name]
        total = len(section_df)
        completed = int(section_df["Done"].sum()) if "Done" in section_df.columns else 0
        percent = (completed / total * 100) if total > 0 else 0
        section_data.append({
            'name': section_name,
            'total': total,
            'completed': completed,
            'percent': percent,
            'color': section_colors[i % len(section_colors)]
        })

if section_data:
    section_names = [d['name'] for d in section_data]

    # Ensure a default selected section exists
    if 'selected_section' not in st.session_state:
        st.session_state.selected_section = section_names[0] if section_names else 'All'
    elif st.session_state.selected_section not in section_names and st.session_state.selected_section != 'All':
        st.session_state.selected_section = section_names[0] if section_names else 'All'

    # Keep dropdown state aligned before rendering the selectbox widget.
    if (
        'selected_section_dropdown' not in st.session_state
        or st.session_state.selected_section_dropdown not in (['All'] + section_names)
        or st.session_state.selected_section_dropdown != st.session_state.selected_section
    ):
        st.session_state.selected_section_dropdown = st.session_state.selected_section

    @st.fragment
    def pie_and_table(section_data, section_names, processed_df):
        selected_section = st.session_state.get('selected_section', section_names[0])

        # Build and render pie chart
        fig_options = build_pie_figure(section_data, selected_section)
        render_pie_with_progress(fig_options, section_data, selected_section, section_names)

        st.write("---")
        cols = st.columns([1, 1, 1])
        with cols[0]:
            dropdown_options = ['All'] + section_names
            dropdown_index = dropdown_options.index(selected_section) if selected_section in dropdown_options else 0
            selected_section = st.selectbox(
                "Select section (or 'All' for everything)",
                options=dropdown_options,
                index=dropdown_index,
                key='selected_section_dropdown'
            )
            st.session_state.selected_section = selected_section

        with cols[1]:
            show_all = st.checkbox("Show all data", value=st.session_state.get('show_all', False))
            st.session_state.show_all = show_all

        with cols[2]:
            show_section_col = st.checkbox(
                "Show Section column",
                value=st.session_state.get('show_section_col', False)
            )
            st.session_state.show_section_col = show_section_col

        if show_all or selected_section == 'All':
            display_df = processed_df
        else:
            display_df = processed_df[processed_df['Section'] == selected_section] if selected_section in section_names else pd.DataFrame()

        if not display_df.empty:
            st.caption(f"Current account: {st.session_state.get('cloud_user_input', st.session_state.active_user_id) or 'not set'}")
            st.subheader(f"Checklist table: { 'All sections' if show_all else selected_section }")

            editor_df = display_df.copy()
            if not show_section_col and 'Section' in editor_df.columns:
                editor_df = editor_df.drop(columns=['Section'])

            editable_cols = ['Done', 'Pending With', 'Date Completed', 'Notes', 'Tested certificate available']
            if AGGRID_AVAILABLE:
                try:
                    gb = GridOptionsBuilder.from_dataframe(editor_df)
                    gb.configure_default_column(resizable=True, sortable=False, filter=False)

                    if 'Section' in editor_df.columns:
                        gb.configure_column('Section', editable=False, wrapText=True, autoHeight=True, width=210)
                    if 'Item' in editor_df.columns:
                        gb.configure_column('Item', editable=False, wrapText=True, autoHeight=True, width=520)
                    if 'Initiator' in editor_df.columns:
                        gb.configure_column('Initiator', editable=False, width=140)
                    if 'Done' in editor_df.columns:
                        gb.configure_column('Done', editable=True, cellRenderer='agCheckboxCellRenderer', cellEditor='agCheckboxCellEditor', width=95)
                    if 'Pending With' in editor_df.columns:
                        gb.configure_column('Pending With', editable=True, width=150)
                    if 'Date Completed' in editor_df.columns:
                        gb.configure_column('Date Completed', editable=True, width=150)
                    if 'Notes' in editor_df.columns:
                        gb.configure_column('Notes', editable=True, wrapText=True, autoHeight=True, width=260)
                    if 'Tested certificate available' in editor_df.columns:
                        gb.configure_column(
                            'Tested certificate available',
                            editable=True,
                            cellRenderer='agCheckboxCellRenderer',
                            cellEditor='agCheckboxCellEditor',
                            width=170,
                        )

                    gb.configure_grid_options(
                        rowHeight=42,
                        suppressHorizontalScroll=False,
                        ensureDomOrder=True,
                    )

                    grid_response = AgGrid(
                        editor_df,
                        gridOptions=gb.build(),
                        height=560,
                        theme='streamlit',
                        fit_columns_on_grid_load=False,
                        update_mode=GridUpdateMode.VALUE_CHANGED,
                        allow_unsafe_jscode=True,
                        reload_data=False,
                        key=f"checklist_grid_{selected_section}_{show_all}_{show_section_col}",
                    )
                    edited_df = pd.DataFrame(grid_response.get('data', editor_df))
                except Exception:
                    st.warning("Grid component unavailable, using built-in table editor instead.")
                    edited_df = st.data_editor(
                        editor_df,
                        use_container_width=True,
                        hide_index=True,
                        disabled=[c for c in editor_df.columns if c not in editable_cols],
                        key=f"checklist_data_editor_{selected_section}_{show_all}_{show_section_col}",
                    )
            else:
                st.info("Using built-in table editor.")
                edited_df = st.data_editor(
                    editor_df,
                    use_container_width=True,
                    hide_index=True,
                    disabled=[c for c in editor_df.columns if c not in editable_cols],
                    key=f"checklist_data_editor_{selected_section}_{show_all}_{show_section_col}",
                )

            save_clicked = st.button('Save data', key='checklist_save_btn')

            if save_clicked:
                # Only update editable columns — never overwrite Item/Section from canvas output
                if show_all:
                    st.session_state.checklist_df[editable_cols] = edited_df[editable_cols].values
                else:
                    mask = st.session_state.checklist_df['Section'] == selected_section
                    st.session_state.checklist_df.loc[mask, editable_cols] = edited_df[editable_cols].values

                st.session_state.last_saved_signature = dataframe_signature(st.session_state.checklist_df)

                current_user = st.session_state.get("cloud_user_input", "").strip() or st.session_state.active_user_id
                if not current_user:
                    st.warning(
                        "⚠️ **No Account ID set!** Your changes have been saved locally in this session, "
                        "but they won't be saved to persistent storage. "
                        "Please set an Account ID in the sidebar 'Account & Cloud Save' section to save to cloud."
                    )
                if current_user:
                    ok, message = save_for_user(cloud_store, current_user, st.session_state.checklist_df)
                    if ok:
                        st.session_state.active_user_id = current_user
                        st.session_state.cloud_status = f"Saved to {cloud_store.backend_name}."
                    else:
                        st.session_state.cloud_status = f"Save failed: {message}"
                else:
                    st.session_state.cloud_status = "Saved in app session. Set Account ID to persist to storage."

                st.rerun()
        else:
            st.info("No checklist rows to display for this section.")

    pie_and_table(section_data, section_names, processed_df)

if st.session_state.autosave_cloud and st.session_state.active_user_id:
    current_signature = dataframe_signature(st.session_state.checklist_df)
    if current_signature != st.session_state.last_saved_signature:
        ok, message = save_for_user(cloud_store, st.session_state.active_user_id, st.session_state.checklist_df)
        if ok:
            st.session_state.last_saved_signature = current_signature
            st.session_state.cloud_status = f"Autosaved to {cloud_store.backend_name}."
        else:
            st.session_state.cloud_status = f"Autosave failed: {message}"

# no explicit progress info displayed now


