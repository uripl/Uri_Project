import pandas as pd
import streamlit as st

from core import repository as repo
from core.formatting import EXPENSE_CATEGORIES, FREQUENCIES, fmt_currency
from ui.rtl import apply_rtl
from ui.tenant_selector import require_tenant

st.set_page_config(page_title="הוצאות שוטפות", page_icon="📤", layout="wide")
apply_rtl()
tenant_id = require_tenant()

tenant = repo.get_tenant(tenant_id)
st.title(f"הוצאות שוטפות — {tenant.name}")

st.caption(
    "הוצאות חוזרות מחושבות אוטומטית בעקומת התזרים העתידית. "
    "אין צורך ליצור תנועה ידנית עבורן."
)

expenses = repo.list_recurring_expenses(tenant_id)

if expenses:
    def _freq_label(e):
        if e.frequency == "monthly":
            return f"חודשי (יום {e.day_of_month})"
        return f"שבועי (יום {e.day_of_month} בשבוע)"

    rows = [{
        "id": e.id,
        "שם": e.name,
        "קטגוריה": e.category,
        "סכום": e.amount,
        "תדירות": _freq_label(e),
        "פעיל": "כן" if e.active else "לא",
    } for e in expenses]
    df = pd.DataFrame(rows)
    st.dataframe(
        df.drop(columns=["id"]),
        use_container_width=True,
        hide_index=True,
        column_config={"סכום": st.column_config.NumberColumn(format="₪%.0f")},
    )

    monthly_total = sum(
        e.amount if e.frequency == "monthly" else e.amount * 4.33
        for e in expenses if e.active
    )
    st.metric("סך הוצאה חודשית מוערכת (פעילות)", fmt_currency(monthly_total, tenant.currency))
else:
    st.info("עדיין לא הוזנו הוצאות שוטפות.")

st.divider()

# Add ----------------------------------------------------------------------
st.subheader("הוספת הוצאה שוטפת")
with st.form("add_expense", clear_on_submit=True):
    c1, c2 = st.columns(2)
    name = c1.text_input("שם ההוצאה")
    category = c2.selectbox("קטגוריה", EXPENSE_CATEGORIES)

    c3, c4, c5 = st.columns(3)
    amount = c3.number_input("סכום (₪)", min_value=0.0, step=100.0, format="%.2f")
    frequency = c4.selectbox("תדירות", list(FREQUENCIES.keys()), format_func=lambda f: FREQUENCIES[f])
    if frequency == "monthly":
        day = c5.number_input("יום בחודש (1-31)", min_value=1, max_value=31, value=1)
    else:
        day = c5.selectbox("יום בשבוע", options=list(range(1, 8)),
                          format_func=lambda d: ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"][d - 1])

    notes = st.text_area("הערות", height=60)
    active = st.checkbox("פעיל", value=True)

    if st.form_submit_button("הוסף", type="primary"):
        if not name.strip() or amount <= 0:
            st.error("שם וסכום חיוביים הם חובה.")
        else:
            repo.create_recurring_expense(
                tenant_id,
                name=name.strip(),
                category=category,
                amount=amount,
                frequency=frequency,
                day_of_month=int(day),
                active=active,
                notes=notes.strip() or None,
            )
            st.success("נוסף.")
            st.rerun()

st.divider()

# Toggle / delete ----------------------------------------------------------
st.subheader("ניהול הוצאות")
if not expenses:
    st.caption("אין הוצאות לפעולה.")
else:
    options = {f"{e.name} — {fmt_currency(e.amount)} ({FREQUENCIES.get(e.frequency, e.frequency)})": e.id for e in expenses}
    label = st.selectbox("בחר הוצאה", list(options.keys()))
    expense_id = options[label]
    expense = next(e for e in expenses if e.id == expense_id)

    c1, c2 = st.columns(2)
    if c1.button("הפעל" if not expense.active else "השבת", type="primary"):
        repo.update_recurring_expense(tenant_id, expense_id, active=not expense.active)
        st.success("עודכן.")
        st.rerun()

    if c2.button("מחק"):
        repo.delete_recurring_expense(tenant_id, expense_id)
        st.success("נמחק.")
        st.rerun()
