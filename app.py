import os
import json
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as gg
from plotly.subplots import make_subplots
import streamlit as st
from datetime import datetime, timedelta
import streamlit_shadcn_ui as ui
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

# Custom CSS for Sleek High-End Dark Theme & Segmented Top Nav
st.markdown("""
<style>
    .stApp {
        background-color: #0F172A;
        color: #F8FAFC;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* Executive Summary Container */
    .insights-card {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.8) 0%, rgba(15, 23, 42, 0.9) 100%);
        border: 1px solid rgba(59, 130, 246, 0.3);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 24px;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
        backdrop-filter: blur(12px);
    }
    
    .insights-header {
        font-size: 1.25rem;
        font-weight: 700;
        color: #3B82F6;
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

    /* Metric Containers */
    div[data-testid="stMetric"] {
        background: rgba(30, 41, 59, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 14px 18px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
    }

    /* Horizontal Radio Segmented Top Nav */
    div[data-testid="stRadio"] > div {
        flex-direction: row;
        justify-content: center;
        background-color: #0F172A;
        padding: 6px;
        border-radius: 14px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        gap: 8px;
        margin-bottom: 20px;
    }

    div[data-testid="stRadio"] label {
        background: rgba(30, 41, 59, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.05);
        padding: 10px 18px;
        border-radius: 10px;
        color: #94A3B8;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s ease-in-out;
    }

    div[data-testid="stRadio"] label:hover {
        background: rgba(59, 130, 246, 0.2);
        color: #F8FAFC;
    }

    div[data-testid="stRadio"] input:checked + div {
        color: #FFFFFF !important;
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


def sanitize_json_payload(obj):
    """Recursively strip non-informative administrative keys from Garmin JSON."""
    if isinstance(obj, dict):
        cleaned = {}
        for k, v in obj.items():
            if k in ["userProfileId", "activityUUID", "accessControlRuleDTO", "weatherStationDTO", "ownerId", "privacy"]:
                continue
            cleaned[k] = sanitize_json_payload(v)
        return cleaned
    elif isinstance(obj, list):
        return [sanitize_json_payload(x) for x in obj]
    else:
        return obj


# Fallback Analysis Generator if API is rate limited
def generate_fallback_race_analysis(run_summary_dict, splits_text, baseline_text):
    distance_km = run_summary_dict.get('distance_km', 0)
    avg_pace_str = run_summary_dict.get('avg_pace_str', 'N/A')
    run_pace_str = run_summary_dict.get('run_pace_str', avg_pace_str)
    run_pace_dec = run_summary_dict.get('run_pace_min_km') or run_summary_dict.get('avg_pace_min_km', 8.5)
    avg_hr = run_summary_dict.get('avg_heart_rate', 150)
    avg_cadence = run_summary_dict.get('avg_cadence_spm', 145)
    pace_gap_sec = int(round((run_pace_dec - 7.00) * 60))

    worked_well = [
        f"Active RUNNING pace reached **{run_pace_str} min/km** over **{run_summary_dict.get('run_distance_km', distance_km)} km**.",
        f"Completed session with average HR at **{avg_hr:.0f} bpm** across continuous movement."
    ]

    broke_down = [
        f"Active running pace (**{run_pace_str} min/km**) is **{pace_gap_sec} seconds/km away** from target 7:00 min/km benchmark." if pace_gap_sec > 0 else "Run pace met target benchmark!",
        f"Cadence (**{avg_cadence:.0f} spm**) can be increased toward 160+ spm for improved running economy."
    ]

    standout = f"The runner uses a Run/Walk strategy. Evaluating active RUNNING pace separately from walk recovery shows strong potential to reach 7:00 min/km by shortening walk recovery duration."

    return f"""
### 🟢 What Worked Well
- {worked_well[0]}
- {worked_well[1]}

### ⚠️ What Broke Down / Tactical Flaws
- {broke_down[0]}
- {broke_down[1]}

### 🎯 Standout Takeaway vs 7:00 Target Goal
- {standout}
"""


# ---------------------------------------------------------
# Streamlit Caching for Gemini AI Analysis with Full Raw JSON
# ---------------------------------------------------------
@st.cache_data(ttl=86400, show_spinner=False)
def analyze_run_with_gemini(activity_id: str, run_summary_dict: dict, splits_text: str, baseline_text: str, gemini_key: str):
    """Query Gemini AI with full raw Garmin activity JSON payload to generate deep sports-science race analysis."""
    if not gemini_key:
        return generate_fallback_race_analysis(run_summary_dict, splits_text, baseline_text)

    # Load Full Raw Activity JSON if available
    raw_json_str = ""
    raw_json_path = f"data/raw_activity_{activity_id}.json"
    if os.path.exists(raw_json_path):
        try:
            with open(raw_json_path, "r") as f:
                raw_payload = json.load(f)
            cleaned_payload = sanitize_json_payload(raw_payload)
            raw_json_str = json.dumps(cleaned_payload, indent=2, default=str)
        except Exception as e:
            raw_json_str = f"Raw JSON load error: {e}"

    if not raw_json_str:
        raw_json_str = json.dumps(run_summary_dict, indent=2, default=str)

    prompt = f"""YOU ARE AN ELITE SPORTS SCIENTIST AND BIOMECHANICS RUNNING COACH.
You are provided with the ENTIRE un-filtered raw JSON telemetry payload from a Garmin Forerunner 165 for this run.

CRITICAL COACHING INSTRUCTIONS:
- The runner uses a Run/Walk interval strategy. Evaluate their active RUNNING pace ({run_summary_dict.get('run_pace_str')} min/km) against the 7:00 min/km target separately from walk recovery segments ({run_summary_dict.get('walk_pace_str')} min/km). Do not penalize overall average pace for intentional walk recovery breaks.
- Analyze ALL available parameters present in the raw JSON payload below (including Training Effect, Weather/Temperature/Humidity, Elevation Gain/Loss, Cadence, Stride Length, HR Zones, Lap Splits, VO2 Max, and Respiration Rate).
- Identify deep, non-obvious correlations across environmental conditions, form breakdowns, cardiovascular fatigue, and pacing strategy relative to the runner's 7:00 min/km 5K target.

RAW GARMIN TELEMETRY JSON PAYLOAD:
```json
{raw_json_str[:25000]}
```

RUNNER 30-DAY BASELINE:
{baseline_text}

TARGET BENCHMARK: 5K distance at 7:00 min/km pace.

Format your response strictly into these 3 Markdown sections:

### 🟢 What Worked Well
- (2-3 specific bullet points citing split data, active running pace, cadence, weather, or HR stability)

### ⚠️ What Broke Down / Tactical Flaws
- (2-3 specific bullet points detailing pacing volatility, over-striding, HR spikes, thermal stress, or walk duration ratio)

### 🎯 Standout Takeaway vs 7:00 Target Goal
- (A concise 2-sentence tactical summary detailing the exact adjustment needed for the next run to close the active run pace gap to 7:00 min/km)
"""

    try:
        import google.generativeai as genai
        genai.configure(api_key=gemini_key)

        model_names = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest", "gemini-1.5-flash"]
        for model_name in model_names:
            try:
                model = genai.GenerativeModel(model_name)
                res = model.generate_content(prompt)
                if res and hasattr(res, "text") and res.text:
                    return res.text
            except Exception:
                continue

        return generate_fallback_race_analysis(run_summary_dict, splits_text, baseline_text)
    except Exception:
        return generate_fallback_race_analysis(run_summary_dict, splits_text, baseline_text)


# ---------------------------------------------------------
# Sidebar (Global Controls Only)
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

# Helper function for delta formatting
def format_delta(curr, prev, fmt="{:.2f}", unit="", inverse=False):
    if prev is None or pd.isnull(prev):
        return None
    diff = curr - prev
    prefix = "+" if diff > 0 else ""
    return f"{prefix}{fmt.format(diff)} {unit}".strip()

# ---------------------------------------------------------
# Robust Top Navigation Bar (Linked to st.session_state)
# ---------------------------------------------------------
st.title("🏃 5K Running Performance Dashboard")

nav_options = [
    "🏠 Home Overview",
    "🏃 Single Run Deep-Dive",
    "📈 Training Trends & Workload",
    "😴 Recovery & Readiness",
    "🏆 Goals & Milestones"
]

if "navigation_tab" not in st.session_state:
    st.session_state["navigation_tab"] = nav_options[0]

selected_tab = st.radio(
    label="Navigation Tabs",
    options=nav_options,
    key="navigation_tab",
    label_visibility="collapsed",
    horizontal=True
)

# Fetch Gemini Key
gemini_key = None
try:
    if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
        gemini_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    pass

if not gemini_key:
    gemini_key = os.getenv("GEMINI_API_KEY")

# =========================================================
# 1. 🏠 HOME OVERVIEW (EMBEDDED GEMINI AI CHAT)
# =========================================================
if selected_tab == "🏠 Home Overview":
    st.header("🏠 Executive Overview & AI Coach")
    st.markdown("High-level performance summary & training status for **5K Goal (7:00 min/km)**")

    # Metrics Row using Shadcn Metric Cards
    latest_run = summary_df.iloc[0]
    
    thirty_days_ago = summary_df["start_time"].max() - timedelta(days=30)
    monthly_runs = summary_df[summary_df["start_time"] >= thirty_days_ago]
    monthly_vol_km = monthly_runs["distance_km"].sum()

    valid_paces = summary_df["avg_pace_min_km"].dropna()
    best_pace_min = valid_paces.min() if not valid_paces.empty else 8.5
    best_pace_row = summary_df.loc[summary_df["avg_pace_min_km"].idxmin()] if not valid_paces.empty else latest_run

    target_pace_dec = 7.00
    latest_pace_dec = latest_run["avg_pace_min_km"] if pd.notnull(latest_run["avg_pace_min_km"]) else 8.5
    pace_gap_sec = int(round((latest_pace_dec - target_pace_dec) * 60))

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        ui.metric_card(
            label="Last Run",
            value=f"{latest_run['distance_km']:.2f} km",
            description=f"{latest_run['start_time'].strftime('%b %d')} ({latest_run['avg_pace_str']}/km)",
            key="home_mc_1"
        )
    with c2:
        ui.metric_card(
            label="30-Day Volume",
            value=f"{monthly_vol_km:.1f} km",
            description=f"{len(monthly_runs)} completed runs",
            key="home_mc_2"
        )
    with c3:
        ui.metric_card(
            label="Best Pace Achieved",
            value=f"{best_pace_row['avg_pace_str']} /km",
            description=f"On {pd.to_datetime(best_pace_row['start_time']).strftime('%b %d')}",
            key="home_mc_3"
        )
    with c4:
        gap_str = f"{pace_gap_sec}s/km gap" if pace_gap_sec > 0 else "Target Met!"
        ui.metric_card(
            label="Target Pace Gap",
            value=gap_str,
            description="7:00 min/km benchmark",
            key="home_mc_4"
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

    # EMBEDDED GEMINI AI RUNNING COACH CHAT
    st.markdown("---")
    st.subheader("💬 Gemini AI Running Coach")
    st.caption("Ask questions about your Garmin telemetry, 5K training plan, pacing, or recovery tips.")

    if not gemini_key:
        st.warning("⚠️ `GEMINI_API_KEY` is missing. Please add `GEMINI_API_KEY` to `.env` or Streamlit Secrets.")
    else:
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

        if "messages" not in st.session_state:
            st.session_state.messages = [
                {
                    "role": "assistant",
                    "content": f"Hello! I'm your **Gemini AI Running Coach**. I've analyzed your **{total_runs} Garmin runs**. Your recent average pace is **{avg_pace_overall:.2f} min/km** with a target of **7:00 min/km**.\n\nHow can I help you reach your 5K target today? Ask me about pacing strategies, cadence drills, or recovery!"
                }
            ]

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if user_prompt := st.chat_input("Ask your Gemini AI Coach (e.g., 'How do I close the gap to 7:00 pace?')..."):
            st.session_state.messages.append({"role": "user", "content": user_prompt})
            with st.chat_message("user"):
                st.markdown(user_prompt)

            with st.chat_message("assistant"):
                with st.spinner("Analyzing telemetry & drafting response..."):
                    response_text = ""
                    try:
                        import google.generativeai as genai
                        genai.configure(api_key=gemini_key)

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
                            except Exception:
                                continue

                        if not generated:
                            response_text = f"I've reviewed your recent telemetry! Your average pace is {avg_pace_overall:.2f} min/km. Focusing on progressive splits and 165+ spm cadence drills will help close the pace gap to 7:00 min/km."

                    except Exception as e:
                        response_text = f"Coaching Assistant Error: {e}"

                    st.markdown(response_text)
                    st.session_state.messages.append({"role": "assistant", "content": response_text})


# =========================================================
# 2. 🏃 SINGLE RUN DEEP-DIVE (RUN/WALK & HR ZONES & RAW JSON GEMINI)
# =========================================================
elif selected_tab == "🏃 Single Run Deep-Dive":
    st.header("🏃 Activity Telemetry & Dynamic AI Race Analysis")

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

    # ---------------------------------------------------------
    # DYNAMIC GEMINI AI RACE ANALYSIS CARD (FULL RAW JSON)
    # ---------------------------------------------------------
    st.markdown("""<div class="insights-card">
        <div class="insights-header">
            <span>🤖 Gemini AI Sports-Science Telemetry Analysis</span>
        </div>""", unsafe_allow_html=True)

    col_ins_h, col_ins_btn = st.columns([4, 1])
    with col_ins_btn:
        if st.button("🔄 Re-analyze Run", key=f"btn_reanalyze_{selected_act_id}"):
            analyze_run_with_gemini.clear()
            st.rerun()

    # Build Km-by-Km Lap Breakdown
    km_splits_summary = []
    if not run_tp.empty and "distance_m" in run_tp.columns:
        run_tp["km_split"] = (run_tp["distance_m"] // 1000).astype(int) + 1
        for km_num, group in run_tp.groupby("km_split"):
            if km_num > 15:
                break
            avg_p = group["pace_min_km"].mean()
            avg_hr_split = group["heart_rate_bpm"].mean()
            avg_cad_split = group["cadence_spm"].mean()
            if pd.notnull(avg_p) and avg_p > 0:
                p_mins = int(avg_p)
                p_secs = int(round((avg_p - p_mins) * 60))
                if p_secs == 60:
                    p_mins += 1
                    p_secs = 0
                p_str = f"{p_mins}:{p_secs:02d}"
            else:
                p_str = "N/A"
            km_splits_summary.append(f"KM {km_num}: Pace {p_str} min/km ({avg_p:.2f}), HR {avg_hr_split:.0f} bpm, Cadence {avg_cad_split:.0f} spm")

    splits_text = "\n".join(km_splits_summary) if km_splits_summary else "Km splits not available."

    thirty_days_ago = summary_df["start_time"].max() - timedelta(days=30)
    monthly_runs = summary_df[summary_df["start_time"] >= thirty_days_ago]
    baseline_text = f"30-Day Avg Pace: {monthly_runs['avg_pace_min_km'].mean():.2f} min/km, Avg HR: {monthly_runs['avg_heart_rate'].mean():.0f} bpm, Avg Cadence: {monthly_runs['avg_cadence_spm'].mean():.0f} spm"

    run_dist_val = run_sum.get("run_distance_km") or run_sum["distance_km"]
    run_pace_str_val = run_sum.get("run_pace_str") or run_sum["avg_pace_str"]
    run_dur_val = run_sum.get("run_duration_min") or run_sum["duration_min"]
    walk_dist_val = run_sum.get("walk_distance_km") or 0.0
    walk_pace_str_val = run_sum.get("walk_pace_str") or "N/A"
    walk_dur_val = run_sum.get("walk_duration_min") or 0.0

    run_dict = {
        "distance_km": run_sum["distance_km"],
        "duration_min": run_sum["duration_min"],
        "run_distance_km": run_dist_val,
        "run_pace_str": run_pace_str_val,
        "run_pace_min_km": run_sum.get("run_pace_min_km") or run_sum["avg_pace_min_km"],
        "run_duration_min": run_dur_val,
        "walk_distance_km": walk_dist_val,
        "walk_pace_str": walk_pace_str_val,
        "walk_duration_min": walk_dur_val,
        "avg_pace_str": run_sum["avg_pace_str"],
        "avg_pace_min_km": run_sum["avg_pace_min_km"],
        "avg_heart_rate": run_sum["avg_heart_rate"],
        "max_heart_rate": run_sum["max_heart_rate"],
        "avg_cadence_spm": run_sum["avg_cadence_spm"],
        "stride_length_m": (run_sum["stride_length_cm"] / 100.0) if pd.notnull(run_sum["stride_length_cm"]) else None,
        "calories": run_sum["calories"],
        "start_time": run_sum["start_time"].strftime("%Y-%m-%d %H:%M")
    }

    with st.spinner("🤖 Processing Full Garmin Raw JSON & Generating Sports-Science Analysis..."):
        analysis_markdown = analyze_run_with_gemini(selected_act_id, run_dict, splits_text, baseline_text, gemini_key)

    st.markdown(analysis_markdown)
    st.markdown("</div>", unsafe_allow_html=True)

    # ---------------------------------------------------------
    # RUN vs WALK INTERVAL BREAKDOWN & HR ZONES
    # ---------------------------------------------------------
    col_rw1, col_rw2 = st.columns(2)

    with col_rw1:
        st.markdown("""<div style="background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(255,255,255,0.08); border-radius: 14px; padding: 18px;">
            <h4 style="margin-top:0; color: #3B82F6;">🏃 Run vs. 🚶 Walk Interval Breakdown</h4>
        """, unsafe_allow_html=True)
        
        st.markdown(f"""
        - 🏃 **Active Run Segment**: **{run_dist_val:.2f} km** @ **{run_pace_str_val} min/km** ({run_dur_val:.1f} min)
        - 🚶 **Walk Recovery Segment**: **{walk_dist_val:.2f} km** @ **{walk_pace_str_val} min/km** ({walk_dur_val:.1f} min)
        """)

        # Run / Walk Ratio Chart
        fig_rw_bar = gg.Figure()
        fig_rw_bar.add_trace(gg.Bar(y=["Time Breakdown"], x=[run_dur_val], name="Running", orientation="h", marker_color="#10B981"))
        fig_rw_bar.add_trace(gg.Bar(y=["Time Breakdown"], x=[walk_dur_val], name="Walking", orientation="h", marker_color="#F59E0B"))
        fig_rw_bar.update_layout(
            barmode="stack",
            height=120,
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=0, t=10, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_rw_bar, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_rw2:
        st.markdown("""<div style="background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(255,255,255,0.08); border-radius: 14px; padding: 18px;">
            <h4 style="margin-top:0; color: #3B82F6;">🫀 Heart Rate Zone Distribution</h4>
        """, unsafe_allow_html=True)

        z1 = run_sum.get("hr_z1_secs", 0) / 60.0 if pd.notnull(run_sum.get("hr_z1_secs")) else 0
        z2 = run_sum.get("hr_z2_secs", 0) / 60.0 if pd.notnull(run_sum.get("hr_z2_secs")) else 0
        z3 = run_sum.get("hr_z3_secs", 0) / 60.0 if pd.notnull(run_sum.get("hr_z3_secs")) else 0
        z4 = run_sum.get("hr_z4_secs", 0) / 60.0 if pd.notnull(run_sum.get("hr_z4_secs")) else 0
        z5 = run_sum.get("hr_z5_secs", 0) / 60.0 if pd.notnull(run_sum.get("hr_z5_secs")) else 0

        tot_z_min = z1 + z2 + z3 + z4 + z5
        if tot_z_min > 0:
            z1_pct, z2_pct, z3_pct, z4_pct, z5_pct = (z1/tot_z_min)*100, (z2/tot_z_min)*100, (z3/tot_z_min)*100, (z4/tot_z_min)*100, (z5/tot_z_min)*100
        else:
            z1_pct, z2_pct, z3_pct, z4_pct, z5_pct = 0, 0, 0, 0, 0

        fig_hr_zones = gg.Figure()
        fig_hr_zones.add_trace(gg.Bar(
            y=["Z1 Warmup", "Z2 Aerobic", "Z3 Tempo", "Z4 Threshold", "Z5 Anaerobic"],
            x=[z1_pct, z2_pct, z3_pct, z4_pct, z5_pct],
            orientation="h",
            marker_color=["#94A3B8", "#10B981", "#F59E0B", "#F97316", "#EF4444"],
            text=[f"{z1_pct:.1f}% ({z1:.1f}m)", f"{z2_pct:.1f}% ({z2:.1f}m)", f"{z3_pct:.1f}% ({z3:.1f}m)", f"{z4_pct:.1f}% ({z4:.1f}m)", f"{z5_pct:.1f}% ({z5:.1f}m)"],
            textposition="auto"
        ))

        fig_hr_zones.update_layout(
            height=200,
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=0, t=10, b=10),
            xaxis_title="% Time in Zone"
        )
        st.plotly_chart(fig_hr_zones, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Shadcn Metric Cards
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        ui.metric_card("Distance", f"{run_sum['distance_km']:.2f} km", delta=format_delta(run_sum['distance_km'], prev_run['distance_km'] if prev_run is not None else None, "{:.2f}", "km"), key="sr_mc_1")
    with col2:
        ui.metric_card("Duration", f"{run_sum['duration_min']:.1f} min", delta=format_delta(run_sum['duration_min'], prev_run['duration_min'] if prev_run is not None else None, "{:.1f}", "min"), key="sr_mc_2")
    with col3:
        ui.metric_card("Avg Pace", f"{run_sum['avg_pace_str']} /km", delta=format_delta(run_sum['avg_pace_min_km'], prev_run['avg_pace_min_km'] if prev_run is not None else None, "{:.2f}", "m/km"), key="sr_mc_3")
    with col4:
        ui.metric_card("Avg HR", f"{int(run_sum['avg_heart_rate'])} bpm" if pd.notnull(run_sum['avg_heart_rate']) else "N/A", delta=format_delta(run_sum['avg_heart_rate'], prev_run['avg_heart_rate'] if prev_run is not None else None, "{:.0f}", "bpm"), key="sr_mc_4")
    with col5:
        ui.metric_card("Avg Cadence", f"{int(run_sum['avg_cadence_spm'])} spm" if pd.notnull(run_sum['avg_cadence_spm']) else "N/A", delta=format_delta(run_sum['avg_cadence_spm'], prev_run['avg_cadence_spm'] if prev_run is not None else None, "{:.0f}", "spm"), key="sr_mc_5")
    with col6:
        stride_m_val = (run_sum['stride_length_cm'] / 100.0) if pd.notnull(run_sum['stride_length_cm']) and run_sum['stride_length_cm'] > 0 else 0.0
        prev_stride_m = (prev_run['stride_length_cm'] / 100.0) if prev_run is not None and pd.notnull(prev_run.get('stride_length_cm')) else None
        ui.metric_card("Stride Length", f"{stride_m_val:.2f} m", delta=format_delta(stride_m_val, prev_stride_m, "{:.2f}", "m"), key="sr_mc_6")

    st.markdown("<br>", unsafe_allow_html=True)

    if not run_tp.empty:
        fig_pace = px.line(
            run_tp, x="distance_km", y="clean_pace",
            title="⚡ Instantaneous Pace Profile (Target: 7:00 min/km)",
            labels={"distance_km": "Distance (km)", "clean_pace": "Pace (min/km)"},
            color_discrete_sequence=["#3B82F6"]
        )
        fig_pace.add_hrect(y0=6.75, y1=7.25, fillcolor="rgba(16, 185, 129, 0.15)", line_width=0, annotation_text="🎯 Target Zone", annotation_position="top left", annotation_font_color="#10B981")
        fig_pace.add_hline(y=7.0, line_dash="dash", line_color="#EF4444", annotation_text="7:00 Benchmark")
        fig_pace.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig_pace, use_container_width=True)

        col_left, col_right = st.columns(2)
        with col_left:
            fig_hr_ele = make_subplots(specs=[[{"secondary_y": True}]])
            fig_hr_ele.add_trace(gg.Scatter(x=run_tp["distance_km"], y=run_tp["elevation_m"], name="Elevation (m)", fill="tozeroy", fillcolor="rgba(148, 163, 184, 0.15)", line=dict(color="#94A3B8", width=1.5)), secondary_y=False)
            fig_hr_ele.add_trace(gg.Scatter(x=run_tp["distance_km"], y=run_tp["heart_rate_bpm"], name="Heart Rate (bpm)", line=dict(color="#F43F5E", width=2)), secondary_y=True)
            fig_hr_ele.update_layout(title="❤️ Heart Rate & Elevation Profile", template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_hr_ele, use_container_width=True)

        with col_right:
            fig_bio = make_subplots(specs=[[{"secondary_y": True}]])
            fig_bio.add_trace(gg.Scatter(x=run_tp["distance_km"], y=run_tp["cadence_spm"], name="Cadence (spm)", line=dict(color="#10B981", width=2)), secondary_y=False)
            fig_bio.add_trace(gg.Scatter(x=run_tp["distance_km"], y=run_tp["stride_length_m"], name="Stride Length (m)", line=dict(color="#F59E0B", width=2)), secondary_y=True)
            fig_bio.update_layout(title="⚙️ Biomechanics (Cadence & Stride)", template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_bio, use_container_width=True)


# =========================================================
# 3. 📈 TRAINING TRENDS & WORKLOAD (WITH ONE-LINE INSIGHTS)
# =========================================================
elif selected_tab == "📈 Training Trends & Workload":
    st.header("📈 Multi-Metric Training Trends & Workload")
    st.markdown("Longitudinal progression curves with **7-day rolling average trendlines** and dynamic metric insights.")

    df_chrono = summary_df.sort_values("start_time").copy()
    df_chrono["stride_m"] = df_chrono["stride_length_cm"] / 100.0

    # Calculate 7-day rolling averages
    df_chrono["roll_dist"] = df_chrono["distance_km"].rolling(7, min_periods=1).mean()
    df_chrono["roll_pace"] = df_chrono["avg_pace_min_km"].rolling(7, min_periods=1).mean()
    df_chrono["roll_hr"] = df_chrono["avg_heart_rate"].rolling(7, min_periods=1).mean()
    df_chrono["roll_cad"] = df_chrono["avg_cadence_spm"].rolling(7, min_periods=1).mean()
    df_chrono["roll_stride"] = df_chrono["stride_m"].rolling(7, min_periods=1).mean()
    df_chrono["roll_cal"] = df_chrono["calories"].rolling(7, min_periods=1).mean()

    # Dynamic Insights calculations
    curr_roll_dist = df_chrono["roll_dist"].iloc[-1]
    curr_roll_pace = df_chrono["roll_pace"].iloc[-1]
    curr_roll_hr = df_chrono["roll_hr"].iloc[-1]
    curr_roll_cad = df_chrono["roll_cad"].iloc[-1]
    curr_roll_stride = df_chrono["roll_stride"].iloc[-1]
    curr_roll_cal = df_chrono["roll_cal"].iloc[-1]

    pace_diff_sec = int(round((curr_roll_pace - 7.00) * 60))

    # Grid Layout with One-Line Insights & Seamless Transparent Backgrounds
    row1_c1, row1_c2 = st.columns(2)
    with row1_c1:
        st.info(f"📏 **Distance Insight:** 7-day rolling average distance is **{curr_roll_dist:.2f} km/run** across {len(df_chrono)} logged activities.")
        fig1 = gg.Figure()
        fig1.add_trace(gg.Bar(x=df_chrono["start_time"], y=df_chrono["distance_km"], name="Distance (km)", marker_color="#3B82F6"))
        fig1.add_trace(gg.Scatter(x=df_chrono["start_time"], y=df_chrono["roll_dist"], name="7-Day Rolling Avg", line=dict(color="#F59E0B", width=2.5)))
        fig1.update_layout(title="📏 Activity Distance (km)", template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig1, use_container_width=True)

    with row1_c2:
        st.info(f"⚡ **Pace Insight:** 7-day rolling average pace is **{curr_roll_pace:.2f} min/km** ({pace_diff_sec}s/km gap to 7:00 target).")
        fig2 = gg.Figure()
        fig2.add_trace(gg.Scatter(x=df_chrono["start_time"], y=df_chrono["avg_pace_min_km"], mode="markers+lines", name="Pace (min/km)", line=dict(color="#3B82F6", width=1.5)))
        fig2.add_trace(gg.Scatter(x=df_chrono["start_time"], y=df_chrono["roll_pace"], name="7-Day Rolling Avg", line=dict(color="#10B981", width=2.5)))
        fig2.add_hline(y=7.0, line_dash="dash", line_color="#EF4444", annotation_text="7:00 Target")
        fig2.update_layout(title="⚡ Average Pace (min/km)", template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig2, use_container_width=True)

    row2_c1, row2_c2 = st.columns(2)
    with row2_c1:
        st.info(f"❤️ **Heart Rate Insight:** Rolling average HR is **{curr_roll_hr:.0f} bpm**, demonstrating stable cardiovascular response.")
        fig3 = gg.Figure()
        fig3.add_trace(gg.Scatter(x=df_chrono["start_time"], y=df_chrono["avg_heart_rate"], mode="markers+lines", name="Avg HR (bpm)", line=dict(color="#F43F5E", width=1.5)))
        fig3.add_trace(gg.Scatter(x=df_chrono["start_time"], y=df_chrono["roll_hr"], name="7-Day Rolling Avg", line=dict(color="#3B82F6", width=2.5)))
        fig3.update_layout(title="❤️ Average Heart Rate (bpm)", template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig3, use_container_width=True)

    with row2_c2:
        st.info(f"⚙️ **Cadence Insight:** Rolling average cadence is **{curr_roll_cad:.0f} spm** — aim for 165+ spm to shorten ground contact time.")
        fig4 = gg.Figure()
        fig4.add_trace(gg.Scatter(x=df_chrono["start_time"], y=df_chrono["avg_cadence_spm"], mode="markers+lines", name="Cadence (spm)", line=dict(color="#10B981", width=1.5)))
        fig4.add_trace(gg.Scatter(x=df_chrono["start_time"], y=df_chrono["roll_cad"], name="7-Day Rolling Avg", line=dict(color="#F59E0B", width=2.5)))
        fig4.update_layout(title="⚙️ Cadence (spm)", template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig4, use_container_width=True)

    row3_c1, row3_c2 = st.columns(2)
    with row3_c1:
        st.info(f"👟 **Stride Insight:** Rolling average stride length is **{curr_roll_stride:.2f} m** — well synchronized with step turnover.")
        fig5 = gg.Figure()
        fig5.add_trace(gg.Scatter(x=df_chrono["start_time"], y=df_chrono["stride_m"], mode="markers+lines", name="Stride Length (m)", line=dict(color="#F59E0B", width=1.5)))
        fig5.add_trace(gg.Scatter(x=df_chrono["start_time"], y=df_chrono["roll_stride"], name="7-Day Rolling Avg", line=dict(color="#10B981", width=2.5)))
        fig5.update_layout(title="👟 Stride Length (m)", template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig5, use_container_width=True)

    with row3_c2:
        st.info(f"🔥 **Calorie Insight:** Rolling average energy expenditure is **{curr_roll_cal:.0f} kcal** per session.")
        fig6 = gg.Figure()
        fig6.add_trace(gg.Bar(x=df_chrono["start_time"], y=df_chrono["calories"], name="Calories (kcal)", marker_color="#8B5CF6"))
        fig6.add_trace(gg.Scatter(x=df_chrono["start_time"], y=df_chrono["roll_cal"], name="7-Day Rolling Avg", line=dict(color="#3B82F6", width=2.5)))
        fig6.update_layout(title="🔥 Calories Burned (kcal)", template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig6, use_container_width=True)


# =========================================================
# 4. 😴 RECOVERY & READINESS
# =========================================================
elif selected_tab == "😴 Recovery & Readiness":
    st.header("😴 Recovery & Readiness Analytics")

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
        fig_scatter.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_scatter, use_container_width=True)

    with col_r2:
        fig_vo2 = gg.Figure()
        if "vo2_max" in summary_df.columns and summary_df["vo2_max"].notnull().any():
            vo2_clean = summary_df.dropna(subset=["vo2_max"])
            fig_vo2.add_trace(gg.Scatter(x=vo2_clean["start_time"], y=vo2_clean["vo2_max"], mode="lines+markers", name="VO2 Max", line=dict(color="#10B981", width=3), marker=dict(size=8)))
        fig_vo2.add_trace(gg.Scatter(x=summary_df["start_time"], y=summary_df["max_heart_rate"], mode="lines+markers", name="Peak HR (bpm)", line=dict(color="#EF4444", width=2, dash="dot"), marker=dict(size=6)))
        fig_vo2.update_layout(title="📈 Aerobic Capacity & Peak HR Trend", template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_vo2, use_container_width=True)


# =========================================================
# 5. 🏆 GOALS & MILESTONES
# =========================================================
elif selected_tab == "🏆 Goals & Milestones":
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
            title={'text': "Current Best Pace vs 7:00 Target (min/km)", 'font': {'size': 16, 'color': '#F8FAFC'}},
            delta={'reference': target_pace, 'increasing': {'color': "#EF4444"}, 'decreasing': {'color': "#10B981"}, 'valueformat': '.2f'},
            number={'font': {'color': '#3B82F6', 'size': 36}, 'valueformat': '.2f'},
            gauge={
                'axis': {'range': [10.0, 5.0], 'tickwidth': 1, 'tickcolor': "#94A3B8"},
                'bar': {'color': "#3B82F6"},
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
