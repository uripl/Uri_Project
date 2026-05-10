from datetime import date

import pandas as pd
import streamlit as st

from core import repository as repo
from core.formatting import (
    DEBT_CATEGORIES,
    DEBT_STATUSES,
    fmt_currency,
    fmt_date,
    money_format,
)
from ui.rtl import apply_rtl
from ui.tenant_selector import require_tenant

st.set_page_config(page_title="חובות", page_icon="💸", layout="wide")
apply_rtl()
tenant_id = require_tenant()

tenant = repo.get_tenant(tenant_id)
st.title(f"חובות — {tenant.name}")

debts = repo.list_debts(tenant_id)
today = date.today()

# Existing list -------------------------------------------------------------
if debts:
    rows = []
    plan_counts = {}
    for d in debts:
        installments = repo.list_debt_installments(tenant_id, d.id, only_pending=True)
        plan_counts[d.id] = len(installments)
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
            "הסדר": "✓" if plan_counts[d.id] > 0 else "—",
            "הערות": d.notes or "",
        })
    df = pd.DataFrame(rows)
    st.dataframe(
        df.drop(columns=["id"]),
        use_container_width=True,
        hide_index=True,
        column_config={
            "סכום מקורי": st.column_config.NumberColumn(format=money_format()),
            "שולם": st.column_config.NumberColumn(format=money_format()),
            "יתרה": st.column_config.NumberColumn(format=money_format()),
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

# Per-debt management panel ------------------------------------------------
st.subheader("ניהול חוב קיים")
if not debts:
    st.caption("אין חובות לפעולה.")
else:
    debt_options = {
        f"{d.creditor} — יתרה {fmt_currency(max(d.original_amount - d.paid_amount, 0))} "
        f"(פירעון {fmt_date(d.due_date)})": d.id
        for d in debts
    }
    label = st.selectbox("בחר חוב", list(debt_options.keys()))
    debt_id = debt_options[label]
    debt = next(d for d in debts if d.id == debt_id)
    remaining = max(debt.original_amount - debt.paid_amount, 0.0)

    tab_quick, tab_edit, tab_plan = st.tabs(["פעולות מהירות", "עריכה מלאה", "הסדר תשלומים"])

    # ---------------------------------------------------- quick actions
    with tab_quick:
        c1, c2 = st.columns(2)
        if c1.button("סמן כשולם במלואו", type="primary", key="mark_paid_full"):
            repo.mark_debt_paid(tenant_id, debt_id, payment_date=today)
            st.success("סומן כשולם.")
            st.rerun()

        if c2.button("מחק חוב", key="delete_debt"):
            repo.delete_debt(tenant_id, debt_id)
            st.success("נמחק (כולל הסדרים שלו).")
            st.rerun()

        st.markdown("**עדכון תשלום חלקי**")
        with st.form("partial_payment", clear_on_submit=True):
            extra = st.number_input("סכום ששולם עכשיו", min_value=0.0,
                                    step=100.0, format="%.2f")
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

    # ------------------------------------------------------ edit form
    with tab_edit:
        with st.form("edit_debt"):
            c1, c2, c3 = st.columns(3)
            new_creditor = c1.text_input("נושה", value=debt.creditor, key="ed_creditor")
            new_category = c2.selectbox(
                "קטגוריה", DEBT_CATEGORIES,
                index=DEBT_CATEGORIES.index(debt.category) if debt.category in DEBT_CATEGORIES else 0,
                key="ed_category",
            )
            new_amount = c3.number_input(
                "סכום מקורי (₪)", min_value=0.0, step=100.0,
                value=float(debt.original_amount), format="%.2f", key="ed_amount",
            )

            c4, c5, c6 = st.columns(3)
            new_due = c4.date_input("תאריך פירעון", value=debt.due_date, key="ed_due")
            new_paid = c5.number_input(
                "שולם עד כה (₪)", min_value=0.0, step=100.0,
                value=float(debt.paid_amount), format="%.2f", key="ed_paid",
            )
            statuses = list(DEBT_STATUSES.keys())
            new_status = c6.selectbox(
                "סטטוס", statuses,
                index=statuses.index(debt.status) if debt.status in statuses else 0,
                format_func=lambda s: DEBT_STATUSES[s], key="ed_status",
            )
            new_notes = st.text_area("הערות", value=debt.notes or "", height=70, key="ed_notes")

            if st.form_submit_button("שמור שינויים", type="primary"):
                if not new_creditor.strip() or new_amount <= 0:
                    st.error("נושה וסכום חיוביים הם חובה.")
                else:
                    repo.update_debt(
                        tenant_id, debt_id,
                        creditor=new_creditor.strip(),
                        category=new_category,
                        original_amount=new_amount,
                        paid_amount=new_paid,
                        due_date=new_due,
                        status=new_status,
                        notes=new_notes.strip() or None,
                    )
                    st.success("עודכן.")
                    st.rerun()

    # ------------------------------------------------ installment plan
    with tab_plan:
        st.caption(
            "הסדר תשלומים פורס את היתרה למספר תשלומים. כשיש הסדר פעיל, התחזית מציגה "
            "את התשלומים בתאריכים שלהם — לא את החוב המקורי. חוב באיחור ללא הסדר נשמר "
            "כהתחייבות פתוחה ולא נדחס לתחזית."
        )
        st.markdown(f"**יתרה לפריסה:** {fmt_currency(remaining, tenant.currency)}")

        installments = repo.list_debt_installments(tenant_id, debt_id)
        if installments:
            inst_rows = [{
                "id": i.id,
                "תאריך": i.due_date,
                "סכום": i.amount,
                "סטטוס": "שולם" if i.status == "paid" else "מתוכנן",
            } for i in installments]
            inst_df = pd.DataFrame(inst_rows)
            st.dataframe(
                inst_df.drop(columns=["id"]),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "סכום": st.column_config.NumberColumn(format=money_format()),
                    "תאריך": st.column_config.DateColumn(format="DD/MM/YYYY"),
                },
            )
            scheduled_total = sum(i.amount for i in installments if i.status != "paid")
            paid_total = sum(i.amount for i in installments if i.status == "paid")
            c1, c2 = st.columns(2)
            c1.metric("סך מתוכנן", fmt_currency(scheduled_total, tenant.currency))
            c2.metric("סך שולם דרך ההסדר", fmt_currency(paid_total, tenant.currency))

            st.markdown("**ניהול תשלום בודד**")
            pending = [i for i in installments if i.status != "paid"]
            if pending:
                inst_options = {f"{fmt_date(i.due_date)} — {fmt_currency(i.amount)}": i.id for i in pending}
                inst_label = st.selectbox("בחר תשלום מתוכנן", list(inst_options.keys()), key="inst_select")
                inst_id = inst_options[inst_label]
                ic1, ic2 = st.columns(2)
                if ic1.button("סמן כשולם", type="primary", key="mark_inst_paid"):
                    repo.mark_installment_paid(tenant_id, inst_id, payment_date=today)
                    st.success("נרשם תשלום.")
                    st.rerun()
                if ic2.button("מחק תשלום", key="delete_inst"):
                    repo.delete_debt_installment(tenant_id, inst_id)
                    st.success("נמחק.")
                    st.rerun()

        st.divider()
        st.markdown("**יצירת הסדר אוטומטי**")
        st.caption("פורס את היתרה לתשלומים שווים בתדירות שתבחרי.")
        with st.form("auto_schedule"):
            c1, c2, c3 = st.columns(3)
            count = c1.number_input("מספר תשלומים", min_value=1, max_value=120,
                                    value=6, step=1, key="sched_count")
            freq = c2.selectbox("תדירות", ["monthly", "weekly"],
                               format_func=lambda f: "חודשי" if f == "monthly" else "שבועי",
                               key="sched_freq")
            first = c3.date_input("תאריך התשלום הראשון", value=today, key="sched_first")
            replace = st.checkbox("מחק תשלומים מתוכננים קיימים והחלף", value=True, key="sched_replace")

            if st.form_submit_button("צור הסדר", type="primary"):
                if remaining <= 0:
                    st.error("אין יתרה לפריסה.")
                else:
                    created = repo.schedule_installments(
                        tenant_id, debt_id,
                        count=int(count), first_date=first,
                        frequency=freq, replace_existing=replace,
                    )
                    st.success(f"נוצרו {len(created)} תשלומים.")
                    st.rerun()

        st.divider()
        st.markdown("**הוספת תשלום ידני**")
        with st.form("manual_inst", clear_on_submit=True):
            c1, c2 = st.columns(2)
            inst_date = c1.date_input("תאריך תשלום", value=today, key="m_inst_date")
            inst_amount = c2.number_input(
                "סכום (₪)", min_value=0.0, step=100.0, format="%.2f", key="m_inst_amount",
            )
            inst_notes = st.text_input("הערה (אופציונלי)", key="m_inst_notes")
            if st.form_submit_button("הוסף תשלום"):
                if inst_amount <= 0:
                    st.error("סכום חיובי הוא חובה.")
                else:
                    repo.create_debt_installment(
                        tenant_id, debt_id,
                        due_date=inst_date,
                        amount=inst_amount,
                        status="scheduled",
                        notes=inst_notes.strip() or None,
                    )
                    st.success("נוסף.")
                    st.rerun()
