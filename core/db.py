"""Backend wiring: lazy-construct a `Store`. With credentials present, build a
SheetsStore — and surface any failure loudly. With no credentials at all, fall
back silently to MemoryStore (used by tests and local exploration)."""
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
_last_sheets_error: Optional[str] = None


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


def _friendly_error(exc: Exception) -> str:
    """Translate common Google API errors into actionable Hebrew messages."""
    msg = str(exc)
    low = msg.lower()
    if "drive" in low and ("has not been used" in low or "is disabled" in low or "accessnotconfigured" in low):
        return ("Google Drive API לא מופעל בפרויקט הזה. "
                "כנסי ל-console.cloud.google.com → APIs & Services → Library → "
                "חפשי 'Google Drive API' → Enable, ואז עשי Reboot לאפליקציה.")
    if "sheets" in low and ("has not been used" in low or "is disabled" in low or "accessnotconfigured" in low):
        return ("Google Sheets API לא מופעל בפרויקט הזה. "
                "כנסי ל-console.cloud.google.com → APIs & Services → Library → "
                "חפשי 'Google Sheets API' → Enable, ואז עשי Reboot לאפליקציה.")
    if "invalid_grant" in low or "invalid jwt" in low:
        return ("המפתח של ה-Service Account לא תקין. ודאי שה-private_key הועתק שלם, "
                "כולל ה-`\\n` בסוף וב-BEGIN/END שורות.")
    if "permission" in low or "forbidden" in low:
        return f"בעיית הרשאות מול גוגל: {msg}"
    return msg


def _build_sheets_store_from_info(info: dict) -> SheetsStore:
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
                # Sharing failures are non-fatal — the workbook still exists in
                # the service account's Drive — but we want them visible.
                try:
                    spreadsheet.share(editor, perm_type="user", role="writer", notify=False)
                except Exception as share_err:
                    try:
                        import streamlit as st
                        st.warning(
                            f"⚠️ הגליון נוצר אך השיתוף עם {editor} נכשל: {share_err}. "
                            "תוכלי להוסיף אותו ידנית ב-Drive של ה-Service Account."
                        )
                    except Exception:
                        pass

    store = SheetsStore(spreadsheet)
    store.ensure_schema()
    return store


def get_store() -> Store:
    """Return the active Store. Built lazily on first call.

    Behavior:
      - No credentials configured at all → silent fallback to MemoryStore
        (intended for tests and local exploration).
      - Credentials configured but Sheets connection failed → fallback to
        MemoryStore *and* show a loud error in the Streamlit UI so the
        user knows their data is not being persisted.
    """
    global _store, _last_sheets_error
    if _store is not None:
        return _store

    info = _get_service_account_info()
    if info is None:
        _store = MemoryStore()
        return _store

    try:
        _store = _build_sheets_store_from_info(info)
        _last_sheets_error = None
    except Exception as e:
        _last_sheets_error = _friendly_error(e)
        try:
            import streamlit as st
            st.error(
                f"⚠️ לא הצלחתי להתחבר ל-Google Sheets:\n\n**{_last_sheets_error}**\n\n"
                "האפליקציה ממשיכה לרוץ במצב זיכרון בלבד — **הנתונים יימחקו ב-reboot הבא**. "
                "תקני את הבעיה למעלה ועשי Reboot כדי להתחבר לגליון אמיתי."
            )
        except Exception:
            pass
        _store = MemoryStore()

    return _store


def last_sheets_error() -> Optional[str]:
    """Returns the last connection error message, if any. Used by the UI to
    render a persistent banner."""
    return _last_sheets_error


def is_persistent() -> bool:
    """True if the active store actually persists across restarts (i.e. Sheets)."""
    return isinstance(_store, SheetsStore)


def reset_store() -> None:
    """Drop the cached store. Used by tests and after configuration changes."""
    global _store, _last_sheets_error
    _store = None
    _last_sheets_error = None


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
