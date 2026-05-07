"""Backend wiring: lazy-construct a `Store`, defaulting to Sheets if credentials exist
and falling back to an in-process MemoryStore otherwise (useful for tests and local
exploration without Google credentials)."""
from __future__ import annotations

import os
from typing import Optional

from core.store import MemoryStore, SheetsStore, Store

_DEFAULT_SPREADSHEET_NAME = "תזרים ועוד - DB"
_GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_store: Optional[Store] = None


def _read_streamlit_secret(key: str):
    try:
        import streamlit as st  # local import keeps non-streamlit contexts clean
    except ImportError:
        return None
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        # st.secrets raises if no secrets file at all.
        return None
    return None


def _get_service_account_info() -> dict | None:
    """Return service-account JSON as a dict, from secrets or env."""
    raw = _read_streamlit_secret("gcp_service_account")
    if raw is not None:
        return dict(raw)

    env_json = os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
    if env_json:
        import json
        return json.loads(env_json)

    return None


def _get_editor_email() -> str | None:
    raw = _read_streamlit_secret("editor_email")
    if raw:
        return str(raw)
    return os.environ.get("EDITOR_EMAIL") or None


def _get_spreadsheet_name() -> str:
    raw = _read_streamlit_secret("spreadsheet_name")
    if raw:
        return str(raw)
    return os.environ.get("SPREADSHEET_NAME") or _DEFAULT_SPREADSHEET_NAME


def _get_spreadsheet_id() -> str | None:
    raw = _read_streamlit_secret("spreadsheet_id")
    if raw:
        return str(raw)
    return os.environ.get("SPREADSHEET_ID") or None


def _build_sheets_store() -> SheetsStore | None:
    """Construct a SheetsStore using a service account.

    Resolution order for the workbook:
      1) `spreadsheet_id` from secrets/env — open by ID
      2) Search the service account's Drive for a workbook named `spreadsheet_name`
      3) Create a new workbook with that name and share it with `editor_email` if set
    """
    info = _get_service_account_info()
    if info is None:
        return None

    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as e:
        raise RuntimeError(
            "Missing 'gspread' / 'google-auth'. Install requirements: pip install -r requirements.txt"
        ) from e

    creds = Credentials.from_service_account_info(info, scopes=_GOOGLE_SCOPES)
    client = gspread.authorize(creds)

    sheet_id = _get_spreadsheet_id()
    if sheet_id:
        spreadsheet = client.open_by_key(sheet_id)
    else:
        name = _get_spreadsheet_name()
        try:
            spreadsheet = client.open(name)
        except gspread.SpreadsheetNotFound:
            spreadsheet = client.create(name)
            editor = _get_editor_email()
            if editor:
                try:
                    spreadsheet.share(editor, perm_type="user", role="writer", notify=False)
                except Exception:
                    pass

    store = SheetsStore(spreadsheet)
    store.ensure_schema()
    return store


def get_store() -> Store:
    """Return the active Store. Built lazily on first call."""
    global _store
    if _store is None:
        sheets = None
        try:
            sheets = _build_sheets_store()
        except Exception:
            sheets = None
        _store = sheets if sheets is not None else MemoryStore()
    return _store


def reset_store() -> None:
    """Drop the cached store. Used by tests and after configuration changes."""
    global _store
    _store = None


def set_store(store: Store) -> None:
    """Inject a specific Store. Used by tests."""
    global _store
    _store = store


def init_db() -> None:
    """Backwards-compatible entry point.

    With Sheets, schema is ensured the first time the store is built. Calling
    `init_db()` simply triggers that build so connection errors surface early
    rather than lazily mid-page.
    """
    get_store()
