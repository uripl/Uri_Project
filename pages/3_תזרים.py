import calendar
from datetime import date

import plotly.graph_objects as go
import streamlit as st

import pandas as pd

from core import forecast, repository as repo
from core.formatting import fmt_currency, fmt_date, money_format
from ui.rtl import apply_rtl
from ui.tenant_selector import require_tenant


def _month_spans(start: date, count: int) -> list[tuple[date, date, str]]:
    """Return a list of (month_start, next_month_start, label) tuples covering
    `count` consecutive calendar months starting from the month of `start`."""
    spans = []
    y, m = start.year, start.month
    for _ in range(count):
        ms = date(y, m, 1)
        next_y, next_m = (y + 1, 1) if m == 12 else (y, m + 1)
        me = date(next_y, next_m, 1)
        spans.append((ms, me, f"{m:02d}/{y}"))
        y, m = next_y, next_m
    return spans

st.set_page_config(page_title="תזרים", page_icon="📈", layout="wide")
apply_rtl()
tenant_id = require_tenant()

tenant = repo.get_tenant(tenant_id)
st.title(f"תזרים — {tenant.name}")

today = date.today()

horizon_label = st.selectbox("טווח", ["3 חודשים", "6 חודשים", "12 חודשים"], index=1)
horizon_days = {"3 חודשים": 90, "6 חודשים": 180, "12 חודשים": 365}[horizon_label]

df = forecast.monthly_cash_breakdown(tenant_id, start_date=today, horizon_days=horizon_days)

if df.empty:
    st.info("אין נתונים בטווח שנבחר.")
    st.stop()

month_labels_chart = [d.strftime("%m/%Y") for d in df["period"]]

fig = go.Figure()
fig.add_trace(go.Bar(
    x=month_labels_chart,
    y=df["incomes"],
    name="הכנסות",
    marker_color="#1a7f37",
    text=[fmt_currency(v, tenant.currency) for v in df["incomes"]],
    textposition="outside",
))
fig.add_trace(go.Bar(
    x=month_labels_chart,
    y=df["expenses"],
    name="הוצאות",
    marker_color="#cf222e",
    text=[fmt_currency(v, tenant.currency) for v in df["expenses"]],
    textposition="outside",
))
fig.add_trace(go.Bar(
    x=month_labels_chart,
    y=df["debt_payments"],
    name="החזר חובות",
    marker_color="#bf8700",
    text=[fmt_currency(v, tenant.currency) for v in df["debt_payments"]],
    textposition="outside",
))
fig.add_trace(go.Scatter(
    x=month_labels_chart,
    y=df["net"],
    name="נטו",
    mode="lines+text",
    line=dict(color="#0969da", width=3),
    text=[fmt_currency(v, tenant.currency) for v in df["net"]],
    textposition="top center",
))

fig.update_layout(
    barmode="group",
    height=460,
    margin=dict(l=10, r=10, t=30, b=10),
    yaxis=dict(tickprefix="₪ ", tickformat=",.0f", title=""),
    xaxis=dict(title="", autorange="reversed", type="category"),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    hovermode="x unified",
    font=dict(family="Heebo, sans-serif", size=13),
    bargap=0.25,
)
st.plotly_chart(fig, use_container_width=True)

# Summary table -------------------------------------------------------------
st.subheader("פירוט חודשי")
display = df.copy()
display.columns = ["חודש", "הכנסות", "הוצאות", "החזר חובות", "נטו"]
st.dataframe(
    display,
    use_container_width=True,
    hide_index=True,
    column_config={
        "חודש": st.column_config.DateColumn(format="MM/YYYY"),
        "הכנסות": st.column_config.NumberColumn(format=money_format()),
        "הוצאות": st.column_config.NumberColumn(format=money_format()),
        "החזר חובות": st.column_config.NumberColumn(format=money_format()),
        "נטו": st.column_config.NumberColumn(format=money_format()),
    },
)

# Debt installment matrix --------------------------------------------------
st.divider()
st.subheader("פריסת חובות לחודשים")
st.caption(
    "מטריצה של חובות פתוחים מול 12 החודשים הקרובים. כל תא הוא הסכום המתוכנן לתשלום "
    "באותו חוב באותו חודש. אפשר לערוך תאים ישירות (כולל העברת סכום מחודש לחודש) "
    "ולשמור — האפליקציה תיצור / תעדכן / תמחק הסדרי תשלומים בהתאם. "
    "תשלומים שכבר סומנו כשולמו לא משתנים."
)

