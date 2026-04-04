import os
import json

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from checklist_data import (
    load_checklist_json,
    build_df_from_json,
    reorder_by_json,
    dataframe_signature,
    enforce_ta_forms_order,
)
from cloud_storage import build_store_from_env, load_for_user, save_for_user
from visualizations import (
    build_pie_figure,
    render_pie_with_progress,
    apply_glass_effect_styling,
)
from sidebar_config import render_sidebar


def render_tabulator_view(df: pd.DataFrame, height: int = 420) -> None:
        """Render a read-only Tabulator table inside Streamlit with wrapped text."""
        if df.empty:
                st.info("No rows available for Tabulator view.")
                return

        records = df.fillna("").to_dict(orient="records")
        columns = []
        for col in df.columns:
                col_def = {
                        "title": col,
                        "field": col,
                        "headerSort": False,
                        "resizable": True,
                        "hozAlign": "center" if col in ("Done", "Tested certificate available") else "left",
                }
                if col in ("Done", "Tested certificate available"):
                        col_def["formatter"] = "tickCross"
                        col_def["formatterParams"] = {"allowEmpty": True}
                if col == "Item":
                        col_def["widthGrow"] = 3
                columns.append(col_def)

        html_code = f"""
        <!doctype html>
        <html>
        <head>
            <meta charset='utf-8'>
            <meta name='viewport' content='width=device-width, initial-scale=1'>
            <link href='https://unpkg.com/tabulator-tables@6.2.5/dist/css/tabulator.min.css' rel='stylesheet'>
            <style>
                body {{ margin: 0; font-family: Segoe UI, Tahoma, sans-serif; }}
                #tbl {{ width: 100%; }}
                .tabulator .tabulator-cell {{ white-space: normal; word-break: break-word; line-height: 1.25; }}
            </style>
        </head>
        <body>
            <div id='tbl'></div>
            <script src='https://unpkg.com/tabulator-tables@6.2.5/dist/js/tabulator.min.js'></script>
            <script>
                const tableData = {json.dumps(records)};
                const tableColumns = {json.dumps(columns)};
                new Tabulator('#tbl', {{
                    data: tableData,
                    columns: tableColumns,
                    layout: 'fitDataStretch',
                    responsiveLayout: 'hide',
                    height: '{height}px'
                }});
            </script>
        </body>
        </html>
        """

        components.html(html_code, height=height + 24, scrolling=True)


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

# Clean-start table rendering path: always use Streamlit's native editor.
processed_df = enforce_ta_forms_order(st.session_state.checklist_df.copy())
st.session_state.checklist_df = processed_df

section_names = [s for s in processed_df["Section"].dropna().astype(str).unique().tolist() if s]
if not section_names and "Section" in default_checklist_df.columns:
    section_names = [s for s in default_checklist_df["Section"].dropna().astype(str).unique().tolist() if s]

if "selected_section" not in st.session_state:
    st.session_state.selected_section = "All"

if st.session_state.selected_section != "All" and st.session_state.selected_section not in section_names:
    st.session_state.selected_section = "All"

if section_names:
    section_data = []
    section_colors = ["#E6F3FF", "#E6FFE6", "#FFFFE6", "#FFE6F3", "#F3E6FF", "#FFF3E6"]
    for i, section_name in enumerate(section_names):
        section_df = processed_df[processed_df["Section"] == section_name]
        total = len(section_df)
        completed = int(section_df["Done"].sum()) if "Done" in section_df.columns else 0
        percent = (completed / total * 100) if total > 0 else 0
        section_data.append(
            {
                "name": section_name,
                "total": total,
                "completed": completed,
                "percent": percent,
                "color": section_colors[i % len(section_colors)],
            }
        )

    donut_selected = st.session_state.selected_section if st.session_state.selected_section in section_names else section_names[0]
    fig_options = build_pie_figure(section_data, donut_selected)
    render_pie_with_progress(fig_options, section_data, donut_selected, section_names)
    st.write("---")

controls = st.columns([2, 1, 1])
with controls[0]:
    dropdown_options = ["All"] + section_names
    selected_section = st.selectbox(
        "Section",
        options=dropdown_options,
        index=dropdown_options.index(st.session_state.selected_section) if st.session_state.selected_section in dropdown_options else 0,
        key="selected_section",
    )

with controls[1]:
    show_all = st.checkbox("Show all data", value=(selected_section == "All"), key="show_all")

with controls[2]:
    show_section_col = st.checkbox("Show Section column", value=True, key="show_section_col")

if show_all or selected_section == "All":
    display_df = processed_df.copy()
else:
    display_df = processed_df[processed_df["Section"] == selected_section].copy()

st.caption(f"Current account: {st.session_state.get('cloud_user_input', st.session_state.active_user_id) or 'not set'}")
st.subheader(f"Checklist table: {'All sections' if show_all or selected_section == 'All' else selected_section}")

if display_df.empty:
    st.info("No checklist rows to display.")
else:
    editor_df = display_df.copy()
    if not show_section_col and "Section" in editor_df.columns:
        editor_df = editor_df.drop(columns=["Section"])

    with st.expander("Tabulator view", expanded=False):
        st.caption("Tabulator grid is read-only in this Streamlit embed. Edit data in the table below.")
        render_tabulator_view(editor_df, height=460)

    editable_cols = ["Done", "Pending With", "Date Completed", "Notes", "Tested certificate available"]
    edited_df = st.data_editor(
        editor_df,
        use_container_width=True,
        hide_index=True,
        disabled=[c for c in editor_df.columns if c not in editable_cols],
        key="checklist_data_editor",
    )

    if st.button("Save data", key="checklist_save_btn"):
        if show_all or selected_section == "All":
            st.session_state.checklist_df[editable_cols] = edited_df[editable_cols].values
        else:
            mask = st.session_state.checklist_df["Section"] == selected_section
            st.session_state.checklist_df.loc[mask, editable_cols] = edited_df[editable_cols].values

        st.session_state.last_saved_signature = dataframe_signature(st.session_state.checklist_df)

        current_user = st.session_state.get("cloud_user_input", "").strip() or st.session_state.active_user_id
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


