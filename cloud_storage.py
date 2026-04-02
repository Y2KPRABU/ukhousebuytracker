import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import quote_plus

import pandas as pd

try:
    import requests
except ImportError:
    requests = None

EXPECTED_COLUMNS = [
    "Section",
    "Item",
    "Initiator",
    "Done",
    "Pending With",
    "Date Completed",
    "Notes",
    "Tested certificate available",
]


class CloudStorageError(RuntimeError):
    pass


class BaseChecklistStore:
    def load_user(self, user_id: str) -> Optional[pd.DataFrame]:
        raise NotImplementedError

    def save_user(self, user_id: str, df: pd.DataFrame) -> None:
        raise NotImplementedError

    @property
    def backend_name(self) -> str:
        raise NotImplementedError


def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()
    for col in EXPECTED_COLUMNS:
        if col not in cleaned.columns:
            if col in ("Done", "Tested certificate available"):
                cleaned[col] = False
            else:
                cleaned[col] = ""
    cleaned = cleaned[EXPECTED_COLUMNS]

    # Normalize booleans so persisted data stays consistent across backends.
    for bool_col in ("Done", "Tested certificate available"):
        cleaned[bool_col] = cleaned[bool_col].fillna(False).astype(bool)

    for text_col in ("Section", "Item", "Initiator", "Pending With", "Date Completed", "Notes"):
        cleaned[text_col] = cleaned[text_col].fillna("").astype(str)

    return cleaned


def _sanitize_user_id(user_id: str) -> str:
    return (
        user_id.strip()
        .lower()
        .replace("@", "_at_")
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
    )


class LocalJsonChecklistStore(BaseChecklistStore):
    def __init__(self, root_dir: str = ".user_data"):
        self.root = Path(root_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def backend_name(self) -> str:
        return "local-json"

    def _path_for_user(self, user_id: str) -> Path:
        safe_name = _sanitize_user_id(user_id)
        return self.root / f"{safe_name}.json"

    def load_user(self, user_id: str) -> Optional[pd.DataFrame]:
        path = self._path_for_user(user_id)
        if not path.exists():
            return None

        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        records = payload.get("checklist", [])
        if not isinstance(records, list) or not records:
            return None

        return normalize_df(pd.DataFrame(records))

    def save_user(self, user_id: str, df: pd.DataFrame) -> None:
        path = self._path_for_user(user_id)
        normalized = normalize_df(df)
        payload = {
            "user_id": user_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "checklist": normalized.to_dict(orient="records"),
        }
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)


class SupabaseChecklistStore(BaseChecklistStore):
    def __init__(self, base_url: str, api_key: str, table_name: str = "user_checklists"):
        if requests is None:
            raise CloudStorageError("requests package is required for Supabase cloud storage.")

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.table_name = table_name

    @property
    def backend_name(self) -> str:
        return "supabase"

    def _headers(self, prefer: Optional[str] = None) -> dict:
        headers = {
            "apikey": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def load_user(self, user_id: str) -> Optional[pd.DataFrame]:
        encoded_user = quote_plus(user_id)
        url = (
            f"{self.base_url}/rest/v1/{self.table_name}"
            f"?select=checklist&user_id=eq.{encoded_user}&limit=1"
        )
        resp = requests.get(url, headers=self._headers(), timeout=15)
        if resp.status_code >= 400:
            raise CloudStorageError(f"Cloud load failed ({resp.status_code}): {resp.text}")

        rows = resp.json()
        if not rows:
            return None

        checklist = rows[0].get("checklist", [])
        if not isinstance(checklist, list) or not checklist:
            return None

        return normalize_df(pd.DataFrame(checklist))

    def save_user(self, user_id: str, df: pd.DataFrame) -> None:
        normalized = normalize_df(df)
        payload = [
            {
                "user_id": user_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "checklist": normalized.to_dict(orient="records"),
            }
        ]
        url = f"{self.base_url}/rest/v1/{self.table_name}?on_conflict=user_id"
        prefer = "resolution=merge-duplicates,return=minimal"
        resp = requests.post(url, headers=self._headers(prefer=prefer), json=payload, timeout=20)
        if resp.status_code >= 400:
            raise CloudStorageError(f"Cloud save failed ({resp.status_code}): {resp.text}")


def build_store_from_env() -> BaseChecklistStore:
    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip() or os.getenv("SUPABASE_ANON_KEY", "").strip()
    supabase_table = os.getenv("SUPABASE_CHECKLIST_TABLE", "user_checklists").strip() or "user_checklists"

    if supabase_url and supabase_key:
        try:
            return SupabaseChecklistStore(
                base_url=supabase_url,
                api_key=supabase_key,
                table_name=supabase_table,
            )
        except Exception:
            # Fall back instead of hard-failing app startup.
            pass

    return LocalJsonChecklistStore()


def merge_with_canonical(loaded_df: pd.DataFrame, default_df: pd.DataFrame) -> pd.DataFrame:
    """Overlay saved user progress onto the canonical JSON structure.

    Always returns a DataFrame with every section/item defined in default_df.
    Progress columns (Done, notes, etc.) are copied from loaded_df where the
    (Section, Item) key matches, so stale or renamed sections never cause rows
    to vanish from the UI.
    """
    user_cols = [
        "Done",
        "Pending With",
        "Date Completed",
        "Notes",
        "Tested certificate available",
    ]
    result = default_df.copy()
    if loaded_df is None or loaded_df.empty:
        return result

    try:
        # Merge on Section + Item to overlay user progress
        merged = result.merge(
            loaded_df[["Section", "Item"] + [c for c in user_cols if c in loaded_df.columns]],
            on=["Section", "Item"],
            how="left",
            suffixes=("", "_loaded")
        )
        # Copy back loaded values, preferring non-null
        for col in user_cols:
            if f"{col}_loaded" in merged.columns:
                merged[col] = merged[f"{col}_loaded"].fillna(merged[col])
                merged = merged.drop(columns=[f"{col}_loaded"])
        return merged
    except Exception:
        return result


def load_for_user(store: BaseChecklistStore, user_id: str, default_df: pd.DataFrame) -> Tuple[pd.DataFrame, str]:
    if not user_id.strip():
        return normalize_df(default_df), "anonymous-default"

    loaded_df = store.load_user(user_id)
    if loaded_df is None or loaded_df.empty:
        return normalize_df(default_df), "default"

    merged = merge_with_canonical(normalize_df(loaded_df), normalize_df(default_df))
    return normalize_df(merged), "cloud"


def save_for_user(store: BaseChecklistStore, user_id: str, df: pd.DataFrame) -> Tuple[bool, str]:
    if not user_id.strip():
        return False, "Please enter a user account ID first."

    try:
        store.save_user(user_id, normalize_df(df))
        return True, "Saved"
    except Exception as err:
        return False, str(err)
