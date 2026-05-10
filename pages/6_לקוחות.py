import pandas as pd
import streamlit as st

from core import repository as repo
from core.formatting import money_format
from ui.rtl import apply_rtl
from ui.tenant_selector import render_tenant_selector

st.set_page_config(page_title="לקוחות", page_icon="⚙️", layout="wide")
apply_rtl()
render_tenant_selector()

st.title("ניהול לקוחות")
st.caption(
    "המבנה תומך כיום בריבוי לקוחות (multi-tenant). הוסף כאן לקוחות נוספים "
    "ועבור ביניהם דרך הסיידבר."
)

tenants = repo.list_tenants()

if tenants:
    rows = [{
        "id": t.id,
        "שם": t.name,
        "מטבע": t.currency,
        "יתרה פותחת": t.opening_balance,
        "הערות": t.notes or "",
    } for t in tenants]
    df = pd.DataFrame(rows)
    st.dataframe(
        df.drop(columns=["id"]),
        use_container_width=True,
        hide_index=True,
        column_config={"יתרה פותחת": st.column_config.NumberColumn(format=money_format())},
    )
else:
    st.info("עדיין אין לקוחות. הוסף לקוח ראשון.")

st.divider()

# Add new tenant -----------------------------------------------------------
st.subheader("הוספת לקוח חדש")
with st.form("add_tenant", clear_on_submit=True):
    c1, c2 = st.columns(2)
    name = c1.text_input("שם הלקוח / העסק")
    currency = c2.selectbox("מטבע", ["ILS", "USD", "EUR"])
    opening = st.number_input(
        "יתרה פותחת (₪) — סכום המזומן הנוכחי בעסק", value=0.0, step=1000.0, format="%.2f"
    )
    notes = st.text_area("הערות", height=70)

    if st.form_submit_button("הוסף לקוח", type="primary"):
        if not name.strip():
            st.error("שם הלקוח חובה.")
        else:
            tenant = repo.create_tenant(
                name=name.strip(),
                currency=currency,
                opening_balance=opening,
                notes=notes.strip() or None,
            )
            st.success(f"נוסף לקוח: {tenant.name}")
            st.rerun()

st.divider()

# Edit / delete -----------------------------------------------------------
st.subheader("עריכת לקוח קיים")
if not tenants:
    st.caption("אין לקוחות לעריכה.")
else:
    options = {t.name: t.id for t in tenants}
    label = st.selectbox("בחר לקוח", list(options.keys()))
    tenant_id = options[label]
    tenant = next(t for t in tenants if t.id == tenant_id)

    with st.form("edit_tenant"):
        c1, c2 = st.columns(2)
        new_name = c1.text_input("שם", value=tenant.name)
        new_currency = c2.selectbox(
            "מטבע", ["ILS", "USD", "EUR"],
            index=["ILS", "USD", "EUR"].index(tenant.currency) if tenant.currency in ["ILS", "USD", "EUR"] else 0,
        )
        new_opening = st.number_input(
            "יתרה פותחת", value=float(tenant.opening_balance), step=1000.0, format="%.2f"
        )
        new_notes = st.text_area("הערות", value=tenant.notes or "", height=70)

        c3, c4 = st.columns(2)
        if c3.form_submit_button("שמור שינויים", type="primary"):
            repo.update_tenant(
                tenant_id,
                name=new_name.strip() or tenant.name,
                currency=new_currency,
                opening_balance=new_opening,
                notes=new_notes.strip() or None,
            )
            st.success("נשמר.")
            st.rerun()

        if c4.form_submit_button("⚠️ מחק לקוח (וכל הנתונים)"):
            repo.delete_tenant(tenant_id)
            st.session_state.pop("active_tenant_id", None)
            st.success("נמחק.")
            st.rerun()
