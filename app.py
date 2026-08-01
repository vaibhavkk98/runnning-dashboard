import os
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as gg
from plotly.subplots import make_subplots
import streamlit as st
from data_loader import fetch_garmin_data

# ---------------------------------------------------------
# Page Configuration & Design Tokens
# ---------------------------------------------------------
st.set_page_config(
    page_title="Garmin 5K Running Dashboard",
    page_icon="🏃",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Premium Dark Glassmorphism Theme
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
    
    /* Tab Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 12px;
        border-bottom: 1px solid #1E293B;
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 48px;
        border-radius: 8px 8px 0px 0px;
        color: #94A3B8;
        font-weight: 600;
    }
    
    .stTabs [aria-selected="true"] {
        color: #38BDF8 !important;
        border-bottom: 2px solid #38BDF8 !important;
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

    # Fill derived stride length in summary if missing: Speed (m/s) / (Cadence / 60) * 100
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
# Sidebar
# ---------------------------------------------------------
st.sidebar.image("https://img.icons8.com/color/96/running.png", width=60)
st.sidebar.title("Garmin 5K Dashboard")
st.sidebar.caption("Target Pace: **7:00 min/km** | Device: **Forerunner 165**")

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

# ---------------------------------------------------------
# Main Header
# ---------------------------------------------------------
st.title("🏃 5K Running Performance & Training Dashboard")
st.markdown("Real-time telemetry and biometrics from **Garmin Forerunner 165**")

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Single Run Deep-Dive",
    "📈 Training Trends & Workload",
    "🫀 Recovery & Readiness",
    "🏆 5K Goal & Milestones"
])

# =========================================================
# TAB 1: SINGLE RUN DEEP-DIVE (MICRO VIEW)
# =========================================================
with tab1:
    st.header("🔍 Activity Telemetry & Biometrics")

    # Dropdown selector
    run_options = {
        f"{row['start_time'].strftime('%b %d, %Y %H:%M')} - {row['activity_name']} ({row['distance_km']} km)": row["activity_id"]
        for _, row in summary_df.iterrows()
    }
    
    selected_label = st.selectbox("Select Activity:", list(run_options.keys()))
    selected_act_id = run_options[selected_label]

    selected_index = summary_df[summary_df["activity_id"] == selected_act_id].index[0]
    run_sum = summary_df.iloc[selected_index]
    
    # Previous run comparison (if available)
    prev_run = summary_df.iloc[selected_index + 1] if selected_index + 1 < len(summary_df) else None

    run_tp = trackpoints_df[trackpoints_df["activity_id"] == selected_act_id].copy()

    if not run_tp.empty:
        run_tp["distance_km"] = run_tp["distance_m"] / 1000.0
        run_tp["clean_pace"] = run_tp["pace_min_km"].apply(lambda p: p if 3.0 <= p <= 14.0 else None)
        
        # Derive stride length if missing in trackpoints
        for t_idx, t_row in run_tp.iterrows():
            if (pd.isnull(t_row.get("stride_length_m")) or t_row.get("stride_length_m") == 0) and t_row.get("speed_mps") and t_row.get("cadence_spm"):
                sp_mps = t_row["speed_mps"]
                cad_spm = t_row["cadence_spm"]
                if sp_mps > 0 and cad_spm > 0:
                    run_tp.at[t_idx, "stride_length_m"] = round(sp_mps / (cad_spm / 60.0), 2)

    # ---------------------------------------------------------
    # INSIGHTS & COACHING ENGINE (Automated Run Debrief)
    # ---------------------------------------------------------
    avg_pace_dec = run_sum["avg_pace_min_km"] if pd.notnull(run_sum["avg_pace_min_km"]) else 8.5
    target_pace_dec = 7.00
    pace_gap_sec = int(round((avg_pace_dec - target_pace_dec) * 60))

    avg_cadence = run_sum["avg_cadence_spm"] if pd.notnull(run_sum["avg_cadence_spm"]) else 0.0

    # Cardiac Drift calculation (First 25% HR vs Last 25% HR)
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
        # A. Target Pace Gap
        if pace_gap_sec > 0:
            st.markdown(f"""
            <div style="margin-bottom: 12px;">
                <span class="insight-badge badge-amber">⏱️ Target Pace Gap</span><br>
                Average pace <b>{run_sum['avg_pace_str']} min/km</b> is <b>{pace_gap_sec} seconds/km slower</b> than target 7:00 min/km benchmark.
            </div>
            """, unsafe_allow_html=True)
        elif pace_gap_sec == 0:
            st.markdown(f"""
            <div style="margin-bottom: 12px;">
                <span class="insight-badge badge-green">🎯 On Target</span><br>
                Hit exact target benchmark pace of <b>7:00 min/km</b>!
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="margin-bottom: 12px;">
                <span class="insight-badge badge-green">🚀 Above Benchmark</span><br>
                Average pace <b>{run_sum['avg_pace_str']} min/km</b> is <b>{abs(pace_gap_sec)} seconds/km faster</b> than target!
            </div>
            """, unsafe_allow_html=True)

        # B. Cadence & Form Assessment
        if avg_cadence < 155:
            st.markdown(f"""
            <div style="margin-bottom: 12px;">
                <span class="insight-badge badge-amber">⚠️ Cadence Warning ({avg_cadence:.0f} spm)</span><br>
                Cadence is below the recommended 160–170 spm threshold. Low step frequency increases ground contact time and joint impact.
            </div>
            """, unsafe_allow_html=True)
        elif avg_cadence < 170:
            st.markdown(f"""
            <div style="margin-bottom: 12px;">
                <span class="insight-badge badge-green">👍 Good Cadence ({avg_cadence:.0f} spm)</span><br>
                Solid step rate. Increasing to 165–175 spm will further improve efficiency and shorten ground contact.
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="margin-bottom: 12px;">
                <span class="insight-badge badge-green">🔥 Optimal Cadence ({avg_cadence:.0f} spm)</span><br>
                Excellent step rate! High turnover minimizes impact stress and promotes forward propulsion.
            </div>
            """, unsafe_allow_html=True)

    with ins_col2:
        # C. Cardiac Drift Detector
        if cardiac_drift_pct > 5.0:
            st.markdown(f"""
            <div style="margin-bottom: 12px;">
                <span class="insight-badge badge-red">🌡️ Cardiac Drift Detected (+{cardiac_drift_pct:.1f}%)</span><br>
                Heart rate rose from <b>{first_q_hr:.0f} bpm</b> (first 25%) to <b>{last_q_hr:.0f} bpm</b> (final 25%). Indicates aerobic fatigue, heat buildup, or dehydration.
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="margin-bottom: 12px;">
                <span class="insight-badge badge-green">💚 Controlled HR (+{cardiac_drift_pct:.1f}% Drift)</span><br>
                Heart rate remained steady from start (<b>{first_q_hr:.0f} bpm</b>) to finish (<b>{last_q_hr:.0f} bpm</b>). Excellent aerobic stability!
            </div>
            """, unsafe_allow_html=True)

        # D. Tailored Action Items
        st.markdown(f"""
        <div>
            <b>📋 Next Run Action Items:</b>
            <ul style="margin-top: 4px; padding-left: 20px; font-size: 0.9rem; color: #CBD5E1;">
                <li><b>Pacing:</b> Aim for progressive split—start 15s slower for km 1, then settle into target pace.</li>
                <li><b>Cadence Drill:</b> Focus on quick, light foot strikes to bring cadence toward 165+ spm.</li>
                <li><b>Recovery:</b> {"Prioritize pre-run hydration & Zone 2 aerobic base." if cardiac_drift_pct > 5.0 else "Maintain current recovery & hydration strategy."}</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # ---------------------------------------------------------
    # KPI CARDS WITH DELTAS
    # ---------------------------------------------------------
    col1, col2, col3, col4, col5, col6 = st.columns(6)

    def format_delta(curr, prev, fmt="{:.2f}", unit="", inverse=False):
        if prev is None or pd.isnull(prev):
            return None
        diff = curr - prev
        prefix = "+" if diff > 0 else ""
        return f"{prefix}{fmt.format(diff)} {unit}".strip()

    with col1:
        dist_delta = format_delta(run_sum['distance_km'], prev_run['distance_km'] if prev_run is not None else None, "{:.2f}", "km")
        st.metric("Distance", f"{run_sum['distance_km']:.2f} km", delta=dist_delta)

    with col2:
        dur_delta = format_delta(run_sum['duration_min'], prev_run['duration_min'] if prev_run is not None else None, "{:.1f}", "min")
        st.metric("Duration", f"{run_sum['duration_min']:.1f} min", delta=dur_delta)

    with col3:
        pace_str = run_sum['avg_pace_str'] if pd.notnull(run_sum['avg_pace_str']) else "N/A"
        pace_delta = format_delta(run_sum['avg_pace_min_km'], prev_run['avg_pace_min_km'] if prev_run is not None else None, "{:.2f}", "m/km")
        st.metric("Avg Pace", f"{pace_str} /km", delta=pace_delta, delta_color="inverse")

    with col4:
        hr_val = f"{int(run_sum['avg_heart_rate'])}" if pd.notnull(run_sum['avg_heart_rate']) else "N/A"
        hr_delta = format_delta(run_sum['avg_heart_rate'], prev_run['avg_heart_rate'] if prev_run is not None else None, "{:.0f}", "bpm")
        st.metric("Avg Heart Rate", f"{hr_val} bpm", delta=hr_delta, delta_color="inverse")

    with col5:
        cad_val = f"{int(run_sum['avg_cadence_spm'])}" if pd.notnull(run_sum['avg_cadence_spm']) else "N/A"
        cad_delta = format_delta(run_sum['avg_cadence_spm'], prev_run['avg_cadence_spm'] if prev_run is not None else None, "{:.0f}", "spm")
        st.metric("Avg Cadence", f"{cad_val} spm", delta=cad_delta)

    with col6:
        stride_m_val = (run_sum['stride_length_cm'] / 100.0) if pd.notnull(run_sum['stride_length_cm']) and run_sum['stride_length_cm'] > 0 else 0.0
        prev_stride_m = (prev_run['stride_length_cm'] / 100.0) if prev_run is not None and pd.notnull(prev_run.get('stride_length_cm')) else None
        stride_delta = format_delta(stride_m_val, prev_stride_m, "{:.2f}", "m")
        st.metric("Stride Length", f"{stride_m_val:.2f} m", delta=stride_delta)

    st.markdown("<br>", unsafe_allow_html=True)

    if not run_tp.empty:
        # Chart 1: Instantaneous Pace Profile with 7:00 target line & target band
        fig_pace = px.line(
            run_tp,
            x="distance_km",
            y="clean_pace",
            title="⚡ Instantaneous Pace Profile (Target: 7:00 min/km)",
            labels={"distance_km": "Distance (km)", "clean_pace": "Pace (min/km)"},
            color_discrete_sequence=["#38BDF8"]
        )
        
        # Target Pace Band (6:45 to 7:15 min/km)
        fig_pace.add_hrect(
            y0=6.75, y1=7.25,
            fillcolor="rgba(16, 185, 129, 0.15)",
            line_width=0,
            annotation_text="🎯 Target Zone (6:45 - 7:15)",
            annotation_position="top left",
            annotation_font_color="#10B981"
        )

        fig_pace.add_hline(
            y=7.0,
            line_dash="dash",
            line_color="#EF4444",
            annotation_text="🎯 7:00 Target Benchmark",
            annotation_position="bottom right",
            annotation_font_color="#EF4444"
        )

        fig_pace.update_traces(
            hovertemplate="<b>Distance:</b> %{x:.2f} km<br><b>Pace:</b> %{y:.2f} min/km<extra></extra>"
        )

        fig_pace.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(23, 32, 48, 0.5)",
            yaxis=dict(autorange="reversed", title="Pace (min/km) [Faster Up]"),
            margin=dict(l=40, r=40, t=50, b=40)
        )
        st.plotly_chart(fig_pace, use_container_width=True)

        col_left, col_right = st.columns(2)

        with col_left:
            # Chart 2: Dual Axis HR & Elevation
            fig_hr_ele = make_subplots(specs=[[{"secondary_y": True}]])
            
            fig_hr_ele.add_trace(
                gg.Scatter(
                    x=run_tp["distance_km"],
                    y=run_tp["elevation_m"],
                    name="Elevation (m)",
                    fill="tozeroy",
                    fillcolor="rgba(100, 116, 139, 0.2)",
                    line=dict(color="#94A3B8", width=1.5),
                    hovertemplate="<b>Dist:</b> %{x:.2f} km<br><b>Elevation:</b> %{y:.1f} m<extra></extra>"
                ),
                secondary_y=False
            )
            
            fig_hr_ele.add_trace(
                gg.Scatter(
                    x=run_tp["distance_km"],
                    y=run_tp["heart_rate_bpm"],
                    name="Heart Rate (bpm)",
                    line=dict(color="#F43F5E", width=2),
                    hovertemplate="<b>Dist:</b> %{x:.2f} km<br><b>Heart Rate:</b> %{y:.0f} bpm<extra></extra>"
                ),
                secondary_y=True
            )

            fig_hr_ele.update_layout(
                title="❤️ Heart Rate & Elevation Profile",
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(23, 32, 48, 0.5)",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            fig_hr_ele.update_xaxes(title_text="Distance (km)")
            fig_hr_ele.update_yaxes(title_text="Elevation (m)", secondary_y=False)
            fig_hr_ele.update_yaxes(title_text="Heart Rate (bpm)", secondary_y=True)

            st.plotly_chart(fig_hr_ele, use_container_width=True)

        with col_right:
            # Chart 3: Biomechanics (Cadence & Stride Length)
            fig_bio = make_subplots(specs=[[{"secondary_y": True}]])
            
            fig_bio.add_trace(
                gg.Scatter(
                    x=run_tp["distance_km"],
                    y=run_tp["cadence_spm"],
                    name="Cadence (spm)",
                    line=dict(color="#10B981", width=2),
                    hovertemplate="<b>Dist:</b> %{x:.2f} km<br><b>Cadence:</b> %{y:.0f} spm<extra></extra>"
                ),
                secondary_y=False
            )

            fig_bio.add_trace(
                gg.Scatter(
                    x=run_tp["distance_km"],
                    y=run_tp["stride_length_m"],
                    name="Stride Length (m)",
                    line=dict(color="#F59E0B", width=2),
                    hovertemplate="<b>Dist:</b> %{x:.2f} km<br><b>Stride:</b> %{y:.2f} m<extra></extra>"
                ),
                secondary_y=True
            )

            fig_bio.update_layout(
                title="⚙️ Biomechanics (Cadence & Stride Length)",
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(23, 32, 48, 0.5)",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            fig_bio.update_xaxes(title_text="Distance (km)")
            fig_bio.update_yaxes(title_text="Cadence (spm)", secondary_y=False)
            fig_bio.update_yaxes(title_text="Stride Length (m)", secondary_y=True)

            st.plotly_chart(fig_bio, use_container_width=True)

# =========================================================
# TAB 2: TRAINING TRENDS & WORKLOAD (MACRO VIEW)
# =========================================================
with tab2:
    st.header("📈 Training Load & Progress Tracking")

    # Aggregate weekly volume
    df_trend = summary_df.copy()
    df_trend["week"] = df_trend["start_time"].dt.to_period("W").dt.start_time
    weekly_df = df_trend.groupby("week")["distance_km"].sum().reset_index()
    weekly_df = weekly_df.sort_values("week")

    # 10% Guidance Line
    weekly_df["volume_ceiling"] = weekly_df["distance_km"].shift(1) * 1.10

    col_w1, col_w2 = st.columns([2, 1])

    with col_w1:
        fig_vol = gg.Figure()
        fig_vol.add_trace(gg.Bar(
            x=weekly_df["week"],
            y=weekly_df["distance_km"],
            name="Weekly Distance (km)",
            marker_color="#38BDF8",
            hovertemplate="<b>Week Starting:</b> %{x|%b %d}<br><b>Distance:</b> %{y:.2f} km<extra></extra>"
        ))
        fig_vol.add_trace(gg.Scatter(
            x=weekly_df["week"],
            y=weekly_df["volume_ceiling"],
            name="10% Progression Ceiling",
            line=dict(color="#F59E0B", width=2, dash="dash"),
            hovertemplate="<b>10% Ceiling:</b> %{y:.2f} km<extra></extra>"
        ))
        fig_vol.update_layout(
            title="📅 Weekly Training Volume (km) vs 10% Rule",
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(23, 32, 48, 0.5)",
            xaxis_title="Week Starting",
            yaxis_title="Total Distance (km)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_vol, use_container_width=True)

    with col_w2:
        # Acute-to-Chronic Workload Ratio (ACWR) Calculation
        max_date = summary_df["start_time"].max()
        last_7_days = summary_df[summary_df["start_time"] >= (max_date - pd.Timedelta(days=7))]
        last_28_days = summary_df[summary_df["start_time"] >= (max_date - pd.Timedelta(days=28))]

        acute_load = last_7_days["distance_km"].sum()
        chronic_load = (last_28_days["distance_km"].sum() / 4.0) if not last_28_days.empty else 1.0

        acwr = acute_load / chronic_load if chronic_load > 0 else 0.0

        # Gauge Chart
        fig_gauge = gg.Figure(gg.Indicator(
            mode="gauge+number",
            value=acwr,
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': "Acute-to-Chronic Ratio (ACWR)", 'font': {'size': 16, 'color': '#E2E8F0'}},
            number={'font': {'color': '#38BDF8', 'size': 32}, 'valueformat': '.2f'},
            gauge={
                'axis': {'range': [0, 2.0], 'tickwidth': 1, 'tickcolor': "#94A3B8"},
                'bar': {'color': "#38BDF8"},
                'bgcolor': "rgba(0,0,0,0)",
                'borderwidth': 2,
                'bordercolor': "#334155",
                'steps': [
                    {'range': [0, 0.8], 'color': 'rgba(234, 179, 8, 0.3)'},   # Under-training
                    {'range': [0.8, 1.3], 'color': 'rgba(34, 197, 94, 0.4)'},  # Sweet spot
                    {'range': [1.3, 1.5], 'color': 'rgba(234, 179, 8, 0.3)'},  # Overreaching
                    {'range': [1.5, 2.0], 'color': 'rgba(239, 68, 68, 0.4)'}   # High Risk
                ],
                'threshold': {
                    'line': {'color': "#EF4444", 'width': 4},
                    'thickness': 0.75,
                    'value': 1.5
                }
            }
        ))
        fig_gauge.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            height=300,
            margin=dict(l=20, r=20, t=50, b=20)
        )
        st.plotly_chart(fig_gauge, use_container_width=True)

        if acwr >= 0.8 and acwr <= 1.3:
            st.success("✅ **Optimal Workload**: Safe progression zone (0.8 - 1.3).")
        elif acwr > 1.3 and acwr <= 1.5:
            st.warning("⚠️ **Caution**: Increasing workload rapidly.")
        elif acwr > 1.5:
            st.error("🚨 **High Injury Risk**: ACWR > 1.5. Consider a recovery week.")
        else:
            st.info("ℹ️ **Building Base**: Under-training / fresh state.")

# =========================================================
# TAB 3: RECOVERY & READINESS
# =========================================================
with tab3:
    st.header("🫀 Physiological Efficiency & Fitness Adaptation")

    col_r1, col_r2 = st.columns(2)

    with col_r1:
        # Scatterplot: HR vs Pace
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
        fig_scatter.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(23, 32, 48, 0.5)"
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

    with col_r2:
        # VO2 Max & Max HR trend over runs
        fig_vo2 = gg.Figure()
        
        if "vo2_max" in summary_df.columns and summary_df["vo2_max"].notnull().any():
            vo2_clean = summary_df.dropna(subset=["vo2_max"])
            fig_vo2.add_trace(gg.Scatter(
                x=vo2_clean["start_time"],
                y=vo2_clean["vo2_max"],
                mode="lines+markers",
                name="VO2 Max",
                line=dict(color="#10B981", width=3),
                marker=dict(size=8),
                hovertemplate="<b>Date:</b> %{x|%b %d}<br><b>VO2 Max:</b> %{y:.0f}<extra></extra>"
            ))
        
        fig_vo2.add_trace(gg.Scatter(
            x=summary_df["start_time"],
            y=summary_df["max_heart_rate"],
            mode="lines+markers",
            name="Peak HR (bpm)",
            line=dict(color="#EF4444", width=2, dash="dot"),
            marker=dict(size=6),
            hovertemplate="<b>Date:</b> %{x|%b %d}<br><b>Peak HR:</b> %{y:.0f} bpm<extra></extra>"
        ))

        fig_vo2.update_layout(
            title="📈 Aerobic Capacity & Peak Heart Rate Trend",
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(23, 32, 48, 0.5)",
            xaxis_title="Date",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_vo2, use_container_width=True)

# =========================================================
# TAB 4: 5K GOAL & MILESTONE WALL
# =========================================================
with tab4:
    st.header("🏆 5K Training Goal: 7:00 min/km Target")

    # Current Best Pace calculation
    valid_paces = summary_df["avg_pace_min_km"].dropna()
    best_pace = valid_paces.min() if not valid_paces.empty else 8.5
    target_pace = 7.00

    col_g1, col_g2 = st.columns([1, 1])

    with col_g1:
        # Pace Gauge to 7:00 target
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
                'threshold': {
                    'line': {'color': "#10B981", 'width': 4},
                    'thickness': 0.8,
                    'value': 7.0
                }
            }
        ))
        fig_target_gauge.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            height=300
        )
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
    
    # Format stride length cleanly in table
    table_df = summary_df.copy()
    table_df["stride_m"] = table_df["stride_length_cm"].apply(lambda x: f"{x/100.0:.2f} m" if pd.notnull(x) and x > 0 else "N/A")

    st.dataframe(
        table_df[[
            "activity_name", "start_time", "distance_km", "duration_min", 
            "avg_pace_str", "avg_heart_rate", "avg_cadence_spm", "stride_m", "calories"
        ]].rename(columns={
            "activity_name": "Activity Name",
            "start_time": "Date & Time",
            "distance_km": "Distance (km)",
            "duration_min": "Duration (min)",
            "avg_pace_str": "Avg Pace (/km)",
            "avg_heart_rate": "Avg HR (bpm)",
            "avg_cadence_spm": "Cadence (spm)",
            "stride_m": "Stride Length",
            "calories": "Calories (kcal)"
        }),
        use_container_width=True
    )
