from datetime import date

import plotly.graph_objects as go
import streamlit as st

from core import forecast, repository as repo
from core.formatting import fmt_currency, fmt_date
from ui.rtl import apply_rtl
from ui.tenant_selector import require_tenant

st.set_page_config(page_title="סקירה", page_icon="📊", layout="wide")
apply_rtl()
tenant_id = require_tenant()

tenant = repo.get_tenant(tenant_id)
st.title(f"סקירה — {tenant.name}")

today = date.today()
balance_now = repo.current_balance(tenant_id, as_of=today)
total_debt = forecast.total_open_debt(tenant_id)
overdue = forecast.overdue_debt(tenant_id, as_of=today)
inc_30d = forecast.expected_income_30d(tenant_id, as_of=today)

curve = forecast.cumulative_cash_curve(tenant_id, start_date=today, horizon_days=365)
zero_date = forecast.zero_crossing_date(curve)
recovery_date = forecast.positive_recovery_date(curve)
runway = forecast.runway_months(tenant_id, as_of=today)

# KPI strip ------------------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("יתרת מזומן נוכחית", fmt_currency(balance_now, tenant.currency))
with c2:
    st.metric("סך חוב פתוח", fmt_currency(total_debt, tenant.currency))
with c3:
    st.metric("חוב באיחור", fmt_currency(overdue, tenant.currency))
with c4:
    st.metric("הכנסה צפויה (30 יום)", fmt_currency(inc_30d, tenant.currency))

st.divider()

# Headline message ----------------------------------------------------------
if balance_now < 0:
    if recovery_date is not None:
        days = (recovery_date - today).days
        st.success(
            f"📈 העסק כרגע במינוס. לפי התחזית, היתרה חוזרת לחיובי בתאריך **{fmt_date(recovery_date)}** "
            f"(בעוד {days} ימים)."
        )
    else:
        st.error("⚠️ העסק במינוס וההיסטוגרמה לא מראה חזרה לחיובי בטווח של 12 חודשים. יש לפעול אקטיבית להזרמת הכנסות / דחיית חובות.")
elif zero_date is not None:
    days = (zero_date - today).days
    st.warning(
        f"⚠️ לפי התחזית, יתרת המזומנים תרד מתחת ל-0 בתאריך **{fmt_date(zero_date)}** "
        f"(בעוד {days} ימים)."
    )
    if runway is not None:
        st.caption(f"runway: כ-{runway:.1f} חודשים")
else:
    st.success("✅ לפי התחזית, היתרה נשארת חיובית לאורך כל 12 החודשים הקרובים.")

# Cash curve chart ----------------------------------------------------------
st.subheader("עקומת תזרים מצטברת (12 חודשים קדימה)")

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=curve["date"],
    y=curve["balance"],
    mode="lines",
    name="יתרה חזויה",
    line=dict(color="#0969da", width=3),
    fill="tozeroy",
    fillcolor="rgba(9, 105, 218, 0.08)",
))

fig.add_hline(y=0, line=dict(color="#cf222e", width=2, dash="dash"))

if zero_date is not None:
    fig.add_shape(
        type="line",
        xref="x",
        yref="paper",
        x0=zero_date.isoformat(),
        x1=zero_date.isoformat(),
        y0=0,
        y1=1,
        line=dict(color="#cf222e", width=2, dash="dot"),
    )
    fig.add_annotation(
        xref="x",
        yref="paper",
        x=zero_date.isoformat(),
        y=1.0,
        text="חציית 0",
        showarrow=False,
        yanchor="bottom",
        font=dict(color="#cf222e"),
    )

fig.update_layout(
    height=420,
    margin=dict(l=10, r=10, t=10, b=10),
    xaxis=dict(title="", autorange="reversed", tickformat="%m/%Y"),
    yaxis=dict(title="", tickprefix="₪ ", tickformat=",.0f"),
    hovermode="x unified",
    showlegend=False,
    font=dict(family="Heebo, sans-serif", size=13),
)
st.plotly_chart(fig, use_container_width=True)

# Aging buckets -------------------------------------------------------------
st.subheader("חובות פתוחים לפי גילאי איחור")
buckets = forecast.aging_buckets(tenant_id, as_of=today)
b1, b2, b3, b4 = st.columns(4)
b1.metric("0-30 יום", fmt_currency(buckets["0-30"], tenant.currency))
b2.metric("31-60 יום", fmt_currency(buckets["31-60"], tenant.currency))
b3.metric("61-90 יום", fmt_currency(buckets["61-90"], tenant.currency))
b4.metric("90+ יום (קריטי)", fmt_currency(buckets["90+"], tenant.currency))

bucket_fig = go.Figure(data=[go.Bar(
    x=list(buckets.keys()),
    y=list(buckets.values()),
    marker_color=["#1a7f37", "#bf8700", "#d1242f", "#82071e"],
)])
bucket_fig.update_layout(
    height=260,
    margin=dict(l=10, r=10, t=10, b=10),
    xaxis_title="",
    yaxis=dict(title="", tickprefix="₪ ", tickformat=",.0f"),
    showlegend=False,
    font=dict(family="Heebo, sans-serif", size=13),
)
st.plotly_chart(bucket_fig, use_container_width=True)
