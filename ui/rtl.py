import streamlit as st

_RTL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;500;700&display=swap');

html, body, [class*="css"], .stApp, .block-container {
    direction: rtl;
    font-family: 'Heebo', -apple-system, BlinkMacSystemFont, sans-serif;
}

.stApp {
    text-align: right;
}

[data-testid="stSidebar"] {
    direction: rtl;
    text-align: right;
}

input, textarea, select {
    direction: rtl;
    text-align: right;
}

div[data-testid="stMetricValue"], div[data-testid="stMetricLabel"] {
    direction: rtl;
    text-align: right;
}

.stDataFrame, .stTable {
    direction: rtl;
}

.stDataFrame [data-testid="stTable"] {
    text-align: right;
}

button[kind="primary"], button[kind="secondary"] {
    direction: rtl;
}

div[data-baseweb="select"] {
    direction: rtl;
}

h1, h2, h3, h4, h5, h6 {
    text-align: right;
}

[data-testid="stMarkdownContainer"] p {
    text-align: right;
}

.cash-positive { color: #1a7f37; }
.cash-negative { color: #cf222e; }
.cash-neutral { color: #57606a; }
</style>
"""


def apply_rtl() -> None:
    st.markdown(_RTL_CSS, unsafe_allow_html=True)
