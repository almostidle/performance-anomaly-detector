import os
from datetime import datetime, timedelta

import streamlit as st
import requests
import pandas as pd

st.set_page_config(
    page_title="Performance Anomaly Detector",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="📊",
)

API_BASE = os.getenv("API_URL") or "http://{}:{}".format(
    os.getenv("API_HOST", "localhost"), os.getenv("API_PORT", "8000")
)
# must match the metric names the collector/detector use
METRICS = [
    "queries_per_sec",
    "latency_p50",
    "latency_p95",
    "cpu_percent",
    "memory_percent",
    "disk_io_percent",
]

# ---------------- styling ----------------
st.markdown(
    """
    <style>
        .block-container { padding-top: 1.5rem; padding-bottom: 3rem; max-width: 1200px; }

        .hero {
            background: linear-gradient(135deg, #1f2937 0%, #111827 100%);
            border: 1px solid #2d3748;
            border-radius: 14px;
            padding: 1.6rem 2rem;
            margin-bottom: 1.6rem;
        }
        .hero h1 { margin: 0; font-size: 1.9rem; }
        .hero p { color: #9aa0a6; margin: 0.3rem 0 0 0; font-size: 0.95rem; }

        div[data-testid="stMetricValue"] { font-size: 1.5rem; font-weight: 700; }
        div[data-testid="stMetric"] {
            background-color: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px;
            padding: 0.8rem 1rem 0.4rem 1rem;
        }

        .anomaly-card {
            border-radius: 10px;
            padding: 0.9rem 1.1rem;
            margin-bottom: 0.6rem;
            border-left: 4px solid;
        }
        .sev-critical { background: rgba(239, 68, 68, 0.08);  border-color: #ef4444; }
        .sev-warning  { background: rgba(249, 115, 22, 0.08); border-color: #f97316; }
        .sev-info     { background: rgba(234, 179, 8, 0.08);  border-color: #eab308; }

        section[data-testid="stSidebar"] { border-right: 1px solid rgba(255,255,255,0.06); }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------- hero header ----------------
st.markdown(
    """
    <div class="hero">
        <h1>📊 Performance Anomaly Detector</h1>
        <p>Live metric monitoring, historical trends & anomaly tracking</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------- sidebar ----------------
now = datetime.now().replace(microsecond=0)
# set defaults ONCE; after that Streamlit keeps whatever you type
if "start_dt" not in st.session_state:
    st.session_state["start_dt"] = (now - timedelta(days=1)).isoformat()
if "end_dt" not in st.session_state:
    st.session_state["end_dt"] = now.isoformat()

with st.sidebar:
    st.header("⚙️ Controls")
    selected_metric = st.selectbox("Metric", METRICS)
    start_dt = st.text_input("Start (ISO)", key="start_dt")
    end_dt = st.text_input("End (ISO)", key="end_dt")
    fetch_clicked = st.button("🔍 Fetch Latest Data", use_container_width=True, type="primary")

    st.divider()
    anomaly_days = st.slider("Anomaly scan (days back)", 1, 30, 7)

    st.divider()
    st.caption("API status")
    try:
        health = requests.get(f"{API_BASE}/health", timeout=2)
        if health.status_code == 200:
            st.success("Online", icon="✅")
        else:
            st.error("Responding with error", icon="⚠️")
    except requests.exceptions.RequestException:
        st.error("Unreachable", icon="🔴")
    st.caption(f"`{API_BASE}`")

# ---------------- tabs ----------------
tab_metrics, tab_anomalies = st.tabs(["📈  Metric Data", "🚨  Anomalies"])

with tab_metrics:
    if fetch_clicked:
        try:
            resp = requests.get(
                f"{API_BASE}/metrics",
                params={"name": selected_metric, "start": start_dt, "end": end_dt},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            # the API can return a [dict, 500] list on failure, so check the shape first
            if not isinstance(data, dict):
                st.error(f"Unexpected API response: {data}")
            elif "error" in data:
                st.error(data["error"])
            elif data.get("count", 0) == 0:
                st.warning("No data for this range", icon="📭")
            else:
                df = pd.DataFrame(data["data"])
                df["ts"] = pd.to_datetime(df["ts"])
                df = df.set_index("ts")

                st.caption(f"Showing **{selected_metric}** · {start_dt} → {end_dt}")

                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Data Points", data["count"])
                col2.metric("Latest", f"{df['val'].iloc[-1]:.1f}")
                col3.metric("Average", f"{df['val'].mean():.1f}")
                col4.metric("Peak", f"{df['val'].max():.1f}")

                st.write("")
                st.line_chart(df["val"], height=340)

                # baseline for this metric (business hours vs nights)
                try:
                    b = requests.get(
                        f"{API_BASE}/baseline",
                        params={"name": selected_metric, "days": 7},
                        timeout=10,
                    ).json().get("baseline", {})
                    bh = (b.get("business_hours") or {}).get("mean")
                    nt = (b.get("nights") or {}).get("mean")
                    st.caption(
                        f"7-day baseline · business hours: **{bh if bh is not None else 'n/a'}** "
                        f"· nights/weekends: **{nt if nt is not None else 'n/a'}**"
                    )
                except Exception:
                    pass

                with st.expander("View raw response"):
                    st.json(data)

        except requests.exceptions.RequestException as e:
            st.error(f"API unavailable — is FastAPI running at {API_BASE}? ({e})")
    else:
        st.info("Pick a metric and date range in the sidebar, then click **Fetch Latest Data**.", icon="👈")

with tab_anomalies:
    try:
        anomalies_resp = requests.get(
            f"{API_BASE}/anomalies", params={"days": anomaly_days}, timeout=30
        )
        anomalies_resp.raise_for_status()
        anomalies_data = anomalies_resp.json()
        events = anomalies_data.get("anomalies", [])

        if not events:
            st.success(f"No anomalies detected in the last {anomaly_days} days.", icon="✅")
        else:
            counts = {"critical": 0, "warning": 0, "info": 0}
            for a in events:
                counts[a["severity"]] = counts.get(a["severity"], 0) + 1

            c1, c2, c3 = st.columns(3)
            c1.metric("🔴 Critical", counts["critical"])
            c2.metric("🟠 Warning", counts["warning"])
            c3.metric("🟡 Info", counts["info"])

            shown = st.multiselect(
                "Show severities",
                ["critical", "warning", "info"],
                default=["critical", "warning", "info"],
            )
            st.write("")

            severity_icon = {"critical": "🔴", "warning": "🟠", "info": "🟡"}
            for a in events:
                if a["severity"] not in shown:
                    continue
                icon = severity_icon.get(a["severity"], "⚪")
                dev = a["deviation_pct"]

                st.markdown(
                    f"""
                    <div class="anomaly-card sev-{a['severity']}">
                        <b>{icon} {a['metric']}</b> &nbsp;·&nbsp; <span style="color:#9aa0a6;">{a['type'].replace('_', ' ')}</span>
                        &nbsp;·&nbsp; <b>{a['severity'].upper()}</b><br>
                        <span style="color:#9aa0a6;">
                            {a['start']} → {a['end']} ({a['readings']} readings)<br>
                            peak <b style="color:#e5e7eb;">{a['peak_value']}</b> vs baseline
                            <b style="color:#e5e7eb;">{a['baseline_value']}</b>
                            ({dev:+.1f}%)<br>
                            💡 {a['root_cause']}
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    except requests.exceptions.RequestException as e:
        st.error(f"API unavailable — is FastAPI running at {API_BASE}? ({e})")