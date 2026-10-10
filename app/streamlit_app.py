import os
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import yaml
from datetime import datetime, timedelta

# ----------------------------------------------------------------------------
# Initialization & Setup
# ----------------------------------------------------------------------------
st.set_page_config(page_title="Kairos", layout="wide")

# Determine mode
OFFLINE_MODE = os.environ.get("KAIROS_OFFLINE", "0") == "1"

st.sidebar.title("Kairos")
st.sidebar.markdown(
    f"**Mode:** {'Offline (Mock Data)' if OFFLINE_MODE else 'Live'}"
)

@st.cache_data
def load_watchlist():
    with open("watchlist.yaml", "r") as f:
        data = yaml.safe_load(f)
    return data.get("entities", [])

watchlist = load_watchlist()
entity_options = {e["entity_id"]: e for e in watchlist}

selected_entity_id = st.sidebar.selectbox(
    "Select Company",
    options=list(entity_options.keys()),
    format_func=lambda x: entity_options[x]["name"]
)
selected_entity = entity_options[selected_entity_id]

# ----------------------------------------------------------------------------
# Mock Data Generators (To be replaced with real db queries later)
# ----------------------------------------------------------------------------

def get_mock_timeseries():
    # 12 weeks of data
    dates = [datetime.now().date() - timedelta(weeks=i) for i in range(12, 0, -1)]
    price = [100 + i * 2 + (i % 3) * 5 for i in range(12)]
    share = [50 - i + (i % 2) * 3 for i in range(12)]
    return pd.DataFrame({
        "Week": dates,
        "Price": price,
        "Search Share": share
    })

def get_mock_sensors():
    return [
        {"metric": "Search Share", "value": "42%", "change": "-15%", "status": "down"},
        {"metric": "NSE Price", "value": "₹132.0", "change": "+8%", "status": "up"},
        {"metric": "App Health (Play)", "value": "3.8", "change": "-0.4 vs displayed", "status": "down"},
        {"metric": "Ad Creatives", "value": "120", "change": "+200%", "status": "up"},
        {"metric": "News Sentiment", "value": "Neutral", "change": "-", "status": "neutral"},
    ]

def get_mock_alerts():
    return [
        {
            "id": "R1",
            "name": "Search interest vs price disconnect",
            "severity": "High",
            "condition": "4-week mean search share vs prior 8 weeks moved > 15% down, while price moved > 8% up.",
            "base_rate": "True in 2 of the last 40 weeks",
            "evidence": {
                "engine": "google_trends & google_finance",
                "time": "2026-10-10 10:00 IST",
                "hash": "a1b2c3d4e5f6",
                "fragment": '{"interest_over_time": ...}'
            }
        },
        {
            "id": "R2",
            "name": "Recent reviews below displayed rating",
            "severity": "Medium",
            "condition": "Recent Play review mean (3.8) is > 0.3 below the displayed rating (4.2).",
            "base_rate": "True in 12 of the last 40 weeks",
            "evidence": {
                "engine": "google_play_product",
                "time": "2026-10-10 10:05 IST",
                "hash": "f6e5d4c3b2a1",
                "fragment": '{"reviews": ...}'
            }
        }
    ]

# ----------------------------------------------------------------------------
# Main UI rendering
# ----------------------------------------------------------------------------

st.title(f"{selected_entity['name']} ({selected_entity['nse_ticker']})")
st.markdown(f"**Primary Brand:** {selected_entity['primary_brand']} | **Domain:** {selected_entity['domain']}")

# --- Sensor Tiles ---
st.subheader("Latest Readings")
sensors = get_mock_sensors()
cols = st.columns(len(sensors))
for col, s in zip(cols, sensors):
    with col:
        color = "red" if s["status"] == "down" else "green" if s["status"] == "up" else "gray"
        st.markdown(f"""
        <div style="padding:10px; border-radius:5px; border:1px solid #ddd;">
            <h4 style="margin:0; font-size:14px; color:#555;">{s['metric']}</h4>
            <h2 style="margin:5px 0;">{s['value']}</h2>
            <span style="color:{color}; font-size:12px;">{s['change']}</span>
        </div>
        """, unsafe_allow_html=True)

st.write("") # spacer

# --- Main Chart ---
st.subheader("Price vs. Search Share")
df = get_mock_timeseries()

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=df["Week"], y=df["Price"], name="Price (₹)",
    line=dict(color='blue', width=2)
))
fig.add_trace(go.Scatter(
    x=df["Week"], y=df["Search Share"], name="Search Share (%)",
    yaxis="y2", line=dict(color='orange', width=2, dash='dot')
))

fig.update_layout(
    yaxis=dict(title="Price (₹)"),
    yaxis2=dict(title="Search Share (%)", overlaying="y", side="right"),
    hovermode="x unified",
    margin=dict(l=0, r=0, t=30, b=0)
)
st.plotly_chart(fig, use_container_width=True)

# --- Alert Panel ---
st.subheader("Active Alerts")
alerts = get_mock_alerts()

if not alerts:
    st.info("No active alerts.")
else:
    for al in alerts:
        with st.expander(f"[{al['severity']}] {al['id']}: {al['name']}"):
            st.write(f"**Condition:** {al['condition']}")
            st.write(f"**Base Rate:** {al['base_rate']}")
            
            st.markdown("#### Evidence Viewer")
            ev = al["evidence"]
            st.code(f"Engine: {ev['engine']}\nTime: {ev['time']}\nHash: {ev['hash']}", language="text")
            st.json(ev['fragment'])

# --- Footer ---
st.markdown("---")
st.markdown("*Data via SerpApi · Not investment advice.*")
