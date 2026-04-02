"""
Sidebar configuration and controls for the UK House Buying Checklist app.
Handles Account & Cloud Save, Google Sheets integration, and tips.
"""

import json
import os

import pandas as pd
import streamlit as st

from cloud_storage import load_for_user, save_for_user


def render_sidebar(
    cloud_store,
    default_checklist_df: pd.DataFrame,
    DATA_FILE: str,
    DEFAULT_SHEET_NAME: str,
    dataframe_signature,
    get_gsheet_client,
    load_sheet_to_df,
    write_df_to_sheet,
):
    """
    Render the entire left sidebar with Account & Cloud Save, Google Sheets, and tips.
    
    Args:
        cloud_store: Cloud storage backend instance
        default_checklist_df: Default checklist DataFrame
        DATA_FILE: Path to the default checklist JSON file
        DEFAULT_SHEET_NAME: Name of the default Google Sheets worksheet
        dataframe_signature: Function to compute DataFrame signature
        get_gsheet_client: Function to get Google Sheets client
        load_sheet_to_df: Function to load DataFrame from Google Sheet
        write_df_to_sheet: Function to write DataFrame to Google Sheet
    """
    
    # ==================== Account & Cloud Save ====================
    st.sidebar.markdown(
        "<h2 style='color:#0f172a; background:#e6f3ff; padding:12px; border-radius:8px; text-align:center;'>"
        "💾 Account & Cloud Save"
        "</h2>",
        unsafe_allow_html=True,
    )
    
    cloud_user_input = st.sidebar.text_input(
        "🔑 Account ID (email or username)",
        value=st.session_state.active_user_id,
        key="cloud_user_input",
    )
    
    if not cloud_user_input.strip():
        st.sidebar.info(
            "⚠️ **No Account ID set.** Data will save locally only. "
            "Add an Account ID to persist to cloud storage."
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

    if st.sidebar.button("Overwrite account with latest format"):
        target_user = cloud_user_input.strip()
        if not target_user:
            st.session_state.cloud_status = "Overwrite failed: Please enter an Account ID first."
        else:
            migrated_df, source = load_for_user(cloud_store, target_user, default_checklist_df)
            ok, message = save_for_user(cloud_store, target_user, migrated_df)
            if ok:
                st.session_state.checklist_df = migrated_df
                st.session_state.active_user_id = target_user
                st.session_state.last_saved_signature = dataframe_signature(migrated_df)
                st.session_state.cloud_status = (
                    f"Overwrote account data with latest format via {cloud_store.backend_name} "
                    f"(source: {source})."
                )
                st.rerun()
            else:
                st.session_state.cloud_status = f"Overwrite failed: {message}"
    
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
    
    # ==================== Tips & Info ====================
    st.sidebar.info("Tip: Ensure your buildings insurance is active from the moment of **Exchange**, not Completion!")
    st.sidebar.write("### Data source")
    st.sidebar.write(f"Loaded from `{DATA_FILE}`")
    
    # ==================== Google Sheets Integration (Expander) ====================
    with st.sidebar.expander("📊 Google Sheets Integration", expanded=False):
        spreadsheet_id = st.text_input("Spreadsheet ID", value=os.getenv("GOOGLE_SHEET_ID", ""))
        user_id = st.text_input("User identifier (email or username)", value=st.session_state.active_user_id)
        
        if user_id.strip():
            # sanitize worksheet name
            sanitized = user_id.strip().replace("@", "_at_").replace(" ", "_").replace("/", "_").replace("\\", "_")
            sheet_name = st.text_input("Worksheet name", value=f"{DEFAULT_SHEET_NAME}_{sanitized}")
        else:
            sheet_name = st.text_input("Worksheet name", value=DEFAULT_SHEET_NAME)
        
        credentials_text = st.text_area("Service Account JSON (paste content here)", height=180)
        credentials_file = st.file_uploader("Or upload service_account.json", type="json")
        
        service_account_info = None
        if credentials_file is not None:
            try:
                service_account_info = json.load(credentials_file)
            except Exception as err:
                st.error(f"Invalid uploaded JSON: {err}")
        elif credentials_text:
            try:
                service_account_info = json.loads(credentials_text)
            except Exception as err:
                st.error(f"Invalid JSON text: {err}")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("Load from Google Sheets"):
                if not spreadsheet_id or not sheet_name or service_account_info is None:
                    st.warning("Provide Spreadsheet ID, worksheet name/user ID, and service account credentials first.")
                else:
                    try:
                        client = get_gsheet_client(service_account_info)
                        loaded_df = load_sheet_to_df(spreadsheet_id, sheet_name, client)
                        if loaded_df.empty:
                            st.info("No valid data found in Google Sheet tab; using local checklist defaults.")
                        else:
                            st.session_state.checklist_df = loaded_df
                            st.rerun()
                    except Exception as err:
                        st.error(f"Unable to load Google Sheet: {err}")
        
        with col2:
            if st.button("Save to Google Sheets"):
                if not spreadsheet_id or not sheet_name or service_account_info is None:
                    st.warning("Provide Spreadsheet ID, worksheet name/user ID, and service account credentials first.")
                else:
                    try:
                        client = get_gsheet_client(service_account_info)
                        write_df_to_sheet(st.session_state.checklist_df, spreadsheet_id, sheet_name, client)
                        st.success(f"Checklist saved to Google Sheets tab '{sheet_name}'.")
                    except Exception as err:
                        st.error(f"Unable to save to Google Sheet: {err}")
