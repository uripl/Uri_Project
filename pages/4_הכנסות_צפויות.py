from datetime import date

import pandas as pd
import streamlit as st

from core import repository as repo
from core.formatting import (
    FREQUENCIES,
    INCOME_CATEGORIES,
    INCOME_STATUSES,
    fmt_currency,
    fmt_date,
    money_format,
)
from ui.rtl import apply_rtl
from ui.tenant_selector import require_tenant

st.set_page_config(page_title="הכנסות צפויות", page_icon="📥", layout="wide")
apply_rtl()
tenant_id = require_tenant()

tenant = repo.get_tenant(tenant_id)
st.title(f"הכנסות — {tenant.name}")

today = date.today()

tab_one_off, tab_recurring = st.tabs(["חד-פעמיות (חוזה / חשבונית)", "חוזרות (חודשי / שבועי)"])

# ============================================================ One-off incomes
with tab_one_off:
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
                "סכום": st.column_config.NumberColumn(format=money_format()),
                "צפי משוקלל": st.column_config.NumberColumn(format=money_format()),
                "תאריך צפוי": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "סבירות (%)": st.column_config.NumberColumn(format="%d%%"),
            },
        )

        pending_total = sum(i.expected_value for i in incomes if i.status == "pending")
        st.metric("סך צפי משוקלל (ממתין)", fmt_currency(pending_total, tenant.currency))
    else:
        st.info("עדיין לא הוזנו הכנסות חד-פעמיות.")

    st.divider()

    st.subheader("הוספת הכנסה חד-פעמית")
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

    st.subheader("ניהול הכנסה קיימת")
    if not incomes:
        st.caption("אין הכנסות לפעולה.")
    else:
        options = {f"{i.source} — {fmt_currency(i.amount)} ({fmt_date(i.expected_date)})": i.id for i in incomes}
        label = st.selectbox("בחר הכנסה", list(options.keys()))
        income_id = options[label]
        income = next(i for i in incomes if i.id == income_id)

        tab_quick, tab_edit = st.tabs(["פעולות מהירות", "עריכה מלאה"])
        with tab_quick:
            c1, c2 = st.columns(2)
            if c1.button("סמן כהתקבל", type="primary", key="oi_mark"):
                repo.mark_income_received(tenant_id, income_id, received_date=today)
                st.success("סומן כהתקבל ונרשמה תנועת מזומן.")
                st.rerun()

            if c2.button("מחק", key="oi_del"):
                repo.delete_expected_income(tenant_id, income_id)
                st.success("נמחק.")
                st.rerun()

        with tab_edit:
            with st.form("edit_oi"):
                c1, c2 = st.columns(2)
                e_source = c1.text_input("מקור", value=income.source, key="e_oi_source")
                e_amount = c2.number_input("סכום (₪)", min_value=0.0, step=100.0,
                                            value=float(income.amount), format="%.2f",
                                            key="e_oi_amount")
                c3, c4 = st.columns(2)
                e_date = c3.date_input("תאריך צפוי", value=income.expected_date, key="e_oi_date")
                e_prob = c4.slider("סבירות (%)", 0, 100, value=int(income.probability),
                                    step=5, key="e_oi_prob")
                statuses = list(INCOME_STATUSES.keys())
                e_status = st.selectbox(
                    "סטטוס", statuses,
                    index=statuses.index(income.status) if income.status in statuses else 0,
                    format_func=lambda s: INCOME_STATUSES[s], key="e_oi_status",
                )
                e_notes = st.text_area("הערות", value=income.notes or "", height=70, key="e_oi_notes")

                if st.form_submit_button("שמור שינויים", type="primary"):
                    if not e_source.strip() or e_amount <= 0:
                        st.error("מקור וסכום חיוביים הם חובה.")
                    else:
                        repo.update_expected_income(
                            tenant_id, income_id,
                            source=e_source.strip(),
                            amount=e_amount,
                            expected_date=e_date,
                            probability=e_prob,
                            status=e_status,
                            notes=e_notes.strip() or None,
                        )
                        st.success("עודכן.")
                        st.rerun()

