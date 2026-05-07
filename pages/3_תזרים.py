from datetime import date

import plotly.graph_objects as go
import streamlit as st

from core import forecast, repository as repo
from core.formatting import fmt_currency, fmt_date
from ui.rtl import apply_rtl
from ui.tenant_selector import require_tenant

st.set_page_config(page_title="תזרים", page_icon="📈", layout="wide")
apply_rtl()
tenant_id = require_tenant()

tenant = repo.get_tenant(tenant_id)
st.title(f"תזרים — {tenant.name}")

today = date.today()

c1, c2 = st.columns([1, 3])
with c1:
    granularity = st.radio("גרגיריות", ["שבועי", "חודשי"], horizontal=True)
    horizon_label = st.selectbox("טווח", ["3 חודשים", "6 חודשים", "12 חודשים"], index=1)
    horizon_days = {"3 חודשים": 90, "6 חודשים": 180, "12 חודשים": 365}[horizon_label]

if granularity == "שבועי":
    df = forecast.weekly_cash_summary(tenant_id, start_date=today, horizon_days=horizon_days)
    period_label = "שבוע (התחלה)"
else:
    df = forecast.monthly_cash_summary(tenant_id, start_date=today, horizon_days=horizon_days)
    period_label = "חודש (התחלה)"

if df.empty:
    st.info("אין נתונים בטווח שנבחר.")
    st.stop()

fig = go.Figure()
fig.add_trace(go.Bar(
    x=df["period"],
    y=df["delta_in"],
    name="כניסות",
    marker_color="#1a7f37",
))
fig.add_trace(go.Bar(
    x=df["period"],
    y=-df["delta_out"],
    name="יציאות",
    marker_color="#cf222e",
))
fig.add_trace(go.Scatter(
    x=df["period"],
    y=df["net"],
    name="נטו",
    mode="lines+markers",
    line=dict(color="#0969da", width=2),
))

fig.update_layout(
    barmode="relative",
    height=420,
    margin=dict(l=10, r=10, t=10, b=10),
    yaxis_title=tenant.currency,
    legend=dict(orientation="h"),
    hovermode="x unified",
)
st.plotly_chart(fig, use_container_width=True)

# Summary table -------------------------------------------------------------
st.subheader("פירוט תקופה")
display = df.copy()
display.columns = [period_label, "כניסות", "יציאות", "נטו"]
st.dataframe(
    display,
    use_container_width=True,
    hide_index=True,
    column_config={
        period_label: st.column_config.DateColumn(format="DD/MM/YYYY"),
        "כניסות": st.column_config.NumberColumn(format="₪%.0f"),
        "יציאות": st.column_config.NumberColumn(format="₪%.0f"),
        "נטו": st.column_config.NumberColumn(format="₪%.0f"),
    },
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
    import pandas as pd
    df_events = pd.DataFrame(rows)
    st.dataframe(
        df_events.drop(columns=["id"]),
        use_container_width=True,
        hide_index=True,
        column_config={
            "תאריך": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "סכום": st.column_config.NumberColumn(format="₪%.0f"),
        },
    )

    delete_options = {f"{fmt_date(e.date)} — {e.description} ({fmt_currency(e.amount)})": e.id for e in events}
    if delete_options:
        with st.expander("מחיקת תנועה"):
            label = st.selectbox("בחר תנועה למחיקה", list(delete_options.keys()))
            if st.button("מחק", key="delete_cash_event"):
                repo.delete_cash_event(tenant_id, delete_options[label])
                st.success("נמחק.")
                st.rerun()
