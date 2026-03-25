"""
Checklist data loading and DataFrame utilities.
Handles JSON loading, DataFrame construction, ordering, and hashing.
"""

import json
import os

import pandas as pd


DEFAULT_CHECKLIST = {
    "Initial Stage": [
        "Memorandum of Sale (from Agent)",
        "ID & AML Checks (Passport/Address)",
        "Client Care Pack (Signed)",
    ],
    "Legal & Searches": [
        "TA6 Property Info Form (Check FENSA)",
        "TA10 Fittings/Contents Form",
        "Local Authority & Environmental Searches",
        "Report on Title (Read & Signed)",
    ],
    "Exchange & Completion": [
        "Buildings Insurance (Active today!)",
        "Transfer Deed (TR1) Signed",
        "Exchange Deposit Paid",
        "Completion Statement Received",
        "Key Collection",
    ],
}


def load_checklist_json(data_file: str) -> dict:
    """Load checklist definition from a JSON file, falling back to DEFAULT_CHECKLIST."""
    if os.path.exists(data_file):
        with open(data_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_CHECKLIST


def build_df_from_json(checklist_data: dict) -> pd.DataFrame:
    """Build a DataFrame with all required columns from the checklist dict."""
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
                "Tested certificate available": False,
            })
    return pd.DataFrame(rows)


def reorder_by_json(df: pd.DataFrame, canonical_data: dict) -> pd.DataFrame:
    """Reorder DataFrame rows to match the section/item order defined in the JSON."""
    order_map = {}
    idx = 0
    for section, items in canonical_data.items():
        for item in items:
            order_map[(section, item)] = idx
            idx += 1
    sort_keys = df.apply(
        lambda row: order_map.get((row["Section"], row["Item"]), len(order_map)),
        axis=1,
    )
    return df.iloc[sort_keys.argsort(kind="stable")].reset_index(drop=True)


def dataframe_signature(df: pd.DataFrame) -> str:
    """Create a stable hash so autosave only triggers when content actually changes."""
    as_text = df.fillna("").astype(str)
    return str(pd.util.hash_pandas_object(as_text, index=True).sum())


def enforce_ta_forms_order(df: pd.DataFrame) -> pd.DataFrame:
    """If solicitor has been instructed, move TA6/TA10 into Legal & Searches."""
    if "Item" not in df.columns or "Done" not in df.columns:
        return df

    instruct_idx = df.index[df["Item"] == "Instruct solicitor"]
    if len(instruct_idx) and df.at[instruct_idx[0], "Done"]:
        for ta_item in ["TA6 Property Info Form (Check FENSA)", "TA10 Fittings/Contents Form"]:
            if ta_item in df["Item"].values:
                ta_idx = df.index[df["Item"] == ta_item][0]
                df.at[ta_idx, "Section"] = "Legal & Searches"

        legal_rows = df[df["Section"] == "Legal & Searches"]
        other_rows = df[df["Section"] != "Legal & Searches"]
        df = pd.concat([other_rows, legal_rows], ignore_index=True)

    return df
