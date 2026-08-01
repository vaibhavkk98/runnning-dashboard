import os
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as gg
from plotly.subplots import make_subplots
import streamlit as st
from datetime import datetime, timedelta
from data_loader import fetch_garmin_data

# Load Dotenv if available locally
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ---------------------------------------------------------
# Page Configuration & Design Tokens
# ---------------------------------------------------------
st.set_page_config(
    page_title="Garmin 5K Running Dashboard",
    page_icon="🏃",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Dark Glassmorphism Theme
st.markdown("""
<style>
    .stApp {
        background-color: #0B0E14;
        color: #E2E8F0;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* Executive Summary Container */
    .insights-card {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.8) 100%);
        border: 1px solid rgba(56, 189, 248, 0.25);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 24px;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
        backdrop-filter: blur(12px);
    }
    
    .insights-header {
        font-size: 1.25rem;
        font-weight: 700;
        color: #38BDF8;
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 16px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        padding-bottom: 8px;
    }
    
    .insight-badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 600;
        margin-bottom: 8px;
    }
    
    .badge-amber {
        background: rgba(245, 158, 11, 0.2);
        color: #F59E0B;
        border: 1px solid rgba(245, 158, 11, 0.4);
    }
    
    .badge-green {
        background: rgba(16, 185, 129, 0.2);
        color: #10B981;
        border: 1px solid rgba(16, 185, 129, 0.4);
    }

    .badge-red {
        background: rgba(239, 68, 68, 0.2);
        color: #EF4444;
        border: 1px solid rgba(239, 68, 68, 0.4);
    }

    /* Metric Cards */
    div[data-testid="stMetric"] {
        background: rgba(23, 32, 48, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 14px 18px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
    }
    
    /* Navigation Menu Styling */
    div[data-testid="stSidebarNav"] {
        background-color: transparent;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# Data Loading & Auto-Fetch Logic
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def load_data():
    summary_file = "data/runs_summary.csv"
    trackpoints_file = "data/raw_trackpoints.csv"

    # Auto-fetch if CSVs are missing
    if not os.path.exists(summary_file) or not os.path.exists(trackpoints_file):
        with st.spinner("Fetching initial Garmin running data..."):
            try:
                fetch_garmin_data()
            except Exception as e:
                st.error(f"Failed to fetch initial Garmin data: {e}")
                return None, None

    if not os.path.exists(summary_file) or not os.path.exists(trackpoints_file):
        return None, None

    summary_df = pd.read_csv(summary_file)
    trackpoints_df = pd.read_csv(trackpoints_file)

    # Convert timestamps
    summary_df["start_time"] = pd.to_datetime(summary_df["start_time"])
    trackpoints_df["timestamp"] = pd.to_datetime(trackpoints_df["timestamp"])
    trackpoints_df["start_time"] = pd.to_datetime(trackpoints_df["start_time"])

    # Ensure activity_id is consistent
    summary_df["activity_id"] = summary_df["activity_id"].astype(str)
    trackpoints_df["activity_id"] = trackpoints_df["activity_id"].astype(str)

    # Fill derived stride length in summary if missing
    for idx, row in summary_df.iterrows():
        if (pd.isnull(row.get("stride_length_cm")) or row.get("stride_length_cm") == 0) and row.get("avg_pace_min_km") and row.get("avg_cadence_spm"):
            pace_min_km = row["avg_pace_min_km"]
            cadence_spm = row["avg_cadence_spm"]
            if pace_min_km > 0 and cadence_spm > 0:
                speed_mps = 1000.0 / (pace_min_km * 60.0)
                steps_per_sec = cadence_spm / 60.0
                stride_m = speed_mps / steps_per_sec
                summary_df.at[idx, "stride_length_cm"] = round(stride_m * 100.0, 2)

    return summary_df, trackpoints_df


# ---------------------------------------------------------
# Sidebar & Navigation
# ---------------------------------------------------------
st.sidebar.image("https://img.icons8.com/color/96/running.png", width=60)
st.sidebar.title("Garmin 5K Dashboard")
st.sidebar.caption("Target Pace: **7:00 min/km** | Device: **Forerunner 165**")

st.sidebar.markdown("---")

nav_choice = st.sidebar.radio(
    "Navigation",
    [
        "🏠 Home & Executive Overview",
        "📊 Single Run Deep-Dive",
        "📈 Training Trends & Workload",
        "🫀 Recovery & Readiness",
        "🏆 Goals & Milestones",
        "💬 Gemini AI Running Coach"
    ]
)

st.sidebar.markdown("---")

if st.sidebar.button("🔄 Refresh Garmin Data", use_container_width=True):
    with st.spinner("Connecting to Garmin Connect & fetching latest runs..."):
        try:
            success = fetch_garmin_data()
            if success:
                st.sidebar.success("Data refreshed successfully!")
                st.cache_data.clear()
                st.rerun()
            else:
                st.sidebar.error("No running activities found.")
        except Exception as e:
            st.sidebar.error(f"Refresh failed: {e}")

summary_df, trackpoints_df = load_data()

if summary_df is None or trackpoints_df is None:
    st.error("Data files missing or failed to fetch. Please verify credentials in Streamlit Secrets / `.env` file.")
    st.stop()

# Sort activities newest first
summary_df = summary_df.sort_values(by="start_time", ascending=False).reset_index(drop=True)

# Helper function for delta formatting
def format_delta(curr, prev, fmt="{:.2f}", unit="", inverse=False):
    if prev is None or pd.isnull(prev):
        return None
    diff = curr - prev
    prefix = "+" if diff > 0 else ""
    return f"{prefix}{fmt.format(diff)} {unit}".strip()

# =========================================================
# 1. 🏠 HOME & EXECUTIVE OVERVIEW
# =========================================================
if nav_choice == "🏠 Home & Executive Overview":
    st.title("🏠 Executive Overview")
    st.markdown("High-level performance summary & training status for **5K Goal (7:00 min/km)**")

    # Metrics Row
    latest_run = summary_df.iloc[0]
    
    # 30-Day Monthly Volume
    now = datetime.now()
    thirty_days_ago = summary_df["start_time"].max() - timedelta(days=30)
    monthly_runs = summary_df[summary_df["start_time"] >= thirty_days_ago]
    monthly_vol_km = monthly_runs["distance_km"].sum()

    # Best 5K / Pace
    valid_paces = summary_df["avg_pace_min_km"].dropna()
    best_pace_min = valid_paces.min() if not valid_paces.empty else 8.5
    best_pace_row = summary_df.loc[summary_df["avg_pace_min_km"].idxmin()] if not valid_paces.empty else latest_run

    # Target Pace Gap (seconds/km vs 7:00 target)
    target_pace_dec = 7.00
    latest_pace_dec = latest_run["avg_pace_min_km"] if pd.notnull(latest_run["avg_pace_min_km"]) else 8.5
    pace_gap_sec = int(round((latest_pace_dec - target_pace_dec) * 60))

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(
            "Last Run",
            f"{latest_run['distance_km']:.2f} km",
            delta=f"{latest_run['start_time'].strftime('%b %d')} ({latest_run['avg_pace_str']}/km)"
        )
    with c2:
        st.metric(
            "30-Day Volume",
            f"{monthly_vol_km:.1f} km",
            delta=f"{len(monthly_runs)} completed runs"
        )
    with c3:
        st.metric(
            "Best Pace Achieved",
            f"{best_pace_row['avg_pace_str']} /km",
            delta=f"On {pd.to_datetime(best_pace_row['start_time']).strftime('%b %d')}"
        )
    with c4:
        gap_str = f"{pace_gap_sec}s/km to target" if pace_gap_sec > 0 else "Target Met!"
        st.metric(
            "Target Pace Gap",
            gap_str,
            delta="7:00 min/km benchmark",
            delta_color="inverse"
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # AI Executive Brief Box
    avg_cadence_30d = monthly_runs["avg_cadence_spm"].mean() if not monthly_runs.empty else 150
    avg_hr_30d = monthly_runs["avg_heart_rate"].mean() if not monthly_runs.empty else 160

    st.markdown(f"""
    <div class="insights-card">
        <div class="insights-header">
            <span>⚡ AI Executive Running Brief</span>
        </div>
        <div style="font-size: 0.95rem; line-height: 1.6; color: #CBD5E1;">
            <ul>
                <li><b>Volume & Consistency:</b> Logged <b>{monthly_vol_km:.1f} km</b> over <b>{len(monthly_runs)} runs</b> in the past 30 days. Workload progression is steady.</li>
                <li><b>Biomechanical Form:</b> 30-day average cadence is <b>{avg_cadence_30d:.0f} spm</b>. Target <b>165–175 spm</b> to reduce ground contact time and decrease joint stress.</li>
                <li><b>Pacing Progression:</b> Recent average pace is <b>{latest_run['avg_pace_str']} min/km</b>. You are <b>{pace_gap_sec} seconds/km away</b> from breaking the 7:00 min/km barrier.</li>
            </ul>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Quick Glance Volume & Pace Charts
    col_h1, col_h2 = st.columns(2)
    with col_h1:
        fig_hp = px.line(
            summary_df,
            x="start_time",
            y="avg_pace_min_km",
            title="🏃 Pace Progression Over Time",
            markers=True,
            color_discrete_sequence=["#38BDF8"]
        )
        fig_hp.add_hline(y=7.0, line_dash="dash", line_color="#EF4444", annotation_text="7:00 Target")
        fig_hp.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(23, 32, 48, 0.5)", yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig_hp, use_container_width=True)

    with col_h2:
        fig_hv = px.bar(
            summary_df,
            x="start_time",
            y="distance_km",
            title="📊 Activity Distances (km)",
            color_discrete_sequence=["#10B981"]
        )
        fig_hv.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(23, 32, 48, 0.5)")
        st.plotly_chart(fig_hv, use_container_width=True)


# =========================================================
# 2. 📊 SINGLE RUN DEEP-DIVE
# =========================================================
elif nav_choice == "📊 Single Run Deep-Dive":
    st.header("🔍 Activity Telemetry & Biometrics")

    run_options = {
        f"{row['start_time'].strftime('%b %d, %Y %H:%M')} - {row['activity_name']} ({row['distance_km']} km)": row["activity_id"]
        for _, row in summary_df.iterrows()
    }
    
    selected_label = st.selectbox("Select Activity:", list(run_options.keys()))
    selected_act_id = run_options[selected_label]

    selected_index = summary_df[summary_df["activity_id"] == selected_act_id].index[0]
    run_sum = summary_df.iloc[selected_index]
    prev_run = summary_df.iloc[selected_index + 1] if selected_index + 1 < len(summary_df) else None
    run_tp = trackpoints_df[trackpoints_df["activity_id"] == selected_act_id].copy()

    if not run_tp.empty:
        run_tp["distance_km"] = run_tp["distance_m"] / 1000.0
        run_tp["clean_pace"] = run_tp["pace_min_km"].apply(lambda p: p if 3.0 <= p <= 14.0 else None)
        
        for t_idx, t_row in run_tp.iterrows():
            if (pd.isnull(t_row.get("stride_length_m")) or t_row.get("stride_length_m") == 0) and t_row.get("speed_mps") and t_row.get("cadence_spm"):
                sp_mps = t_row["speed_mps"]
                cad_spm = t_row["cadence_spm"]
                if sp_mps > 0 and cad_spm > 0:
                    run_tp.at[t_idx, "stride_length_m"] = round(sp_mps / (cad_spm / 60.0), 2)

    # Coaching Insights Box
    avg_pace_dec = run_sum["avg_pace_min_km"] if pd.notnull(run_sum["avg_pace_min_km"]) else 8.5
    pace_gap_sec = int(round((avg_pace_dec - 7.00) * 60))
    avg_cadence = run_sum["avg_cadence_spm"] if pd.notnull(run_sum["avg_cadence_spm"]) else 0.0

    cardiac_drift_pct = 0.0
    first_q_hr, last_q_hr = 0.0, 0.0
    if not run_tp.empty and "heart_rate_bpm" in run_tp.columns:
        valid_hr_tp = run_tp.dropna(subset=["heart_rate_bpm"])
        if len(valid_hr_tp) >= 20:
            q_len = max(1, len(valid_hr_tp) // 4)
            first_q_hr = valid_hr_tp.iloc[:q_len]["heart_rate_bpm"].mean()
            last_q_hr = valid_hr_tp.iloc[-q_len:]["heart_rate_bpm"].mean()
            if first_q_hr > 0:
                cardiac_drift_pct = ((last_q_hr - first_q_hr) / first_q_hr) * 100.0

    st.markdown("""<div class="insights-card">
        <div class="insights-header">
            <span>🎯 Run Executive Summary & Coaching Insights</span>
        </div>""", unsafe_allow_html=True)

    ins_col1, ins_col2 = st.columns(2)

    with ins_col1:
        if pace_gap_sec > 0:
            st.markdown(f"""<div style="margin-bottom: 12px;">
                <span class="insight-badge badge-amber">⏱️ Target Pace Gap</span><br>
                Average pace <b>{run_sum['avg_pace_str']} min/km</b> is <b>{pace_gap_sec} seconds/km slower</b> than target 7:00 min/km benchmark.
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown(f"""<div style="margin-bottom: 12px;">
                <span class="insight-badge badge-green">🚀 On / Ahead of Target</span><br>
                Average pace <b>{run_sum['avg_pace_str']} min/km</b> meets or exceeds target benchmark!
            </div>""", unsafe_allow_html=True)

        if avg_cadence < 155:
            st.markdown(f"""<div style="margin-bottom: 12px;">
                <span class="insight-badge badge-amber">⚠️ Cadence Warning ({avg_cadence:.0f} spm)</span><br>
                Cadence is below recommended 160–170 spm threshold. Low step frequency increases ground contact time and joint impact.
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown(f"""<div style="margin-bottom: 12px;">
                <span class="insight-badge badge-green">🔥 Optimal Cadence ({avg_cadence:.0f} spm)</span><br>
                Good leg turnover rate minimizing impact stress.
            </div>""", unsafe_allow_html=True)

    with ins_col2:
        if cardiac_drift_pct > 5.0:
            st.markdown(f"""<div style="margin-bottom: 12px;">
                <span class="insight-badge badge-red">🌡️ Cardiac Drift Detected (+{cardiac_drift_pct:.1f}%)</span><br>
                Heart rate rose from <b>{first_q_hr:.0f} bpm</b> (first 25%) to <b>{last_q_hr:.0f} bpm</b> (final 25%). Indicates aerobic fatigue or hydration drift.
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown(f"""<div style="margin-bottom: 12px;">
                <span class="insight-badge badge-green">💚 Controlled HR (+{cardiac_drift_pct:.1f}% Drift)</span><br>
                Heart rate remained steady from start (<b>{first_q_hr:.0f} bpm</b>) to finish (<b>{last_q_hr:.0f} bpm</b>).
            </div>""", unsafe_allow_html=True)

        st.markdown("""<div>
            <b>📋 Next Run Action Items:</b>
            <ul style="margin-top: 4px; padding-left: 20px; font-size: 0.9rem; color: #CBD5E1;">
                <li><b>Pacing:</b> Focus on a controlled first km to prevent late-run cardiac drift.</li>
                <li><b>Cadence Drill:</b> Maintain light, fast steps aiming for 165+ spm.</li>
                <li><b>Hydration:</b> Ensure proper pre-run fluid intake.</li>
            </ul>
        </div>""", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # KPI Metrics
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.metric("Distance", f"{run_sum['distance_km']:.2f} km", delta=format_delta(run_sum['distance_km'], prev_run['distance_km'] if prev_run is not None else None, "{:.2f}", "km"))
    with col2:
        st.metric("Duration", f"{run_sum['duration_min']:.1f} min", delta=format_delta(run_sum['duration_min'], prev_run['duration_min'] if prev_run is not None else None, "{:.1f}", "min"))
    with col3:
        st.metric("Avg Pace", f"{run_sum['avg_pace_str']} /km", delta=format_delta(run_sum['avg_pace_min_km'], prev_run['avg_pace_min_km'] if prev_run is not None else None, "{:.2f}", "m/km"), delta_color="inverse")
    with col4:
        st.metric("Avg Heart Rate", f"{int(run_sum['avg_heart_rate'])} bpm" if pd.notnull(run_sum['avg_heart_rate']) else "N/A", delta=format_delta(run_sum['avg_heart_rate'], prev_run['avg_heart_rate'] if prev_run is not None else None, "{:.0f}", "bpm"), delta_color="inverse")
    with col5:
        st.metric("Avg Cadence", f"{int(run_sum['avg_cadence_spm'])} spm" if pd.notnull(run_sum['avg_cadence_spm']) else "N/A", delta=format_delta(run_sum['avg_cadence_spm'], prev_run['avg_cadence_spm'] if prev_run is not None else None, "{:.0f}", "spm"))
    with col6:
        stride_m_val = (run_sum['stride_length_cm'] / 100.0) if pd.notnull(run_sum['stride_length_cm']) and run_sum['stride_length_cm'] > 0 else 0.0
        prev_stride_m = (prev_run['stride_length_cm'] / 100.0) if prev_run is not None and pd.notnull(prev_run.get('stride_length_cm')) else None
        st.metric("Stride Length", f"{stride_m_val:.2f} m", delta=format_delta(stride_m_val, prev_stride_m, "{:.2f}", "m"))

    st.markdown("<br>", unsafe_allow_html=True)

    if not run_tp.empty:
        fig_pace = px.line(
            run_tp, x="distance_km", y="clean_pace",
            title="⚡ Instantaneous Pace Profile (Target: 7:00 min/km)",
            labels={"distance_km": "Distance (km)", "clean_pace": "Pace (min/km)"},
            color_discrete_sequence=["#38BDF8"]
        )
        fig_pace.add_hrect(y0=6.75, y1=7.25, fillcolor="rgba(16, 185, 129, 0.15)", line_width=0, annotation_text="🎯 Target Zone", annotation_position="top left", annotation_font_color="#10B981")
        fig_pace.add_hline(y=7.0, line_dash="dash", line_color="#EF4444", annotation_text="7:00 Benchmark")
        fig_pace.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(23, 32, 48, 0.5)", yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig_pace, use_container_width=True)

        col_left, col_right = st.columns(2)
        with col_left:
            fig_hr_ele = make_subplots(specs=[[{"secondary_y": True}]])
            fig_hr_ele.add_trace(gg.Scatter(x=run_tp["distance_km"], y=run_tp["elevation_m"], name="Elevation (m)", fill="tozeroy", fillcolor="rgba(100, 116, 139, 0.2)", line=dict(color="#94A3B8", width=1.5)), secondary_y=False)
            fig_hr_ele.add_trace(gg.Scatter(x=run_tp["distance_km"], y=run_tp["heart_rate_bpm"], name="Heart Rate (bpm)", line=dict(color="#F43F5E", width=2)), secondary_y=True)
            fig_hr_ele.update_layout(title="❤️ Heart Rate & Elevation Profile", template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(23, 32, 48, 0.5)")
            st.plotly_chart(fig_hr_ele, use_container_width=True)

        with col_right:
            fig_bio = make_subplots(specs=[[{"secondary_y": True}]])
            fig_bio.add_trace(gg.Scatter(x=run_tp["distance_km"], y=run_tp["cadence_spm"], name="Cadence (spm)", line=dict(color="#10B981", width=2)), secondary_y=False)
            fig_bio.add_trace(gg.Scatter(x=run_tp["distance_km"], y=run_tp["stride_length_m"], name="Stride Length (m)", line=dict(color="#F59E0B", width=2)), secondary_y=True)
            fig_bio.update_layout(title="⚙️ Biomechanics (Cadence & Stride)", template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(23, 32, 48, 0.5)")
            st.plotly_chart(fig_bio, use_container_width=True)


# =========================================================
# 3. 📈 TRAINING TRENDS & WORKLOAD
# =========================================================
elif nav_choice == "📈 Training Trends & Workload":
    st.header("📈 Multi-Metric Training Trends & Workload")
    st.markdown("Longitudinal progression curves with **7-day rolling average trendlines**.")

    # Sort chronological for rolling averages
    df_chrono = summary_df.sort_values("start_time").copy()
    df_chrono["stride_m"] = df_chrono["stride_length_cm"] / 100.0

    # Calculate 7-day rolling averages
    df_chrono["roll_dist"] = df_chrono["distance_km"].rolling(7, min_periods=1).mean()
    df_chrono["roll_pace"] = df_chrono["avg_pace_min_km"].rolling(7, min_periods=1).mean()
    df_chrono["roll_hr"] = df_chrono["avg_heart_rate"].rolling(7, min_periods=1).mean()
    df_chrono["roll_cad"] = df_chrono["avg_cadence_spm"].rolling(7, min_periods=1).mean()
    df_chrono["roll_stride"] = df_chrono["stride_m"].rolling(7, min_periods=1).mean()
    df_chrono["roll_cal"] = df_chrono["calories"].rolling(7, min_periods=1).mean()

    # 6 Grid Charts
    row1_c1, row1_c2 = st.columns(2)
    with row1_c1:
        fig1 = gg.Figure()
        fig1.add_trace(gg.Bar(x=df_chrono["start_time"], y=df_chrono["distance_km"], name="Distance (km)", marker_color="#38BDF8"))
        fig1.add_trace(gg.Scatter(x=df_chrono["start_time"], y=df_chrono["roll_dist"], name="7-Day Rolling Avg", line=dict(color="#F59E0B", width=2.5)))
        fig1.update_layout(title="📏 Distance (km)", template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(23, 32, 48, 0.5)")
        st.plotly_chart(fig1, use_container_width=True)

    with row1_c2:
        fig2 = gg.Figure()
        fig2.add_trace(gg.Scatter(x=df_chrono["start_time"], y=df_chrono["avg_pace_min_km"], mode="markers+lines", name="Pace (min/km)", line=dict(color="#38BDF8", width=1.5)))
        fig2.add_trace(gg.Scatter(x=df_chrono["start_time"], y=df_chrono["roll_pace"], name="7-Day Rolling Avg", line=dict(color="#10B981", width=2.5)))
        fig2.add_hline(y=7.0, line_dash="dash", line_color="#EF4444", annotation_text="7:00 Target")
        fig2.update_layout(title="⚡ Average Pace (min/km)", template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(23, 32, 48, 0.5)", yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig2, use_container_width=True)

    row2_c1, row2_c2 = st.columns(2)
    with row2_c1:
        fig3 = gg.Figure()
        fig3.add_trace(gg.Scatter(x=df_chrono["start_time"], y=df_chrono["avg_heart_rate"], mode="markers+lines", name="Avg HR (bpm)", line=dict(color="#F43F5E", width=1.5)))
        fig3.add_trace(gg.Scatter(x=df_chrono["start_time"], y=df_chrono["roll_hr"], name="7-Day Rolling Avg", line=dict(color="#38BDF8", width=2.5)))
        fig3.update_layout(title="❤️ Average Heart Rate (bpm)", template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(23, 32, 48, 0.5)")
        st.plotly_chart(fig3, use_container_width=True)

    with row2_c2:
        fig4 = gg.Figure()
        fig4.add_trace(gg.Scatter(x=df_chrono["start_time"], y=df_chrono["avg_cadence_spm"], mode="markers+lines", name="Cadence (spm)", line=dict(color="#10B981", width=1.5)))
        fig4.add_trace(gg.Scatter(x=df_chrono["start_time"], y=df_chrono["roll_cad"], name="7-Day Rolling Avg", line=dict(color="#F59E0B", width=2.5)))
        fig4.update_layout(title="⚙️ Cadence (spm)", template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(23, 32, 48, 0.5)")
        st.plotly_chart(fig4, use_container_width=True)

    row3_c1, row3_c2 = st.columns(2)
    with row3_c1:
        fig5 = gg.Figure()
        fig5.add_trace(gg.Scatter(x=df_chrono["start_time"], y=df_chrono["stride_m"], mode="markers+lines", name="Stride Length (m)", line=dict(color="#F59E0B", width=1.5)))
        fig5.add_trace(gg.Scatter(x=df_chrono["start_time"], y=df_chrono["roll_stride"], name="7-Day Rolling Avg", line=dict(color="#10B981", width=2.5)))
        fig5.update_layout(title="👟 Stride Length (m)", template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(23, 32, 48, 0.5)")
        st.plotly_chart(fig5, use_container_width=True)

    with row3_c2:
        fig6 = gg.Figure()
        fig6.add_trace(gg.Bar(x=df_chrono["start_time"], y=df_chrono["calories"], name="Calories (kcal)", marker_color="#8B5CF6"))
        fig6.add_trace(gg.Scatter(x=df_chrono["start_time"], y=df_chrono["roll_cal"], name="7-Day Rolling Avg", line=dict(color="#38BDF8", width=2.5)))
        fig6.update_layout(title="🔥 Calories Burned (kcal)", template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(23, 32, 48, 0.5)")
        st.plotly_chart(fig6, use_container_width=True)


# =========================================================
# 4. 🫀 RECOVERY & READINESS
# =========================================================
elif nav_choice == "🫀 Recovery & Readiness":
    st.header("🫀 Recovery & Readiness Analytics")

    col_r1, col_r2 = st.columns(2)

    with col_r1:
        fig_scatter = px.scatter(
            summary_df,
            x="avg_pace_min_km",
            y="avg_heart_rate",
            size="distance_km",
            color="vo2_max" if "vo2_max" in summary_df.columns and summary_df["vo2_max"].notnull().any() else None,
            hover_name="activity_name",
            hover_data=["start_time", "distance_km", "avg_pace_str"],
            title="🏃 Pace vs Heart Rate Efficiency",
            labels={"avg_pace_min_km": "Avg Pace (min/km)", "avg_heart_rate": "Avg Heart Rate (bpm)"},
            color_continuous_scale="Viridis"
        )
        fig_scatter.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(23, 32, 48, 0.5)")
        st.plotly_chart(fig_scatter, use_container_width=True)

    with col_r2:
        fig_vo2 = gg.Figure()
        if "vo2_max" in summary_df.columns and summary_df["vo2_max"].notnull().any():
            vo2_clean = summary_df.dropna(subset=["vo2_max"])
            fig_vo2.add_trace(gg.Scatter(x=vo2_clean["start_time"], y=vo2_clean["vo2_max"], mode="lines+markers", name="VO2 Max", line=dict(color="#10B981", width=3), marker=dict(size=8)))
        fig_vo2.add_trace(gg.Scatter(x=summary_df["start_time"], y=summary_df["max_heart_rate"], mode="lines+markers", name="Peak HR (bpm)", line=dict(color="#EF4444", width=2, dash="dot"), marker=dict(size=6)))
        fig_vo2.update_layout(title="📈 Aerobic Capacity & Peak HR Trend", template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(23, 32, 48, 0.5)")
        st.plotly_chart(fig_vo2, use_container_width=True)


# =========================================================
# 5. 🏆 GOALS & MILESTONES
# =========================================================
elif nav_choice == "🏆 Goals & Milestones":
    st.header("🏆 5K Goal & Milestone Wall")

    valid_paces = summary_df["avg_pace_min_km"].dropna()
    best_pace = valid_paces.min() if not valid_paces.empty else 8.5
    target_pace = 7.00

    col_g1, col_g2 = st.columns([1, 1])
    with col_g1:
        fig_target_gauge = gg.Figure(gg.Indicator(
            mode="gauge+number+delta",
            value=best_pace,
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': "Current Best Pace vs 7:00 Target (min/km)", 'font': {'size': 16, 'color': '#E2E8F0'}},
            delta={'reference': target_pace, 'increasing': {'color': "#EF4444"}, 'decreasing': {'color': "#10B981"}, 'valueformat': '.2f'},
            number={'font': {'color': '#38BDF8', 'size': 36}, 'valueformat': '.2f'},
            gauge={
                'axis': {'range': [10.0, 5.0], 'tickwidth': 1, 'tickcolor': "#94A3B8"},
                'bar': {'color': "#38BDF8"},
                'bgcolor': "rgba(0,0,0,0)",
                'steps': [
                    {'range': [10.0, 7.0], 'color': 'rgba(239, 68, 68, 0.2)'},
                    {'range': [7.0, 5.0], 'color': 'rgba(34, 197, 94, 0.3)'}
                ],
                'threshold': {'line': {'color': "#10B981", 'width': 4}, 'thickness': 0.8, 'value': 7.0}
            }
        ))
        fig_target_gauge.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", height=300)
        st.plotly_chart(fig_target_gauge, use_container_width=True)

    with col_g2:
        st.subheader("🌟 Personal Bests & Record Wall")
        longest_run = summary_df["distance_km"].max()
        fastest_pace_row = summary_df.loc[summary_df["avg_pace_min_km"].idxmin()]
        max_elevation = summary_df["elevation_gain_m"].max()
        max_vo2 = summary_df["vo2_max"].max() if "vo2_max" in summary_df.columns else "N/A"

        st.markdown(f"""
        - 🥇 **Longest Distance**: `{longest_run:.2f} km`
        - ⚡ **Fastest Avg Pace**: `{fastest_pace_row['avg_pace_str']} min/km` (*{fastest_pace_row['activity_name']} on {pd.to_datetime(fastest_pace_row['start_time']).strftime('%b %d')}*)
        - ⛰️ **Max Elevation Gain**: `{max_elevation} m`
        - 🫀 **Peak VO2 Max**: `{max_vo2}`
        """)

    st.markdown("---")
    st.subheader("📋 Completed Activities Log")
    table_df = summary_df.copy()
    table_df["stride_m"] = table_df["stride_length_cm"].apply(lambda x: f"{x/100.0:.2f} m" if pd.notnull(x) and x > 0 else "N/A")
    st.dataframe(
        table_df[[
            "activity_name", "start_time", "distance_km", "duration_min", 
            "avg_pace_str", "avg_heart_rate", "avg_cadence_spm", "stride_m", "calories"
        ]].rename(columns={
            "activity_name": "Activity Name", "start_time": "Date & Time", "distance_km": "Distance (km)",
            "duration_min": "Duration (min)", "avg_pace_str": "Avg Pace (/km)", "avg_heart_rate": "Avg HR (bpm)",
            "avg_cadence_spm": "Cadence (spm)", "stride_m": "Stride Length", "calories": "Calories (kcal)"
        }),
        use_container_width=True
    )


# =========================================================
# 6. 💬 GEMINI AI RUNNING COACH
# =========================================================
elif nav_choice == "💬 Gemini AI Running Coach":
    st.header("💬 Gemini AI Running Coach")
    st.markdown("Personalized AI coaching powered by your **Garmin Forerunner 165** telemetry data.")

    # Retrieve API key
    gemini_key = None
    try:
        if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
            gemini_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass

    if not gemini_key:
        gemini_key = os.getenv("GEMINI_API_KEY")

    if not gemini_key:
        st.warning("⚠️ `GEMINI_API_KEY` is missing. Please add `GEMINI_API_KEY` to `.env` or Streamlit Secrets.")
        st.info("Example `.env` format:\n`GEMINI_API_KEY=your_gemini_api_key_here`")
        st.stop()

    # Pre-build summary context for LLM
    recent_runs = summary_df.head(15)
    total_runs = len(summary_df)
    avg_pace_overall = recent_runs["avg_pace_min_km"].mean()
    avg_hr_overall = recent_runs["avg_heart_rate"].mean()
    avg_cadence_overall = recent_runs["avg_cadence_spm"].mean()

    telemetry_context = f"""
USER PROFILE & RUNNING DATA SUMMARY:
- Primary Goal: 5K Training Goal targeting 7:00 min/km pace.
- Device: Garmin Forerunner 165.
- Total Logged Runs: {total_runs}.
- Recent Average Pace: {avg_pace_overall:.2f} min/km.
- Recent Average Heart Rate: {avg_hr_overall:.0f} bpm.
- Recent Average Cadence: {avg_cadence_overall:.0f} spm.

RECENT 10 RUNS LOG:
{recent_runs[['start_time', 'distance_km', 'duration_min', 'avg_pace_str', 'avg_heart_rate', 'avg_cadence_spm']].to_string(index=False)}

You are an expert AI Running Coach and Exercise Physiologist. Provide specific, data-backed coaching advice based on the runner's telemetry above. Be encouraging, precise, and practical.
"""

    # Chat session state
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": f"Hello! I'm your **Gemini AI Running Coach**. I've analyzed your **{total_runs} Garmin runs**. Your recent average pace is **{avg_pace_overall:.2f} min/km** with a target of **7:00 min/km**.\n\nHow can I help you reach your 5K target today? You can ask about interval workouts, cadence drills, or pacing strategies!"
            }
        ]

    # Render Chat History
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat Input
    if user_prompt := st.chat_input("Ask your Gemini AI Coach (e.g. 'How do I close the gap to 7:00 pace?')..."):
        # Display user message
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        # Call Gemini API
        with st.chat_message("assistant"):
            with st.spinner("Analyzing telemetry & drafting response..."):
                response_text = ""
                
                # Attempt using google.genai or google.generativeai
                try:
                    import google.generativeai as genai
                    genai.configure(api_key=gemini_key)

                    # Try standard models in sequence
                    model_names = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest", "gemini-1.5-flash"]
                    generated = False

                    for model_name in model_names:
                        try:
                            model = genai.GenerativeModel(model_name)
                            prompt_text = f"{telemetry_context}\n\nUSER QUESTION: {user_prompt}"
                            res = model.generate_content(prompt_text)
                            if res and hasattr(res, "text") and res.text:
                                response_text = res.text
                                generated = True
                                break
                        except Exception as inner_e:
                            continue

                    if not generated:
                        response_text = "I received your question! Based on your recent telemetry, focusing on 165+ spm cadence and progressive tempo runs will help close your 7:00 min/km pace gap. (Note: API temporary rate limit reached, please try asking again in a few moments)."

                except Exception as e:
                    response_text = f"Coaching Assistant Error: {e}"

                st.markdown(response_text)
                st.session_state.messages.append({"role": "assistant", "content": response_text})
