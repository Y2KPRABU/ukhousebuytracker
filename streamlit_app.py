import json
import os
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="UK House Buying Checklist", page_icon="🏠")

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


if "checklist_df" not in st.session_state:
    st.session_state.checklist_df = build_df_from_json(data)

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


# Sidebar config for Google Sheets linking
st.sidebar.header("Google Sheets integration")
spreadsheet_id = st.sidebar.text_input("Spreadsheet ID", value=os.getenv("GOOGLE_SHEET_ID", ""))
user_id = st.sidebar.text_input("User identifier (email or username)", value=os.getenv("USER_ID", ""))

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
                st.experimental_rerun()
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

# Main interactive editor
st.subheader("Checklist table")
edited_df = st.data_editor(
    st.session_state.checklist_df,
    use_container_width=True,
    num_rows="dynamic",
    column_config={
        "Section": st.column_config.TextColumn("Section", disabled=True),
        "Item": st.column_config.TextColumn("Item", disabled=True),
        "Done": st.column_config.CheckboxColumn("Done"),
        "Pending With": st.column_config.TextColumn("Pending With"),
        "Date Completed": st.column_config.TextColumn("Date Completed"),
        "Notes": st.column_config.TextColumn("Notes"),
        "Tested certificate available": st.column_config.CheckboxColumn("Tested certificate available")
    }
)

# Automatically promote TA6/TA10 once Instruct solicitor is done
processed_df = enforce_ta_forms_order(edited_df.copy())
st.session_state.checklist_df = processed_df

# Overall pie chart for sections
section_data = []
section_colors = ['#E6F3FF', '#E6FFE6', '#FFFFE6', '#FFE6F3', '#F3E6FF', '#FFF3E6']  # light blue, green, yellow, pink, purple, orange
color_map = {}
for i, section_name in enumerate(data.keys()):
    color_map[section_name] = section_colors[i % len(section_colors)]

for section_name in data.keys():
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
    fig = go.Figure(data=[go.Pie(
        labels=[d['name'] for d in section_data],
        values=[d['total'] for d in section_data],
        textinfo='label+value',
        insidetextorientation='radial',
        marker=dict(colors=[d['color'] for d in section_data])
    )])
    fig.update_layout(
        title="Sections Overview (size = total tasks, color = section)",
        showlegend=False,
        height=400
    )
    st.plotly_chart(fig, use_container_width=True)

# Controls hidden as per request

done_count = int(processed_df["Done"].sum()) if "Done" in processed_df else 0
st.info(f"Overall Progress: {done_count} of {len(processed_df)} tasks done ({(done_count/len(processed_df)*100 if len(processed_df)>0 else 0):.1f}%).")

