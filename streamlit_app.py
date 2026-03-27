import os
import textwrap

import streamlit as st

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
    expected = ["Section", "Item", "Done", "Pending With", "Date Completed", "Notes", "Tested certificate available"]
    missing = [col for col in expected if col not in df.columns]
    if missing:
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

            with st.form("checklist_edit_form", clear_on_submit=False):
                editor_df = display_df.copy()

                # Streamlit's grid renderer does not reliably CSS-wrap canvas text,
                # so inject line breaks for display to keep Item readable in-table.
                if 'Item' in editor_df.columns:
                    editor_df['Item'] = editor_df['Item'].apply(
                        lambda v: textwrap.fill(str(v), width=56, break_long_words=False)
                    )
                if show_section_col and 'Section' in editor_df.columns:
                    editor_df['Section'] = editor_df['Section'].apply(
                        lambda v: textwrap.fill(str(v), width=28, break_long_words=False)
                    )

                if not show_section_col and 'Section' in editor_df.columns:
                    editor_df = editor_df.drop(columns=['Section'])

                column_config = {
                    'Item': st.column_config.TextColumn('Item', disabled=True, width="large"),
                    'Done': st.column_config.CheckboxColumn('Done'),
                    'Pending With': st.column_config.TextColumn('Pending With', width="small"),
                    'Date Completed': st.column_config.TextColumn('Date Completed', width="small"),
                    'Notes': st.column_config.TextColumn('Notes', width="medium"),
                    'Tested certificate available': st.column_config.CheckboxColumn('Tested certificate available')
                }
                if show_section_col:
                    column_config['Section'] = st.column_config.TextColumn('Section', disabled=True, width="medium")

                edited_df = st.data_editor(
                    editor_df,
                    width='stretch',
                    num_rows='dynamic',
                    row_height=64,
                    column_config=column_config
                )
                save_clicked = st.form_submit_button("Save data")

            if save_clicked:
                # Only update editable columns — never overwrite Item/Section from canvas output
                editable_cols = ['Done', 'Pending With', 'Date Completed', 'Notes', 'Tested certificate available']
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


