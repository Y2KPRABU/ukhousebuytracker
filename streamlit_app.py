import json
import os

import pandas as pd
import streamlit as st

from cloud_storage import build_store_from_env, load_for_user, save_for_user
from visualizations import build_pie_figure, render_pie_with_progress


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
    page_title="UK House Buying Checklist",
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

st.title("🏠 UK House Buying Checklist")
st.write("Track your journey from offer to keys.")

DATA_FILE = "housebuy_checklist.json"
DEFAULT_SHEET_NAME = "Checklist"

# Load checklist definition from JSON
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
else:
    st.warning(f"Checklist file '{DATA_FILE}' not found. Using default checklist.")
    data = {
        "Initial Stage": [
            "Memorandum of Sale (from Agent)",
            "ID & AML Checks (Passport/Address)",
            "Client Care Pack (Signed)"
        ],
        "Legal & Searches": [
            "TA6 Property Info Form (Check FENSA)",
            "TA10 Fittings/Contents Form",
            "Local Authority & Environmental Searches",
            "Report on Title (Read & Signed)"
        ],
        "Exchange & Completion": [
            "Buildings Insurance (Active today!)",
            "Transfer Deed (TR1) Signed",
            "Exchange Deposit Paid",
            "Completion Statement Received",
            "Key Collection"
        ]
    }

# Build a DataFrame with required columns
def build_df_from_json(checklist_data):
    rows = []
    for section, items in checklist_data.items():
        for item in items:
            rows.append({
                "Section": section,
                "Item": item,
                "Done": False,
                "Pending With": "",
                "Date Completed": "",
                "Notes": "",
                "Tested certificate available": False
            })
    return pd.DataFrame(rows)





def dataframe_signature(df):
    """Create a stable signature so autosave runs only when table content changes."""
    as_text = df.fillna("").astype(str)
    return str(pd.util.hash_pandas_object(as_text, index=True).sum())


def enforce_ta_forms_order(df):
    """If solicitor has been instructed, ensure TA6/TA10 are in Legal & Searches and prioritized."""
    if "Item" not in df.columns or "Done" not in df.columns:
        return df

    instruct_idx = df.index[df["Item"] == "Instruct solicitor"]
    if len(instruct_idx) and df.at[instruct_idx[0], "Done"]:
        # move TA6/TA10 into Legal & Searches
        for ta_item in ["TA6 Property Info Form (Check FENSA)", "TA10 Fittings/Contents Form"]:
            if ta_item in df["Item"].values:
                ta_idx = df.index[df["Item"] == ta_item][0]
                df.at[ta_idx, "Section"] = "Legal & Searches"

        # Reorder so Legal & Searches rows come after the current section with not-done tasks
        legal_rows = df[df["Section"] == "Legal & Searches"]
        other_rows = df[df["Section"] != "Legal & Searches"]
        df = pd.concat([other_rows, legal_rows], ignore_index=True)

    return df


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


# Sidebar config for account cloud persistence
st.sidebar.header("Account & Cloud Save")
cloud_user_input = st.sidebar.text_input(
    "Account ID (email or username)",
    value=st.session_state.active_user_id,
    key="cloud_user_input",
)
st.session_state.autosave_cloud = st.sidebar.checkbox(
    "Autosave account checklist (can be slow)",
    value=st.session_state.autosave_cloud,
)

if st.sidebar.button("Load account data"):
    loaded_df, source = load_for_user(cloud_store, cloud_user_input, default_checklist_df)
    st.session_state.checklist_df = loaded_df
    st.session_state.active_user_id = cloud_user_input.strip()
    st.session_state.last_saved_signature = dataframe_signature(loaded_df)
    st.session_state.cloud_status = f"Loaded {source} data using {cloud_store.backend_name}."
    st.rerun()

if st.sidebar.button("Save account data"):
    ok, message = save_for_user(cloud_store, cloud_user_input, st.session_state.checklist_df)
    if ok:
        st.session_state.active_user_id = cloud_user_input.strip()
        st.session_state.last_saved_signature = dataframe_signature(st.session_state.checklist_df)
        st.session_state.cloud_status = f"Saved to {cloud_store.backend_name}."
    else:
        st.session_state.cloud_status = f"Save failed: {message}"

# One-time default load for the active account on first run.
if "cloud_bootstrap_done" not in st.session_state:
    if st.session_state.active_user_id:
        loaded_df, source = load_for_user(cloud_store, st.session_state.active_user_id, default_checklist_df)
        st.session_state.checklist_df = loaded_df
        st.session_state.last_saved_signature = dataframe_signature(loaded_df)
        st.session_state.cloud_status = f"Loaded {source} data using {cloud_store.backend_name}."
    st.session_state.cloud_bootstrap_done = True