open_debts = [d for d in repo.list_debts(tenant_id, only_open=True)
              if max(d.original_amount - d.paid_amount, 0.0) > 0]

if not open_debts:
    st.info("אין חובות פתוחים לפריסה.")
else:
    matrix_horizon = st.selectbox(
        "אופק תכנון",
        options=[6, 12, 18, 24],
        format_func=lambda n: f"{n} חודשים",
        index=1,
        key="matrix_horizon",
    )
    months = _month_spans(today.replace(day=1), matrix_horizon)
    month_labels = [label for _, _, label in months]

    # Per debt, partition installments into (month-totals scheduled, month-totals
    # already-paid, total-paid-already, total-scheduled). The matrix shows the
    # scheduled-only amounts so editing affects the plan, not history.
    rows = []
    locked_paid_per_cell: dict[tuple[int, str], float] = {}
    for debt in open_debts:
        installments = repo.list_debt_installments(tenant_id, debt.id)
        remaining = max(debt.original_amount - debt.paid_amount, 0.0)
        scheduled_total = 0.0
        row: dict = {"_id": debt.id, "נושה": debt.creditor, "יתרה": remaining}
        for ms, me, label in months:
            scheduled_in_month = sum(
                inst.amount for inst in installments
                if inst.status != "paid" and ms <= inst.due_date < me
            )
            paid_in_month = sum(
                inst.amount for inst in installments
                if inst.status == "paid" and ms <= inst.due_date < me
            )
            row[label] = float(scheduled_in_month)
            locked_paid_per_cell[(debt.id, label)] = float(paid_in_month)
            scheduled_total += scheduled_in_month
        row["לא מוקצה"] = float(remaining - scheduled_total)
        rows.append(row)

    matrix_df = pd.DataFrame(rows)

    column_config: dict = {
        "_id": None,  # hidden
        "נושה": st.column_config.TextColumn("נושה", disabled=True),
        "יתרה": st.column_config.NumberColumn("יתרה פתוחה", format=money_format(), disabled=True),
        "לא מוקצה": st.column_config.NumberColumn(
            "לא מוקצה", format=money_format(), disabled=True,
            help="היתרה שעוד לא הוקצתה לחודש. שלילי = הקצית יותר מהיתרה.",
        ),
    }
    for label in month_labels:
        column_config[label] = st.column_config.NumberColumn(
            label, format=money_format(), min_value=0.0, step=100.0,
        )

    edited_df = st.data_editor(
        matrix_df,
        use_container_width=True,
        hide_index=True,
        column_config=column_config,
        column_order=["נושה", "יתרה"] + month_labels + ["לא מוקצה"],
        num_rows="fixed",
        key="debt_matrix_editor",
    )

    # Per-month totals row -------------------------------------------------
    # Lets the user see how the plan distributes load across months and
    # spot months that are too heavy. Updates live as the editor changes.
    totals_row: dict = {"שורה": "סה״כ חודשי"}
    grand_total = 0.0
    for label in month_labels:
        col_total = float(edited_df[label].fillna(0).sum())
        totals_row[label] = col_total
        grand_total += col_total
    totals_row["סה״כ"] = grand_total

    totals_config: dict = {
        "שורה": st.column_config.TextColumn("", disabled=True),
        "סה״כ": st.column_config.NumberColumn("סה״כ כל החודשים", format=money_format(), disabled=True),
    }
    for label in month_labels:
        totals_config[label] = st.column_config.NumberColumn(
            label, format=money_format(), disabled=True,
        )
    st.caption("סיכום החזרים מתוכננים לכל חודש (לאיזון העומס בין החודשים):")
    st.dataframe(
        pd.DataFrame([totals_row]),
        use_container_width=True,
        hide_index=True,
        column_config=totals_config,
        column_order=["שורה"] + month_labels + ["סה״כ"],
    )

    save_col, info_col = st.columns([1, 3])
    if save_col.button("שמור פריסה", type="primary", key="save_matrix"):
        n_changes = 0
        for i, debt in enumerate(open_debts):
            for ms, me, label in months:
                old_val = float(matrix_df.at[i, label])
                new_val = float(edited_df.at[i, label] or 0)
                if abs(new_val - old_val) <= 0.01:
                    continue
                # Replace SCHEDULED installments in this month for this debt.
                # Already-paid installments in the same month are left alone.
                for inst in repo.list_debt_installments(tenant_id, debt.id):
                    if inst.status == "paid":
                        continue
                    if ms <= inst.due_date < me:
                        repo.delete_debt_installment(tenant_id, inst.id)
                if new_val > 0.01:
                    repo.create_debt_installment(
                        tenant_id, debt.id,
                        due_date=ms,
                        amount=round(new_val, 2),
                        status="scheduled",
                    )
                n_changes += 1
        if n_changes:
            st.success(f"נשמרו {n_changes} שינויים בפריסה.")
            st.rerun()
        else:
            info_col.info("לא נמצאו שינויים.")

    info_col.caption(
        "💡 טיפ: כדי 'להעביר' סכום מחודש אחד לאחר, הקלידי 0 בחודש הראשון "
        "ואת הסכום המבוקש בחודש החדש. סכום בעמודה 'לא מוקצה' שלא הוקצה — "
        "אפשר להחליט אחר כך."
    )

