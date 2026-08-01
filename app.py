import os
import subprocess
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as gg
from plotly.subplots import make_subplots
import streamlit as st

# ---------------------------------------------------------
# Page Configuration & Design Tokens
# ---------------------------------------------------------
st.set_page_config(
    page_title="Garmin 5K Running Dashboard",
    page_icon="🏃",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Dark Premium Glassmorphism Look
st.markdown("""
<style>
    /* Dark theme background */
    .stApp {
        background-color: #0B0E14;
        color: #E2E8F0;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* Card Containers */
    .metric-card {
        background: rgba(23, 32, 48, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
        padding: 18px;
        box-shadow: 0 8px 16px rgba(0, 0, 0, 0.25);
        backdrop-filter: blur(10px);
    }
    
    .metric-label {
        font-size: 0.85rem;
        color: #94A3B8;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 4px;
    }
    
    .metric-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #38BDF8;
    }
    
    .metric-sub {
        font-size: 0.8rem;
        color: #64748B;
        margin-top: 4px;
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
        background-color: transparent;
    }
    
    .stTabs [aria-selected="true"] {
        color: #38BDF8 !important;
        border-bottom: 2px solid #38BDF8 !important;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# Data Loading & Refresh Logic
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def load_data():
    summary_file = "data/runs_summary.csv"
    trackpoints_file = "data/raw_trackpoints.csv"

    if not os.path.exists(summary_file) or not os.path.exists(trackpoints_file):
        return None, None

    summary_df = pd.read_csv(summary_file)
    trackpoints_df = pd.read_csv(trackpoints_file)

    # Convert timestamps
    summary_df["start_time"] = pd.to_datetime(summary_df["start_time"])
    trackpoints_df["timestamp"] = pd.to_datetime(trackpoints_df["timestamp"])
    trackpoints_df["start_time"] = pd.to_datetime(trackpoints_df["start_time"])

    # Ensure activity_id is string/int consistent
    summary_df["activity_id"] = summary_df["activity_id"].astype(str)
    trackpoints_df["activity_id"] = trackpoints_df["activity_id"].astype(str)

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
        result = subprocess.run(["./venv/bin/python", "data_loader.py"], capture_output=True, text=True)
        if result.returncode == 0:
            st.sidebar.success("Data refreshed successfully!")
            st.cache_data.clear()
            st.rerun()
        else:
            st.sidebar.error(f"Refresh failed: {result.stderr}")

summary_df, trackpoints_df = load_data()

if summary_df is None or trackpoints_df is None:
    st.error("Data files missing. Please run `data_loader.py` to extract Garmin running data.")
    st.stop()

# Filter for runs only
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

    # Get selected summary row & trackpoints
    run_sum = summary_df[summary_df["activity_id"] == selected_act_id].iloc[0]
    run_tp = trackpoints_df[trackpoints_df["activity_id"] == selected_act_id].copy()

    if not run_tp.empty:
        run_tp["distance_km"] = run_tp["distance_m"] / 1000.0
        # Filter out extreme pace outliers for clear visual analysis (pace between 3:00 and 14:00 min/km)
        run_tp["clean_pace"] = run_tp["pace_min_km"].apply(lambda p: p if 3.0 <= p <= 14.0 else None)
    
    # KPI Row
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.markdown(f"""<div class="metric-card">
            <div class="metric-label">Distance</div>
            <div class="metric-value">{run_sum['distance_km']:.2f} <span style="font-size:1rem;">km</span></div>
        </div>""", unsafe_allow_html=True)
    with col2:
        st.markdown(f"""<div class="metric-card">
            <div class="metric-label">Duration</div>
            <div class="metric-value">{run_sum['duration_min']:.1f} <span style="font-size:1rem;">min</span></div>
        </div>""", unsafe_allow_html=True)
    with col3:
        pace_str = run_sum['avg_pace_str'] if pd.notnull(run_sum['avg_pace_str']) else "N/A"
        st.markdown(f"""<div class="metric-card">
            <div class="metric-label">Avg Pace</div>
            <div class="metric-value">{pace_str} <span style="font-size:1rem;">/km</span></div>
        </div>""", unsafe_allow_html=True)
    with col4:
        hr_val = f"{int(run_sum['avg_heart_rate'])}" if pd.notnull(run_sum['avg_heart_rate']) else "N/A"
        st.markdown(f"""<div class="metric-card">
            <div class="metric-label">Avg Heart Rate</div>
            <div class="metric-value">{hr_val} <span style="font-size:1rem;">bpm</span></div>
        </div>""", unsafe_allow_html=True)
    with col5:
        cad_val = f"{int(run_sum['avg_cadence_spm'])}" if pd.notnull(run_sum['avg_cadence_spm']) else "N/A"
        st.markdown(f"""<div class="metric-card">
            <div class="metric-label">Avg Cadence</div>
            <div class="metric-value">{cad_val} <span style="font-size:1rem;">spm</span></div>
        </div>""", unsafe_allow_html=True)
    with col6:
        stride_val = f"{run_sum['stride_length_cm']/100.0:.2f}" if pd.notnull(run_sum['stride_length_cm']) and run_sum['stride_length_cm'] > 0 else "N/A"
        st.markdown(f"""<div class="metric-card">
            <div class="metric-label">Stride Length</div>
            <div class="metric-value">{stride_val} <span style="font-size:1rem;">m</span></div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    if not run_tp.empty:
        # Chart 1: Instantaneous Pace Profile with 7:00 target line
        fig_pace = px.line(
            run_tp,
            x="distance_km",
            y="clean_pace",
            title="⚡ Instantaneous Pace Profile (Target: 7:00 min/km)",
            labels={"distance_km": "Distance (km)", "clean_pace": "Pace (min/km)"},
            color_discrete_sequence=["#38BDF8"]
        )
        fig_pace.add_hline(
            y=7.0,
            line_dash="dash",
            line_color="#EF4444",
            annotation_text="🎯 Target Pace (7:00 min/km)",
            annotation_position="bottom right",
            annotation_font_color="#EF4444"
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
                    line=dict(color="#94A3B8", width=1.5)
                ),
                secondary_y=False
            )
            
            fig_hr_ele.add_trace(
                gg.Scatter(
                    x=run_tp["distance_km"],
                    y=run_tp["heart_rate_bpm"],
                    name="Heart Rate (bpm)",
                    line=dict(color="#F43F5E", width=2)
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
                    line=dict(color="#10B981", width=2)
                ),
                secondary_y=False
            )

            fig_bio.add_trace(
                gg.Scatter(
                    x=run_tp["distance_km"],
                    y=run_tp["stride_length_m"],
                    name="Stride Length (m)",
                    line=dict(color="#F59E0B", width=2)
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
            marker_color="#38BDF8"
        ))
        fig_vol.add_trace(gg.Scatter(
            x=weekly_df["week"],
            y=weekly_df["volume_ceiling"],
            name="10% Progression Ceiling",
            line=dict(color="#F59E0B", width=2, dash="dash")
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
        # Acute: Last 7 days total distance
        # Chronic: Average weekly distance over last 28 days
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
                marker=dict(size=8)
            ))
        
        fig_vo2.add_trace(gg.Scatter(
            x=summary_df["start_time"],
            y=summary_df["max_heart_rate"],
            mode="lines+markers",
            name="Peak HR (bpm)",
            line=dict(color="#EF4444", width=2, dash="dot"),
            marker=dict(size=6)
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
    st.dataframe(
        summary_df[[
            "activity_name", "start_time", "distance_km", "duration_min", 
            "avg_pace_str", "avg_heart_rate", "avg_cadence_spm", "calories"
        ]].rename(columns={
            "activity_name": "Activity Name",
            "start_time": "Date & Time",
            "distance_km": "Distance (km)",
            "duration_min": "Duration (min)",
            "avg_pace_str": "Avg Pace (/km)",
            "avg_heart_rate": "Avg HR (bpm)",
            "avg_cadence_spm": "Cadence (spm)",
            "calories": "Calories (kcal)"
        }),
        use_container_width=True
    )
