import streamlit as st
import requests
import pandas as pd

st.set_page_config(
    page_title="Performance Anomaly Detector",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="📊",
)

API_BASE = "http://localhost:8000"
METRICS = ["latency_p95", "throughput", "cpu", "memory", "disk", "queries/sec"]

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

        .placeholder-badge {
            display: inline-block;
            background-color: rgba(240, 196, 25, 0.12);
            color: #f0c419;
            border: 1px solid rgba(240, 196, 25, 0.35);
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.78rem;
            font-weight: 600;
            letter-spacing: 0.02em;
            margin-bottom: 1rem;
        }

        .anomaly-card {
            border-radius: 10px;
            padding: 0.9rem 1.1rem;
            margin-bottom: 0.6rem;
            border-left: 4px solid;
        }
        .sev-high   { background: rgba(239, 68, 68, 0.08);  border-color: #ef4444; }
        .sev-medium { background: rgba(249, 115, 22, 0.08); border-color: #f97316; }
        .sev-low    { background: rgba(234, 179, 8, 0.08);  border-color: #eab308; }

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
with st.sidebar:
    st.header("⚙️ Controls")
    selected_metric = st.selectbox("Metric", METRICS)
    start_dt = st.text_input("Start (ISO)", value="2026-09-23T00:00:00")
    end_dt = st.text_input("End (ISO)", value="2026-09-24T23:59:59")
    fetch_clicked = st.button("🔍 Fetch Latest Data", use_container_width=True, type="primary")

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
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()

            if "error" in data:
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

                with st.expander("View raw response"):
                    st.json(data)

        except requests.exceptions.RequestException as e:
            st.error(f"API unavailable — is FastAPI running at {API_BASE}? ({e})")
    else:
        st.info("Pick a metric and date range in the sidebar, then click **Fetch Latest Data**.", icon="👈")

with tab_anomalies:
    st.markdown('<span class="placeholder-badge">⚠️ PLACEHOLDER DATA — real detection ships Week 5</span>', unsafe_allow_html=True)

    try:
        anomalies_resp = requests.get(f"{API_BASE}/anomalies", params={"days": 7}, timeout=5)
        anomalies_resp.raise_for_status()
        anomalies_data = anomalies_resp.json()

        if anomalies_data.get("count", 0) == 0:
            st.warning("No data for this range", icon="📭")
        else:
            severity_icon = {"high": "🔴", "medium": "🟠", "low": "🟡"}

            for a in anomalies_data["anomalies"]:
                icon = severity_icon.get(a["severity"], "⚪")
                delta = a["value"] - a["baseline"]
                pct = (delta / a["baseline"] * 100) if a["baseline"] else 0

                st.markdown(
                    f"""
                    <div class="anomaly-card sev-{a['severity']}">
                        <b>{icon} {a['metric']}</b> &nbsp;·&nbsp; <span style="color:#9aa0a6;">{a['date']}</span>
                        &nbsp;·&nbsp; <b>{a['severity'].upper()}</b><br>
                        <span style="color:#9aa0a6;">
                            value <b style="color:#e5e7eb;">{a['value']}</b> vs baseline
                            <b style="color:#e5e7eb;">{a['baseline']}</b>
                            ({'+' if delta >= 0 else ''}{delta:.0f}, {pct:+.1f}%)
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    except requests.exceptions.RequestException as e:
        st.error(f"API unavailable — is FastAPI running at {API_BASE}? ({e})")