# Manual cash event entry ---------------------------------------------------
st.divider()
st.subheader("רישום תנועה ידנית")
with st.form("manual_cash", clear_on_submit=True):
    c1, c2, c3 = st.columns(3)
    direction = c1.selectbox("כיוון", ["in", "out"], format_func=lambda x: "כניסה" if x == "in" else "יציאה")
    amount = c2.number_input("סכום (₪)", min_value=0.0, step=100.0, format="%.2f")
    event_date = c3.date_input("תאריך", value=today)
    description = st.text_input("תיאור")

    if st.form_submit_button("הוסף תנועה", type="primary"):
        if amount <= 0:
            st.error("סכום חיובי חובה.")
        else:
            repo.create_cash_event(
                tenant_id,
                date=event_date,
                direction=direction,
                amount=amount,
                description=description.strip() or "תנועה ידנית",
                source_type="manual",
            )
            st.success("נוסף.")
            st.rerun()

# Recent events list --------------------------------------------------------
st.subheader("תנועות שנרשמו (היסטוריה ועתיד קרוב)")
events = repo.list_cash_events(tenant_id)
if not events:
    st.caption("אין תנועות רשומות.")
else:
    rows = [{
        "id": e.id,
        "תאריך": e.date,
        "כיוון": "כניסה" if e.direction == "in" else "יציאה",
        "סכום": e.amount,
        "תיאור": e.description,
        "מקור": e.source_type,
    } for e in events]
    df_events = pd.DataFrame(rows)
    st.dataframe(
        df_events.drop(columns=["id"]),
        use_container_width=True,
        hide_index=True,
        column_config={
            "תאריך": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "סכום": st.column_config.NumberColumn(format=money_format()),
        },
    )

    st.divider()
    st.subheader("ניהול תנועה קיימת")
    options = {f"{fmt_date(e.date)} — {e.description} ({fmt_currency(e.amount)})": e.id for e in events}
    label = st.selectbox("בחר תנועה", list(options.keys()))
    event_id = options[label]
    event = next(e for e in events if e.id == event_id)

    tab_quick, tab_edit = st.tabs(["פעולות מהירות", "עריכה מלאה"])
    with tab_quick:
        if st.button("מחק תנועה", key="ce_delete"):
            repo.delete_cash_event(tenant_id, event_id)
            st.success("נמחק.")
            st.rerun()

    with tab_edit:
        with st.form(f"edit_cash_{event_id}"):
            c1, c2, c3 = st.columns(3)
            e_dir = c1.selectbox(
                "כיוון", ["in", "out"],
                index=0 if event.direction == "in" else 1,
                format_func=lambda x: "כניסה" if x == "in" else "יציאה",
                key=f"e_ce_dir_{event_id}",
            )
            e_amount = c2.number_input(
                "סכום (₪)", min_value=0.0, step=100.0,
                value=float(event.amount), format="%.2f", key=f"e_ce_amount_{event_id}",
            )
            e_date = c3.date_input("תאריך", value=event.date, key=f"e_ce_date_{event_id}")
            e_desc = st.text_input("תיאור", value=event.description, key=f"e_ce_desc_{event_id}")
            if st.form_submit_button("שמור שינויים", type="primary"):
                if e_amount <= 0:
                    st.error("סכום חיובי חובה.")
                else:
                    repo.update_cash_event(
                        tenant_id, event_id,
                        direction=e_dir,
                        amount=e_amount,
                        date=e_date,
                        description=e_desc.strip() or "תנועה ידנית",
                    )
                    st.success("עודכן.")
                    st.rerun()