if st.session_state.cloud_status:
    st.sidebar.caption(st.session_state.cloud_status)

st.sidebar.caption(f"Storage backend: {cloud_store.backend_name}")

# Sidebar config for Google Sheets linking
st.sidebar.header("Google Sheets integration")
spreadsheet_id = st.sidebar.text_input("Spreadsheet ID", value=os.getenv("GOOGLE_SHEET_ID", ""))
user_id = st.sidebar.text_input("User identifier (email or username)", value=st.session_state.active_user_id)

if user_id.strip():
    # sanitize worksheet name
    sanitized = user_id.strip().replace("@", "_at_").replace(" ", "_").replace("/", "_").replace("\\", "_")
    sheet_name = st.sidebar.text_input("Worksheet name", value=f"{DEFAULT_SHEET_NAME}_{sanitized}")
else:
    sheet_name = st.sidebar.text_input("Worksheet name", value=DEFAULT_SHEET_NAME)

credentials_text = st.sidebar.text_area("Service Account JSON (paste content here)", height=180)
credentials_file = st.sidebar.file_uploader("Or upload service_account.json", type="json")

service_account_info = None
if credentials_file is not None:
    try:
        service_account_info = json.load(credentials_file)
    except Exception as err:
        st.sidebar.error(f"Invalid uploaded JSON: {err}")
elif credentials_text:
    try:
        service_account_info = json.loads(credentials_text)
    except Exception as err:
        st.sidebar.error(f"Invalid JSON text: {err}")

if st.sidebar.button("Load from Google Sheets"):
    if not spreadsheet_id or not sheet_name or service_account_info is None:
        st.sidebar.warning("Provide Spreadsheet ID, worksheet name/user ID, and service account credentials first.")
    else:
        try:
            client = get_gsheet_client(service_account_info)
            loaded_df = load_sheet_to_df(spreadsheet_id, sheet_name, client)
            if loaded_df.empty:
                st.sidebar.info("No valid data found in Google Sheet tab; using local checklist defaults.")
            else:
                st.session_state.checklist_df = loaded_df
                st.rerun()
        except Exception as err:
            st.sidebar.error(f"Unable to load Google Sheet: {err}")

if st.sidebar.button("Save to Google Sheets"):
    if not spreadsheet_id or not sheet_name or service_account_info is None:
        st.sidebar.warning("Provide Spreadsheet ID, worksheet name/user ID, and service account credentials first.")
    else:
        try:
            client = get_gsheet_client(service_account_info)
            write_df_to_sheet(st.session_state.checklist_df, spreadsheet_id, sheet_name, client)
            st.sidebar.success(f"Checklist saved to Google Sheets tab '{sheet_name}'.")
        except Exception as err:
            st.sidebar.error(f"Unable to save to Google Sheet: {err}")

st.sidebar.info("Tip: Ensure your buildings insurance is active from the moment of **Exchange**, not Completion!")
st.sidebar.write("### Data source")
st.sidebar.write(f"Loaded from `{DATA_FILE}`")

# Main interactive editor hidden as per request

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
        cols = st.columns([1, 1])
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

        if show_all or selected_section == 'All':
            display_df = processed_df
        else:
            display_df = processed_df[processed_df['Section'] == selected_section] if selected_section in section_names else pd.DataFrame()

        if not display_df.empty:
            st.caption(f"Current account: {st.session_state.get('cloud_user_input', st.session_state.active_user_id) or 'not set'}")
            st.subheader(f"Checklist table: { 'All sections' if show_all else selected_section }")
            with st.form("checklist_edit_form", clear_on_submit=False):
                edited_df = st.data_editor(
                    display_df,
                    width='stretch',
                    num_rows='dynamic',
                    column_config={
                        'Section': st.column_config.TextColumn('Section', disabled=True),
                        'Item': st.column_config.TextColumn('Item', disabled=True),
                        'Done': st.column_config.CheckboxColumn('Done'),
                        'Pending With': st.column_config.TextColumn('Pending With'),
                        'Date Completed': st.column_config.TextColumn('Date Completed'),
                        'Notes': st.column_config.TextColumn('Notes'),
                        'Tested certificate available': st.column_config.CheckboxColumn('Tested certificate available')
                    }
                )
                save_clicked = st.form_submit_button("Save data")

            if save_clicked:
                if show_all:
                    st.session_state.checklist_df = edited_df
                else:
                    mask = st.session_state.checklist_df['Section'] == selected_section
                    st.session_state.checklist_df.loc[mask, edited_df.columns] = edited_df.values

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


