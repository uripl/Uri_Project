from datetime import date

import pandas as pd
import streamlit as st

from core import repository as repo
from core.formatting import INCOME_STATUSES, fmt_currency, fmt_date
from ui.rtl import apply_rtl
from ui.tenant_selector import require_tenant

st.set_page_config(page_title="הכנסות צפויות", page_icon="📥", layout="wide")
apply_rtl()
tenant_id = require_tenant()

tenant = repo.get_tenant(tenant_id)
st.title(f"הכנסות צפויות — {tenant.name}")

today = date.today()
incomes = repo.list_expected_incomes(tenant_id)

if incomes:
    rows = [{
        "id": i.id,
        "מקור": i.source,
        "סכום": i.amount,
        "סבירות (%)": i.probability,
        "צפי משוקלל": i.expected_value,
        "תאריך צפוי": i.expected_date,
        "סטטוס": INCOME_STATUSES.get(i.status, i.status),
        "הערות": i.notes or "",
    } for i in incomes]
    df = pd.DataFrame(rows)
    st.dataframe(
        df.drop(columns=["id"]),
        use_container_width=True,
        hide_index=True,
        column_config={
            "סכום": st.column_config.NumberColumn(format="₪%.0f"),
            "צפי משוקלל": st.column_config.NumberColumn(format="₪%.0f"),
            "תאריך צפוי": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "סבירות (%)": st.column_config.NumberColumn(format="%d%%"),
        },
    )

    pending_total = sum(i.expected_value for i in incomes if i.status == "pending")
    st.metric("סך צפי משוקלל (ממתין)", fmt_currency(pending_total, tenant.currency))
else:
    st.info("עדיין לא הוזנו הכנסות צפויות.")

st.divider()

# Add ----------------------------------------------------------------------
st.subheader("הוספת הכנסה צפויה")
with st.form("add_income", clear_on_submit=True):
    c1, c2 = st.columns(2)
    source = c1.text_input("מקור (לקוח / חוזה / חשבונית)")
    amount = c2.number_input("סכום (₪)", min_value=0.0, step=100.0, format="%.2f")

    c3, c4 = st.columns(2)
    expected = c3.date_input("תאריך צפוי", value=today)
    probability = c4.slider("סבירות (%)", min_value=0, max_value=100, value=100, step=5)
    notes = st.text_area("הערות", height=70)

    if st.form_submit_button("הוסף", type="primary"):
        if not source.strip() or amount <= 0:
            st.error("מקור וסכום חיוביים הם חובה.")
        else:
            repo.create_expected_income(
                tenant_id,
                source=source.strip(),
                amount=amount,
                probability=probability,
                expected_date=expected,
                status="pending",
                notes=notes.strip() or None,
            )
            st.success("נוסף.")
            st.rerun()

st.divider()

# Actions per income -------------------------------------------------------
st.subheader("פעולות על הכנסה קיימת")
if not incomes:
    st.caption("אין הכנסות לפעולה.")
else:
    options = {f"{i.source} — {fmt_currency(i.amount)} ({fmt_date(i.expected_date)})": i.id for i in incomes}
    label = st.selectbox("בחר הכנסה", list(options.keys()))
    income_id = options[label]
    income = next(i for i in incomes if i.id == income_id)

    c1, c2, c3 = st.columns(3)
    if c1.button("סמן כהתקבל", type="primary"):
        repo.mark_income_received(tenant_id, income_id, received_date=today)
        st.success("סומן כהתקבל ונרשמה תנועת מזומן.")
        st.rerun()

    if c2.button("מחק"):
        repo.delete_expected_income(tenant_id, income_id)
        st.success("נמחק.")
        st.rerun()

    with c3.expander("עדכן סבירות"):
        new_prob = st.slider("סבירות חדשה", 0, 100, income.probability, 5, key=f"prob_{income_id}")
        if st.button("עדכן", key=f"update_prob_{income_id}"):
            repo.update_expected_income(tenant_id, income_id, probability=new_prob)
            st.success("עודכן.")
            st.rerun()
