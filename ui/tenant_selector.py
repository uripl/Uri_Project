import streamlit as st

from core import db, repository as repo


SESSION_KEY = "active_tenant_id"


def render_storage_banner() -> None:
    """Show a persistent warning if the app is running on MemoryStore despite
    having credentials configured (i.e. Sheets connection failed)."""
    err = db.last_sheets_error()
    if err:
        st.error(
            f"⚠️ **מצב זמני — הנתונים לא נשמרים בגליון.** "
            f"החיבור ל-Google Sheets נכשל: {err}"
        )


def render_tenant_selector() -> int | None:
    """Render the tenant selector in the sidebar and return the active tenant_id."""
    render_storage_banner()
    tenants = repo.list_tenants()

    with st.sidebar:
        st.markdown("### לקוח פעיל")

        if not tenants:
            st.warning("אין עדיין לקוחות. הוסף לקוח ראשון בדף 'לקוחות'.")
            st.session_state.pop(SESSION_KEY, None)
            return None

        ids = [t.id for t in tenants]
        labels = {t.id: t.name for t in tenants}

        current = st.session_state.get(SESSION_KEY)
        if current not in ids:
            current = ids[0]
            st.session_state[SESSION_KEY] = current

        selected = st.selectbox(
            "בחר לקוח",
            options=ids,
            format_func=lambda i: labels[i],
            index=ids.index(current),
            key="_tenant_selectbox",
            label_visibility="collapsed",
        )
        st.session_state[SESSION_KEY] = selected

        tenant = next(t for t in tenants if t.id == selected)
        st.caption(f"מטבע: {tenant.currency}")
        if tenant.notes:
            st.caption(tenant.notes)

        return selected


def require_tenant() -> int:
    """Use in pages that require an active tenant. Stops the page if none."""
    db.init_db()  # ensures store is built and surfaces connection errors early
    tid = render_tenant_selector()
    if tid is None:
        st.info("עבור לדף 'לקוחות' והוסף לקוח כדי להתחיל.")
        st.stop()
    return tid  # type: ignore[return-value]
