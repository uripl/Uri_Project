import pandas as pd
import streamlit as st

from core import repository as repo
from core.formatting import EXPENSE_CATEGORIES, FREQUENCIES, fmt_currency, money_format
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
        column_config={"סכום": st.column_config.NumberColumn(format=money_format())},
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

# Manage -------------------------------------------------------------------
st.subheader("ניהול הוצאה קיימת")
if not expenses:
    st.caption("אין הוצאות לפעולה.")
else:
    options = {f"{e.name} — {fmt_currency(e.amount)} ({FREQUENCIES.get(e.frequency, e.frequency)})": e.id for e in expenses}
    label = st.selectbox("בחר הוצאה", list(options.keys()))
    expense_id = options[label]
    expense = next(e for e in expenses if e.id == expense_id)

    tab_quick, tab_edit = st.tabs(["פעולות מהירות", "עריכה מלאה"])

    with tab_quick:
        c1, c2 = st.columns(2)
        if c1.button("הפעל" if not expense.active else "השבת", type="primary", key="exp_toggle"):
            repo.update_recurring_expense(tenant_id, expense_id, active=not expense.active)
            st.success("עודכן.")
            st.rerun()

        if c2.button("מחק", key="exp_delete"):
            repo.delete_recurring_expense(tenant_id, expense_id)
            st.success("נמחק.")
            st.rerun()

    with tab_edit:
        with st.form(f"edit_expense_{expense_id}"):
            c1, c2 = st.columns(2)
            e_name = c1.text_input("שם", value=expense.name, key=f"e_exp_name_{expense_id}")
            e_category = c2.selectbox(
                "קטגוריה", EXPENSE_CATEGORIES,
                index=EXPENSE_CATEGORIES.index(expense.category) if expense.category in EXPENSE_CATEGORIES else 0,
                key=f"e_exp_cat_{expense_id}",
            )
            c3, c4, c5 = st.columns(3)
            e_amount = c3.number_input(
                "סכום (₪)", min_value=0.0, step=100.0,
                value=float(expense.amount), format="%.2f", key=f"e_exp_amount_{expense_id}",
            )
            freqs = list(FREQUENCIES.keys())
            e_freq = c4.selectbox(
                "תדירות", freqs,
                index=freqs.index(expense.frequency) if expense.frequency in freqs else 0,
                format_func=lambda f: FREQUENCIES[f], key=f"e_exp_freq_{expense_id}",
            )
            if e_freq == "monthly":
                e_day = c5.number_input(
                    "יום בחודש (1-31)", min_value=1, max_value=31,
                    value=int(expense.day_of_month), key=f"e_exp_day_m_{expense_id}",
                )
            else:
                weekdays = list(range(1, 8))
                e_day = c5.selectbox(
                    "יום בשבוע", weekdays,
                    index=(int(expense.day_of_month) - 1) % 7 if 1 <= int(expense.day_of_month) <= 7 else 0,
                    format_func=lambda d: ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"][d - 1],
                    key=f"e_exp_day_w_{expense_id}",
                )
            e_active = st.checkbox("פעיל", value=expense.active, key=f"e_exp_active_{expense_id}")
            e_notes = st.text_area("הערות", value=expense.notes or "", height=60,
                                    key=f"e_exp_notes_{expense_id}")

            if st.form_submit_button("שמור שינויים", type="primary"):
                if not e_name.strip() or e_amount <= 0:
                    st.error("שם וסכום חיוביים הם חובה.")
                else:
                    repo.update_recurring_expense(
                        tenant_id, expense_id,
                        name=e_name.strip(),
                        category=e_category,
                        amount=e_amount,
                        frequency=e_freq,
                        day_of_month=int(e_day),
                        active=e_active,
                        notes=e_notes.strip() or None,
                    )
                    st.success("עודכן.")
                    st.rerun()
