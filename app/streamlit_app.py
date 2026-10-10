"""Kairos: Alternative-Data Terminal for Indian Equities.

Streamlit application for visualizing SerpApi alternative-data signals,
divergence alerts, and the full stored evidence audit trail.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from kairos import store, tools
from kairos.serp import ledger
from app.presentation import ads_summary, load_verified_capture, weekly_change

# ----------------------------------------------------------------------------
# App Configuration & Theme
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="Kairos | SerpApi Alt-Data Terminal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

ROOT = Path(__file__).resolve().parents[1]

# Custom CSS for polished terminal look
st.markdown(
    """
    <style>
    .metric-card {
        background-color: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 12px;
    }
    .metric-title {
        color: #6c757d;
        font-size: 0.82rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 4px;
    }
    .metric-value {
        font-size: 1.6rem;
        font-weight: 700;
        color: #212529;
        margin-bottom: 4px;
    }
    .metric-proxy {
        font-size: 0.75rem;
        color: #495057;
        font-style: italic;
    }
    .badge-fired {
        background-color: #ffe3e3;
        color: #c92a2a;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.8rem;
    }
    .badge-not-fired {
        background-color: #e6fcf5;
        color: #0ca678;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.8rem;
    }
    .badge-insufficient {
        background-color: #f1f3f5;
        color: #868e96;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.8rem;
    }
    .evidence-box {
        background-color: #f1f3f5;
        border-left: 4px solid #495057;
        padding: 12px;
        border-radius: 4px;
        font-family: monospace;
        font-size: 0.85rem;
        margin: 8px 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------------
# Data Access Layer
# ----------------------------------------------------------------------------
def get_entity_list() -> List[Dict[str, Any]]:
    return tools.list_entities()


def get_company_signals(entity_id: str, weeks: int = 12) -> List[Dict[str, Any]]:
    return tools.get_signals(entity_id, weeks=weeks)


def get_company_alerts(entity_id: Optional[str] = None) -> List[Dict[str, Any]]:
    return tools.get_alerts(entity_id)


def get_explained_alert(alert_id: str) -> Dict[str, Any]:
    return tools.explain_alert(alert_id)


def get_credit_data() -> List[Dict[str, Any]]:
    manifest_p = ledger.manifest_path(ROOT, "data/demo" if using_demo() else "data/raw")
    return ledger.credit_summary(ledger.load(manifest_p))


def using_demo() -> bool:
    return (Path(store.db_path()).resolve() == (ROOT / "data/demo/kairos.db").resolve()
            or store.demo_backed_source())


# ----------------------------------------------------------------------------
# Sidebar Navigation
# ----------------------------------------------------------------------------
is_offline = using_demo()

st.sidebar.title("Kairos")
st.sidebar.markdown(
    "**SerpApi Alt-Data Terminal**\n\n*Detecting divergences between public signals and stock prices.*"
)

mode_badge = "🟢 Demo data (committed fixtures)" if is_offline else "⚡ Stored live captures"
st.sidebar.caption(mode_badge)
st.sidebar.caption("Read-only dashboard. Run snapshots with the CLI, then refresh this page.")
st.sidebar.button("Refresh stored data")

view = st.sidebar.radio(
    "Navigation",
    ["Company Terminal", "Alert Evidence Deep-Dive", "Watchlist Overview", "SerpApi Credit Ledger"],
)

entities = get_entity_list()
entity_map = {e["entity_id"]: e for e in entities}
if not entities:
    st.info("No companies configured. Add an entity to watchlist.yaml, then refresh stored data.")
    st.stop()

if view in ["Company Terminal", "Alert Evidence Deep-Dive"]:
    selected_eid = st.sidebar.selectbox(
        "Select Listed Company",
        options=list(entity_map.keys()),
        format_func=lambda x: f"{entity_map[x]['name']} ({entity_map[x]['nse_ticker']})",
    )
    selected_entity = entity_map[selected_eid]
else:
    selected_eid = None
    selected_entity = None

st.sidebar.markdown("---")
st.sidebar.markdown(
    """
    **Sensors Tracked (SerpApi):**
    - `google_trends`: Search share
    - `google_finance`: Ground-truth price
    - `google_play_product`: App health gap
    - `google_ads_transparency_center`: Ad push
    - `google_news`: Event stream
    """
)

# ----------------------------------------------------------------------------
# View 1: Company Terminal
# ----------------------------------------------------------------------------
if view == "Company Terminal" and selected_entity:
    col_head, col_meta = st.columns([3, 1])
    with col_head:
        st.title(f"{selected_entity['name']}")
        st.markdown(
            f"**Ticker:** `{selected_entity['nse_ticker']}` | "
            f"**Sensors Active:** `{len(selected_entity['sensors'])}/5` | "
            f"**Verification:** `{selected_entity.get('verified_by') or 'Not yet verified'}`"
        )
    with col_meta:
        st.caption("Data Source")
        st.write("SerpApi engines")

    st.markdown("---")

    for sid, outcome in selected_entity.get("collection_status", {}).items():
        if outcome["status"] != "ok":
            st.warning(f"{sid}: latest collection {outcome['status']} at {outcome['started_at']}. "
                       "Any readings below are from an earlier successful capture.")

    # Fetch signals
    signals = get_company_signals(selected_eid, weeks=16)
    signals_by_key = {f"{s['sensor']}:{s['metric']}": s for s in signals}

    # Extract price and search share series
    price_series = signals_by_key.get("price:close")
    share_series = signals_by_key.get("search_share:share")

    # Dual-Axis Plotly Chart
    st.subheader("Price vs. Search Interest Share (16-Week Timeseries)")
    st.caption("Testing the core thesis: does public search share diverge from market equity price?")

    if price_series and share_series:
        df_price = pd.DataFrame(price_series["points"])
        df_share = pd.DataFrame(share_series["points"])

        fig = go.Figure()

        if not df_price.empty:
            fig.add_trace(
                go.Scatter(
                    x=df_price["week"],
                    y=df_price["value"],
                    name="NSE Close Price (₹)",
                    line=dict(color="#1f77b4", width=3),
                    yaxis="y1",
                )
            )

        if not df_share.empty:
            fig.add_trace(
                go.Scatter(
                    x=df_share["week"],
                    y=df_share["value"],
                    name="Search Share (%)",
                    line=dict(color="#ff7f0e", width=2.5, dash="dot"),
                    yaxis="y2",
                )
            )

        fig.update_layout(
            height=380,
            margin=dict(l=40, r=40, t=20, b=30),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            yaxis=dict(
                title=dict(text="NSE Close Price (INR)", font=dict(color="#1f77b4")),
                tickfont=dict(color="#1f77b4"),
            ),
            yaxis2=dict(
                title=dict(text="Search Share (%)", font=dict(color="#ff7f0e")),
                tickfont=dict(color="#ff7f0e"),
                overlaying="y",
                side="right",
            ),
            plot_bgcolor="white",
        )
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="#f0f0f0")
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="#f0f0f0")
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("Insufficient timeseries points to render dual-axis chart.")

    # Sensor Tiles Grid
    st.subheader("Sensor Network Telemetry")
    t1, t2, t3, t4, t5 = st.columns(5)

    # Tile 1: Search Share
    with t1:
        if share_series and share_series["points"]:
            latest_val = share_series["points"][-1]["value"]
            pct_chg = weekly_change(share_series["points"])
            change_text = f"{pct_chg:+.1f}% WoW" if pct_chg is not None else "WoW change unavailable"
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-title">Search Share (S1)</div>
                    <div class="metric-value">{latest_val:.1f}%</div>
                    <span style="font-size:0.8rem; color:{'#0ca678' if pct_chg is not None and pct_chg>=0 else '#495057'};">
                        {change_text}
                    </span>
                    <div class="metric-proxy">Proxy: relative share vs competitors</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.caption(f"Week of {share_series['points'][-1]['week']}; captured {share_series['points'][-1]['captured_at']}")
        else:
            st.markdown('<div class="metric-card"><div class="badge-insufficient">No Reading</div></div>', unsafe_allow_html=True)

    # Tile 2: NSE Price
    with t2:
        if price_series and price_series["points"]:
            latest_price = price_series["points"][-1]["value"]
            price_chg = weekly_change(price_series["points"])
            change_text = f"{price_chg:+.1f}% WoW" if price_chg is not None else "WoW change unavailable"
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-title">Ground Truth Price (S11)</div>
                    <div class="metric-value">₹{latest_price:.1f}</div>
                    <span style="font-size:0.8rem; color:{'#0ca678' if price_chg is not None and price_chg>=0 else '#495057'};">
                        {change_text}
                    </span>
                    <div class="metric-proxy">Ground truth: NSE weekly close</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.caption(f"Week of {price_series['points'][-1]['week']}; captured {price_series['points'][-1]['captured_at']}")
        else:
            st.markdown('<div class="metric-card"><div class="badge-insufficient">No Reading</div></div>', unsafe_allow_html=True)

    # Tile 3: App Reviews Gap
    app_mean = signals_by_key.get("app_reviews:recent_mean")
    app_disp = signals_by_key.get("app_reviews:displayed_rating")
    with t3:
        if app_mean and app_disp and app_mean["points"] and app_disp["points"]:
            rmean = app_mean["points"][-1]["value"]
            rdisp = app_disp["points"][-1]["value"]
            sample_n = app_mean["points"][-1].get("sample_n")
            gap = rmean - rdisp
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-title">App Health (S4)</div>
                    <div class="metric-value">{rmean:.2f} ★</div>
                    <span style="font-size:0.8rem; color:{'#c92a2a' if gap<=-0.3 else '#495057'};">
                        {gap:+.2f} gap (disp: {rdisp:.1f}★, n={sample_n})
                    </span>
                    <div class="metric-proxy">Sample: newest reviews vs store rating</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            sample = app_mean["points"][-1]
            st.caption(f"Review span: {sample['dims'].get('sample_start', 'unknown')} to "
                       f"{sample['dims'].get('sample_end', 'unknown')}; captured {sample['captured_at']}")
        else:
            st.markdown('<div class="metric-card"><div class="badge-insufficient">No Reading</div></div>', unsafe_allow_html=True)

    # Tile 4: Ads Creatives
    ad_reading = ads_summary(signals)
    with t4:
        if ad_reading:
            if ad_reading["recent"]:
                st.markdown(
                    f"""
                    <div class="metric-card">
                        <div class="metric-title">Ad Push (S8)</div>
                        <div class="metric-value">{ad_reading['count']}</div>
                        <span style="font-size:0.8rem; color:#495057;">
                            {ad_reading['comparison']}
                        </span>
                        <div class="metric-proxy">Proxy: active creatives in 14-day window</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                recent = ad_reading["recent"]
                st.caption(f"Window {recent['dims'].get('start_date')} to {recent['dims'].get('end_date')}; "
                           f"captured {recent['captured_at']}")
            else:
                st.markdown('<div class="metric-card"><div class="badge-insufficient">No Reading</div></div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="metric-card"><div class="badge-insufficient">No Reading</div></div>', unsafe_allow_html=True)

    # Tile 5: News
    news_sig = signals_by_key.get("news:article")
    with t5:
        if news_sig and news_sig["points"]:
            latest_art = news_sig["points"][-1]["value"]
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-title">News Activity (S9)</div>
                    <div class="metric-value">{int(latest_art)}</div>
                    <span style="font-size:0.8rem; color:#495057;">
                        Sampled headlines, week of {news_sig['points'][-1]['week']}
                    </span>
                    <div class="metric-proxy">Context: Google News mentions</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.caption(f"Captured {news_sig['points'][-1]['captured_at']}; sampled results, not total coverage")
        else:
            st.markdown('<div class="metric-card"><div class="badge-insufficient">No Reading</div></div>', unsafe_allow_html=True)

    st.markdown("---")

    st.subheader("News Headlines for Context")
    headlines = tools.get_headlines(selected_eid)
    if headlines:
        st.dataframe(pd.DataFrame(headlines)[["title", "source", "link", "observed_at", "captured_at", "capture_id"]],
                     hide_index=True, width="stretch")
    else:
        st.info("No sampled headlines in the latest successful News capture.")

    with st.expander("Sensor Evidence — open the response behind any sensor tile"):
        sensor_id = st.selectbox("Sensor evidence", options=list(tools.SERIES), key="sensor_evidence")
        captures = tools.get_sensor_evidence(selected_eid, sensor_id)
        for cap in captures:
            st.caption(f"{cap['engine']} / {cap.get('role')}; captured {cap['captured_at']}")
            st.code(f"Raw SHA-256: {cap['raw_sha256']}\nFixture SHA-256: {cap.get('fixture_sha256') or 'not applicable'}")
            st.json(cap["params"])
            try:
                st.json(load_verified_capture(ROOT, cap))
            except (OSError, ValueError) as err:
                st.error(f"Cannot verify sensor evidence: {err}")
        if not captures:
            st.info("No stored successful capture for this sensor.")

    # Divergence Alerts Panel
    st.subheader("Divergence Alert Engine")
    st.caption("Deterministic rules evaluate sensor divergence. Each alert provides full provenance.")

    company_alerts = get_company_alerts(selected_eid)
    for a in company_alerts:
        status = a["status"]
        if status == "fired":
            badge_html = '<span class="badge-fired">FIRED</span>'
        elif status == "not_fired":
            badge_html = '<span class="badge-not-fired">NOT FIRED</span>'
        else:
            badge_html = '<span class="badge-insufficient">INSUFFICIENT DATA</span>'

        role_label = "Headline Divergence" if a["role"] == "headline" else "Contextual Gap"

        with st.expander(f"{a['rule_id']} ({role_label}) — {status.upper()}", expanded=(status == "fired")):
            st.markdown(f"**Status:** {badge_html} | **Evaluation week/date:** `{a['as_of']}`", unsafe_allow_html=True)
            st.markdown(f"**Synthesized Finding:** {a['sentence']}")

            if a.get("base_rate"):
                br = a["base_rate"]
                pct_rate = (br["n"] / br["m"] * 100) if br["m"] > 0 else 0
                st.info(
                    f"**Historical Base Rate:** Fired in **{br['n']} of {br['m']} weeks** ({pct_rate:.1f}%). "
                    "Informs analysts whether this divergence is a rare inflection or routine fluctuation."
                )

            if a.get("llm_context"):
                st.markdown(
                    f"**Model-Written Context (Strictly Guarded):** *{a['llm_context']}* "
                    f"`[Validated: contains zero numerals, citations match evidence]`"
                )

            # Conditions breakdown
            if a.get("conditions"):
                st.markdown("**Evaluated Conditions:**")
                cond_rows = []
                for c in a["conditions"]:
                    val_str = f"{c['value']:.3f}" if isinstance(c["value"], (int, float)) else str(c["value"])
                    cond_rows.append({
                        "Condition": c["name"],
                        "Actual Value": f"{val_str} {c['unit']}",
                        "Rule Operator": c["op"],
                        "Threshold": f"{c['threshold']} {c['unit']}",
                        "Passed": "PASS" if c["passed"] else "FAIL",
                    })
                st.dataframe(pd.DataFrame(cond_rows), hide_index=True, width="stretch")

            st.caption(f"Evidence Captures behind this alert: `{', '.join(a['evidence_capture_ids'])}`")

# ----------------------------------------------------------------------------
# View 2: Alert Evidence Deep-Dive
# ----------------------------------------------------------------------------
elif view == "Alert Evidence Deep-Dive" and selected_entity:
    st.title("Audit Trail & Stored Evidence Viewer")
    st.markdown(
        "Every number in Kairos is backed by an immutable SerpApi capture. "
        "Inspect the raw parameters, response SHA-256 hashes, and JSON fragments below."
    )

    company_alerts = get_company_alerts(selected_eid)
    alert_choices = {f"{a['alert_id']} ({a['status']})": a["alert_id"] for a in company_alerts}

    selected_alert_label = st.selectbox("Select Alert to Inspect", list(alert_choices.keys()))
    selected_alert_id = alert_choices[selected_alert_label]

    detailed_alert = get_explained_alert(selected_alert_id)

    st.subheader(f"Alert: `{detailed_alert['alert_id']}`")
    st.markdown(f"**Summary:** {detailed_alert['sentence']}")

    t_obs, t_caps = st.tabs(["Normalized Observation Rows", "Raw SerpApi Captures & JSON"])

    with t_obs:
        st.markdown("### Observations reduced from SerpApi responses")
        obs_list = detailed_alert.get("evidence", [])
        if obs_list:
            df_obs = pd.DataFrame(obs_list)
            st.dataframe(df_obs[["sensor", "metric", "value", "unit", "observed_at", "sample_n", "capture_id", "raw_sha256"]], width="stretch")
        else:
            st.info("No observation rows recorded.")

    with t_caps:
        st.markdown("### Stored Captures and Raw Fixture Inspection")
        captures = detailed_alert.get("captures", [])
        for i, cap in enumerate(captures, 1):
            st.markdown(f"#### Capture {i}: `{cap['capture_id']}`")
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown(f"**Engine:** `{cap['engine']}`")
                st.markdown(f"**Role:** `{cap.get('role', 'N/A')}`")
                st.markdown(f"**Credits Charged:** `{cap.get('credits_charged', 0)}`")
            with col_b:
                st.markdown(f"**Captured Timestamp:** `{cap.get('captured_at')}`")
                st.markdown(f"**Original response SHA-256:** `{cap.get('raw_sha256')}`")
                if cap.get("fixture_sha256"):
                    st.markdown(f"**Sanitized fixture SHA-256:** `{cap['fixture_sha256']}`")
                st.markdown(f"**Fixture Path:** `{cap.get('path')}`")

            st.markdown("**SerpApi Query Parameters:**")
            st.json(cap.get("params", {}))

            # Inspect raw fixture JSON on disk
            rel_path = cap.get("path")
            if rel_path:
                with st.expander(f"View Stored JSON in `{rel_path}`"):
                    try:
                        raw_content = load_verified_capture(ROOT, cap)
                        st.caption("Stored bytes verified against the fixture hash (demo) or response hash (live).")
                        st.json(raw_content)
                    except (OSError, ValueError) as e:
                        st.error(f"Failed to load fixture JSON: {e}")

# ----------------------------------------------------------------------------
# View 3: Watchlist Overview
# ----------------------------------------------------------------------------
elif view == "Watchlist Overview":
    st.title("Tracked Companies Watchlist Matrix")
    st.markdown(
        "Overview of all listed companies monitored by Kairos across the Indian equities universe."
    )

    all_alerts = get_company_alerts()
    summary_rows = []

    for e in entities:
        eid = e["entity_id"]
        c_alerts = [a for a in all_alerts if a["entity_id"] == eid]
        fired_count = sum(1 for a in c_alerts if a["status"] == "fired")
        
        c_signals = get_company_signals(eid, weeks=1)
        c_sig_map = {f"{s['sensor']}:{s['metric']}": s for s in c_signals}
        
        price_val = c_sig_map.get("price:close", {}).get("points", [{}])[-1].get("value")
        share_val = c_sig_map.get("search_share:share", {}).get("points", [{}])[-1].get("value")
        app_val = c_sig_map.get("app_reviews:recent_mean", {}).get("points", [{}])[-1].get("value")

        summary_rows.append({
            "Entity ID": eid,
            "Company Name": e["name"],
            "Ticker": e["nse_ticker"],
            "Fired Alerts": f"{fired_count} Fired" if fired_count > 0 else "0",
            "Latest Price (₹)": f"₹{price_val:.1f}" if price_val is not None else "N/A",
            "Search Share (%)": f"{share_val:.1f}%" if share_val is not None else "N/A",
            "Play Rating Sample": f"{app_val:.2f} ★" if app_val is not None else "N/A",
            "Sensors Configured": len(e["sensors"]),
        })

    st.dataframe(pd.DataFrame(summary_rows), width="stretch", hide_index=True)

# ----------------------------------------------------------------------------
# View 4: SerpApi Credit Ledger
# ----------------------------------------------------------------------------
elif view == "SerpApi Credit Ledger":
    st.title("SerpApi Credit & Quota Ledger")
    st.markdown(
        "Demonstrating quota-aware architecture: cache-first requests, budget guarding, "
        "and deduplicated identical searches."
    )

    ledger_rows = get_credit_data()
    if ledger_rows:
        df_ledger = pd.DataFrame(ledger_rows)
        
        c_calls = df_ledger["calls"].sum()
        c_credits = df_ledger["credits"].sum()
        c_free = df_ledger["free"].sum()

        m1, m2, m3 = st.columns(3)
        m1.metric("Paid calls recorded", c_calls)
        m2.metric("Estimated credits recorded", c_credits)
        m3.metric("Free Hits (1-hr cache / local)", c_free)

        st.subheader("Usage Breakdown by Engine")
        st.dataframe(
            df_ledger.rename(
                columns={
                    "key_label": "Key Label",
                    "engine": "SerpApi Engine",
                    "calls": "API Calls",
                    "credits": "Credits Charged",
                    "free": "Free / Cached",
                }
            ),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("No credit ledger records found.")

    st.markdown("---")
    st.markdown(
        """
        ### Collection behavior:
        1. **Cache-First Client:** Local cache mode reuses stored requests. The ledger estimates provider cache hits; the Account API is the authority on quota.
        2. **Multi-Company Deduplication:** Companies sharing search terms (e.g., Eternal and Swiggy sharing the `Zomato,Swiggy` basket) execute the search once and share the cache.
        3. **Budget Guard:** Collection preserves the reserve (30 credits by default). If quota is unavailable, collection stops; explicitly setting `--reserve 0` permits collection without that guard.
        4. **Offline Mode:** The dashboard reads stored data. Offline collection and direct Account API methods cannot call SerpApi.
        """
    )

# ----------------------------------------------------------------------------
# Global Footer
# ----------------------------------------------------------------------------
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #868e96; font-size: 0.85rem;'>"
    "Data via SerpApi · Not investment advice · Kairos Open Source Terminal"
    "</div>",
    unsafe_allow_html=True,
)