# =========================================================== Recurring incomes
with tab_recurring:
    st.caption(
        "הכנסות חוזרות (חוזה חודשי, ריטיינר וכו') מחושבות אוטומטית בעקומת התזרים העתידית. "
        "אין צורך ליצור תנועה ידנית עבורן."
    )

    rincomes = repo.list_recurring_incomes(tenant_id)

    if rincomes:
        def _freq_label(i):
            if i.frequency == "monthly":
                return f"חודשי (יום {i.day_of_month})"
            return f"שבועי (יום {i.day_of_month} בשבוע)"

        rows = [{
            "id": i.id,
            "מקור": i.source,
            "קטגוריה": i.category,
            "סכום": i.amount,
            "סבירות (%)": i.probability,
            "תדירות": _freq_label(i),
            "פעיל": "כן" if i.active else "לא",
        } for i in rincomes]
        df = pd.DataFrame(rows)
        st.dataframe(
            df.drop(columns=["id"]),
            use_container_width=True,
            hide_index=True,
            column_config={
                "סכום": st.column_config.NumberColumn(format=money_format()),
                "סבירות (%)": st.column_config.NumberColumn(format="%d%%"),
            },
        )

        monthly_estimate = sum(
            (i.amount if i.frequency == "monthly" else i.amount * 4.33) * (i.probability / 100.0)
            for i in rincomes if i.active
        )
        st.metric("סך הכנסה חודשית מוערכת (משוקלל)", fmt_currency(monthly_estimate, tenant.currency))
    else:
        st.info("עדיין לא הוזנו הכנסות חוזרות.")

    st.divider()

    st.subheader("הוספת הכנסה חוזרת")
    with st.form("add_recurring_income", clear_on_submit=True):
        c1, c2 = st.columns(2)
        source = c1.text_input("מקור (לקוח / חוזה)")
        category = c2.selectbox("קטגוריה", INCOME_CATEGORIES)

        c3, c4, c5 = st.columns(3)
        amount = c3.number_input("סכום (₪)", min_value=0.0, step=100.0, format="%.2f", key="ri_amount")
        frequency = c4.selectbox("תדירות", list(FREQUENCIES.keys()),
                                 format_func=lambda f: FREQUENCIES[f], key="ri_freq")
        if frequency == "monthly":
            day = c5.number_input("יום בחודש (1-31)", min_value=1, max_value=31, value=1, key="ri_day_m")
        else:
            day = c5.selectbox("יום בשבוע", options=list(range(1, 8)),
                               format_func=lambda d: ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"][d - 1],
                               key="ri_day_w")

        c6, c7 = st.columns(2)
        probability = c6.slider("סבירות (%)", min_value=0, max_value=100, value=100, step=5, key="ri_prob")
        active = c7.checkbox("פעיל", value=True, key="ri_active")
        notes = st.text_area("הערות", height=60, key="ri_notes")

        if st.form_submit_button("הוסף", type="primary"):
            if not source.strip() or amount <= 0:
                st.error("מקור וסכום חיוביים הם חובה.")
            else:
                repo.create_recurring_income(
                    tenant_id,
                    source=source.strip(),
                    category=category,
                    amount=amount,
                    frequency=frequency,
                    day_of_month=int(day),
                    probability=probability,
                    active=active,
                    notes=notes.strip() or None,
                )
                st.success("נוסף.")
                st.rerun()

    st.divider()

    st.subheader("ניהול הכנסות חוזרות")
    if not rincomes:
        st.caption("אין הכנסות לפעולה.")
    else:
        options = {f"{i.source} — {fmt_currency(i.amount)} ({FREQUENCIES.get(i.frequency, i.frequency)})": i.id for i in rincomes}
        label = st.selectbox("בחר הכנסה חוזרת", list(options.keys()), key="ri_select")
        ri_id = options[label]
        ri = next(i for i in rincomes if i.id == ri_id)

        tab_quick, tab_edit = st.tabs(["פעולות מהירות", "עריכה מלאה"])
        with tab_quick:
            c1, c2 = st.columns(2)
            if c1.button("הפעל" if not ri.active else "השבת", type="primary", key="ri_toggle"):
                repo.update_recurring_income(tenant_id, ri_id, active=not ri.active)
                st.success("עודכן.")
                st.rerun()

            if c2.button("מחק", key="ri_delete"):
                repo.delete_recurring_income(tenant_id, ri_id)
                st.success("נמחק.")
                st.rerun()

        with tab_edit:
            with st.form("edit_ri"):
                c1, c2 = st.columns(2)
                e_source = c1.text_input("מקור", value=ri.source, key="e_ri_source")
                e_category = c2.selectbox(
                    "קטגוריה", INCOME_CATEGORIES,
                    index=INCOME_CATEGORIES.index(ri.category) if ri.category in INCOME_CATEGORIES else 0,
                    key="e_ri_cat",
                )
                c3, c4, c5 = st.columns(3)
                e_amount = c3.number_input(
                    "סכום (₪)", min_value=0.0, step=100.0,
                    value=float(ri.amount), format="%.2f", key="e_ri_amount",
                )
                freqs = list(FREQUENCIES.keys())
                e_freq = c4.selectbox(
                    "תדירות", freqs,
                    index=freqs.index(ri.frequency) if ri.frequency in freqs else 0,
                    format_func=lambda f: FREQUENCIES[f], key="e_ri_freq",
                )
                if e_freq == "monthly":
                    e_day = c5.number_input(
                        "יום בחודש (1-31)", min_value=1, max_value=31,
                        value=int(ri.day_of_month), key="e_ri_day_m",
                    )
                else:
                    weekdays = list(range(1, 8))
                    e_day = c5.selectbox(
                        "יום בשבוע", weekdays,
                        index=(int(ri.day_of_month) - 1) % 7 if 1 <= int(ri.day_of_month) <= 7 else 0,
                        format_func=lambda d: ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"][d - 1],
                        key="e_ri_day_w",
                    )
                c6, c7 = st.columns(2)
                e_prob = c6.slider("סבירות (%)", 0, 100, value=int(ri.probability), step=5, key="e_ri_prob")
                e_active = c7.checkbox("פעיל", value=ri.active, key="e_ri_active")
                e_notes = st.text_area("הערות", value=ri.notes or "", height=60, key="e_ri_notes")

                if st.form_submit_button("שמור שינויים", type="primary"):
                    if not e_source.strip() or e_amount <= 0:
                        st.error("מקור וסכום חיוביים הם חובה.")
                    else:
                        repo.update_recurring_income(
                            tenant_id, ri_id,
                            source=e_source.strip(),
                            category=e_category,
                            amount=e_amount,
                            frequency=e_freq,
                            day_of_month=int(e_day),
                            probability=e_prob,
                            active=e_active,
                            notes=e_notes.strip() or None,
                        )
                        st.success("עודכן.")
                        st.rerun()
