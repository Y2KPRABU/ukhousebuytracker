import os
import traceback

import pandas as pd
import streamlit as st

try:
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
except Exception:
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
from visualizations import (
    build_pie_figure,
    render_pie_with_progress,
    apply_glass_effect_styling,
)
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

    st.caption(f"Grid input: {len(editor_df)} rows x {len(editor_df.columns)} columns")

    editable_cols = ["Done", "Pending With", "Date Completed", "Notes", "Tested certificate available"]
    if AgGrid is None or GridOptionsBuilder is None or GridUpdateMode is None:
        st.error("AgGrid is not available. Install/repair streamlit-aggrid and reload the app.")
        st.stop()

    try:
        gb = GridOptionsBuilder.from_dataframe(editor_df)
        gb.configure_default_column(resizable=True, sortable=False, filter=False)

        if "Section" in editor_df.columns:
            gb.configure_column(
                "Section",
                editable=False,
                width=220,
            )
        if "Item" in editor_df.columns:
            gb.configure_column(
                "Item",
                editable=False,
                width=560,
            )
        if "Initiator" in editor_df.columns:
            gb.configure_column(
                "Initiator",
                editable=False,
                width=170,
            )
        if "Done" in editor_df.columns:
            gb.configure_column("Done", editable=True, cellRenderer="agCheckboxCellRenderer", cellEditor="agCheckboxCellEditor", width=100)
        if "Pending With" in editor_df.columns:
            gb.configure_column(
                "Pending With",
                editable=True,
                width=190,
            )
        if "Date Completed" in editor_df.columns:
            gb.configure_column("Date Completed", editable=True, width=150)
        if "Notes" in editor_df.columns:
            gb.configure_column(
                "Notes",
                editable=True,
                width=360,
            )
        if "Tested certificate available" in editor_df.columns:
            gb.configure_column(
                "Tested certificate available",
                editable=True,
                cellRenderer="agCheckboxCellRenderer",
                cellEditor="agCheckboxCellEditor",
                width=200,
            )

        gb.configure_grid_options(
            rowHeight=44,
            suppressHorizontalScroll=False,
            domLayout="normal",
        )

        item_wrap_css = {
            ".ag-theme-streamlit .ag-cell[col-id='Item']": {
                "white-space": "normal !important",
                "line-height": "1.25 !important",
                "word-break": "break-word !important",
            },
            ".ag-theme-streamlit .ag-cell[col-id='Item'] .ag-cell-value": {
                "white-space": "normal !important",
                "line-height": "1.25 !important",
                "word-break": "break-word !important",
            },
        }

        grid_response = AgGrid(
            editor_df,
            gridOptions=gb.build(),
            theme="streamlit",
            height=620,
            fit_columns_on_grid_load=False,
            update_mode=GridUpdateMode.VALUE_CHANGED,
            allow_unsafe_jscode=False,
            reload_data=False,
            custom_css=item_wrap_css,
            key=f"checklist_aggrid_{selected_section}_{show_all}_{show_section_col}",
        )
        edited_df = pd.DataFrame(grid_response.get("data", editor_df))
    except Exception as err:
        st.error(f"AgGrid render error: {type(err).__name__}: {err}")
        st.code(traceback.format_exc(), language="text")
        st.stop()

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


