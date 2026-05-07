from datetime import date

import pandas as pd
import streamlit as st

from core import repository as repo
from core.formatting import (
    DEBT_CATEGORIES,
    DEBT_STATUSES,
    fmt_currency,
    fmt_date,
)
from ui.rtl import apply_rtl
from ui.tenant_selector import require_tenant

st.set_page_config(page_title="חובות", page_icon="💸", layout="wide")
apply_rtl()
tenant_id = require_tenant()

tenant = repo.get_tenant(tenant_id)
st.title(f"חובות — {tenant.name}")

# Existing list -------------------------------------------------------------
debts = repo.list_debts(tenant_id)
today = date.today()

if debts:
    rows = []
    for d in debts:
        days_overdue = (today - d.due_date).days
        if d.status == "paid":
            bucket = "שולם"
        elif days_overdue <= 0:
            bucket = "עתידי"
        elif days_overdue <= 30:
            bucket = "0-30"
        elif days_overdue <= 60:
            bucket = "31-60"
        elif days_overdue <= 90:
            bucket = "61-90"
        else:
            bucket = "90+"
        rows.append({
            "id": d.id,
            "נושה": d.creditor,
            "קטגוריה": d.category,
            "סכום מקורי": d.original_amount,
            "שולם": d.paid_amount,
            "יתרה": max(d.original_amount - d.paid_amount, 0.0),
            "תאריך פירעון": d.due_date,
            "סטטוס": DEBT_STATUSES.get(d.status, d.status),
            "גיל": bucket,
            "הערות": d.notes or "",
        })
    df = pd.DataFrame(rows)
    st.dataframe(
        df.drop(columns=["id"]),
        use_container_width=True,
        hide_index=True,
        column_config={
            "סכום מקורי": st.column_config.NumberColumn(format="₪%.0f"),
            "שולם": st.column_config.NumberColumn(format="₪%.0f"),
            "יתרה": st.column_config.NumberColumn(format="₪%.0f"),
            "תאריך פירעון": st.column_config.DateColumn(format="DD/MM/YYYY"),
        },
    )

    total_open = sum(r["יתרה"] for r in rows if r["סטטוס"] != "שולם")
    st.metric("סך חוב פתוח", fmt_currency(total_open, tenant.currency))
else:
    st.info("עדיין לא הוזנו חובות.")

st.divider()

# Add new debt -------------------------------------------------------------
st.subheader("הוספת חוב חדש")
with st.form("add_debt", clear_on_submit=True):
    c1, c2, c3 = st.columns(3)
    creditor = c1.text_input("נושה")
    category = c2.selectbox("קטגוריה", DEBT_CATEGORIES)
    amount = c3.number_input("סכום (₪)", min_value=0.0, step=100.0, format="%.2f")

    c4, c5 = st.columns(2)
    due = c4.date_input("תאריך פירעון", value=today)
    paid = c5.number_input("שולם עד כה (₪)", min_value=0.0, step=100.0, value=0.0, format="%.2f")
    notes = st.text_area("הערות", height=70)

    submitted = st.form_submit_button("הוסף", type="primary")
    if submitted:
        if not creditor.strip() or amount <= 0:
            st.error("נושה וסכום חוב חיוביים הם חובה.")
        else:
            status = "paid" if paid >= amount else "open"
            repo.create_debt(
                tenant_id,
                creditor=creditor.strip(),
                category=category,
                original_amount=amount,
                paid_amount=paid,
                due_date=due,
                status=status,
                notes=notes.strip() or None,
            )
            st.success(f"נוסף חוב: {creditor}")
            st.rerun()

st.divider()

# Edit / actions per debt --------------------------------------------------
st.subheader("פעולות על חוב קיים")
if not debts:
    st.caption("אין חובות לפעולה.")
else:
    debt_options = {f"{d.creditor} — {fmt_currency(max(d.original_amount - d.paid_amount, 0))} (פירעון {fmt_date(d.due_date)})": d.id for d in debts}
    label = st.selectbox("בחר חוב", list(debt_options.keys()))
    debt_id = debt_options[label]
    debt = next(d for d in debts if d.id == debt_id)

    c1, c2, c3 = st.columns(3)
    if c1.button("סמן כשולם במלואו", type="primary"):
        repo.mark_debt_paid(tenant_id, debt_id, payment_date=today)
        st.success("סומן כשולם.")
        st.rerun()

    if c2.button("מחק חוב"):
        repo.delete_debt(tenant_id, debt_id)
        st.success("נמחק.")
        st.rerun()

    with c3.expander("עדכון תשלום חלקי"):
        with st.form("partial_payment", clear_on_submit=True):
            extra = st.number_input("סכום ששולם עכשיו", min_value=0.0, step=100.0, format="%.2f")
            pay_date = st.date_input("תאריך תשלום", value=today, key="partial_pay_date")
            if st.form_submit_button("רשום תשלום"):
                if extra > 0:
                    new_paid = min(debt.paid_amount + extra, debt.original_amount)
                    new_status = "paid" if new_paid >= debt.original_amount else "open"
                    repo.update_debt(
                        tenant_id, debt_id,
                        paid_amount=new_paid,
                        status=new_status,
                    )
                    repo.create_cash_event(
                        tenant_id,
                        date=pay_date,
                        direction="out",
                        amount=extra,
                        description=f"תשלום חוב: {debt.creditor}",
                        source_type="debt_payment",
                        source_id=debt.id,
                    )
                    st.success("נרשם.")
                    st.rerun()
