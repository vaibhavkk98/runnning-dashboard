import os
import sys
import json
import pandas as pd
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

# Load environment variables from .env if present
load_dotenv()

DATA_DIR = Path("data")


def get_credentials():
    """Retrieve credentials from Streamlit Secrets or fallback to environment variables."""
    email = None
    password = None

    # 1. Try Streamlit secrets (Streamlit Cloud deployment)
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            email = st.secrets.get("GARMIN_EMAIL")
            password = st.secrets.get("GARMIN_PASSWORD")
    except Exception:
        pass

    # 2. Fallback to environment variables / .env
    if not email or not password:
        email = os.getenv("GARMIN_EMAIL")
        password = os.getenv("GARMIN_PASSWORD")

    return email, password


def get_token_store():
    """Retrieve a writable directory path for Garmin session tokens."""
    token_path = os.path.expanduser("~/.garminconnect")
    try:
        os.makedirs(token_path, exist_ok=True)
        return token_path
    except Exception:
        fallback_path = "/tmp/.garminconnect"
        os.makedirs(fallback_path, exist_ok=True)
        return fallback_path


def get_garmin_client() -> Garmin:
    """Log into Garmin Connect with session token caching."""
    email, password = get_credentials()

    if not email or not password or email == "your_email@example.com":
        raise ValueError("GARMIN_EMAIL and GARMIN_PASSWORD must be configured in Streamlit Secrets or .env file.")

    print(f"Connecting to Garmin Connect for user: {email}...")
    client = Garmin(email, password)
    token_store = get_token_store()

    try:
        client.login(tokenstore=token_store)
        print("Successfully logged into Garmin Connect!")
        return client
    except GarminConnectTooManyRequestsError:
        print("Rate limit reached (429). Please wait a few minutes before trying again.")
        raise
    except GarminConnectAuthenticationError as e:
        print(f"Authentication error: {e}")
        raise
    except GarminConnectConnectionError as e:
        print(f"Connection error: {e}")
        raise


def format_pace(pace_dec):
    """Format decimal pace into M:SS string."""
    if pace_dec and pace_dec > 0:
        mins = int(pace_dec)
        secs = int(round((pace_dec - mins) * 60))
        if secs == 60:
            mins += 1
            secs = 0
        return f"{mins}:{secs:02d}"
    return "N/A"


def parse_runs(activities):
    """Extract summary information for running activities."""
    summary_list = []

    for act in activities:
        act_type = act.get("activityType", {})
        type_key = str(act_type.get("typeKey", "")).lower()

        # Include running activities
        if "run" not in type_key and act_type.get("parentTypeId") != 17:
            continue

        act_id = act.get("activityId")
        start_time = act.get("startTimeLocal")
        distance_m = act.get("distance", 0) or 0
        duration_s = act.get("duration", 0) or 0
        avg_speed_mps = act.get("averageSpeed", 0) or 0
        avg_cadence_spm = act.get("averageRunningCadenceInStepsPerMinute")

        distance_km = round(distance_m / 1000.0, 3)
        duration_min = round(duration_s / 60.0, 2)

        # Average pace in min/km and seconds/km
        if avg_speed_mps > 0:
            avg_pace_dec = (1000.0 / avg_speed_mps) / 60.0
            avg_pace_sec = round(avg_pace_dec * 60.0, 1)
            avg_pace_str = format_pace(avg_pace_dec)
        else:
            avg_pace_dec = None
            avg_pace_sec = None
            avg_pace_str = "N/A"

        # Stride length in cm: if Garmin returns null/0, derive dynamically
        stride_cm = act.get("strideLength")
        if (stride_cm is None or stride_cm == 0) and avg_speed_mps > 0 and avg_cadence_spm and avg_cadence_spm > 0:
            steps_per_sec = avg_cadence_spm / 60.0
            stride_m = avg_speed_mps / steps_per_sec
            stride_cm = round(stride_m * 100.0, 2)

        summary_list.append({
            "activity_id": act_id,
            "activity_name": act.get("activityName"),
            "start_time": start_time,
            "distance_km": distance_km,
            "duration_min": duration_min,
            "elapsed_duration_min": round((act.get("elapsedDuration", 0) or 0) / 60.0, 2),
            "avg_pace_min_km": round(avg_pace_dec, 2) if avg_pace_dec else None,
            "avg_pace_sec": avg_pace_sec,
            "avg_pace_str": avg_pace_str,
            "avg_heart_rate": act.get("averageHR"),
            "max_heart_rate": act.get("maxHR"),
            "avg_cadence_spm": avg_cadence_spm,
            "stride_length_cm": round(stride_cm, 2) if stride_cm is not None else None,
            "elevation_gain_m": act.get("elevationGain"),
            "calories": act.get("calories"),
            "vo2_max": act.get("vO2MaxValue"),
        })

    return pd.DataFrame(summary_list)


def process_run_walk_segmentation(tp_df):
    """Segment trackpoints into Running (>=120 spm), Walking (30-119 spm), and Idle (<30 spm)."""
    if tp_df.empty:
        return {}

    tp_df = tp_df.copy()
    tp_df["cadence_spm"] = tp_df["cadence_spm"].fillna(0)
    tp_df["speed_mps"] = tp_df["speed_mps"].fillna(0)

    run_mask = tp_df["cadence_spm"] >= 120
    walk_mask = (tp_df["cadence_spm"] >= 30) & (tp_df["cadence_spm"] < 120)
    idle_mask = tp_df["cadence_spm"] < 30

    tp_run = tp_df[run_mask]
    tp_walk = tp_df[walk_mask]
    tp_idle = tp_df[idle_mask]

    # Assume sampling interval ~2s
    run_sec = len(tp_run) * 2
    walk_sec = len(tp_walk) * 2
    idle_sec = len(tp_idle) * 2

    run_dist_m = tp_run["speed_mps"].sum() * 2
    walk_dist_m = tp_walk["speed_mps"].sum() * 2

    run_speed_avg = tp_run["speed_mps"].mean() if len(tp_run) > 0 else 0
    walk_speed_avg = tp_walk["speed_mps"].mean() if len(tp_walk) > 0 else 0

    run_pace_dec = (1000.0 / run_speed_avg) / 60.0 if run_speed_avg > 0 else None
    walk_pace_dec = (1000.0 / walk_speed_avg) / 60.0 if walk_speed_avg > 0 else None

    return {
        "run_duration_min": round(run_sec / 60.0, 1),
        "run_distance_km": round(run_dist_m / 1000.0, 2),
        "run_pace_min_km": round(run_pace_dec, 2) if run_pace_dec else None,
        "run_pace_str": format_pace(run_pace_dec),
        "walk_duration_min": round(walk_sec / 60.0, 1),
        "walk_distance_km": round(walk_dist_m / 1000.0, 2),
        "walk_pace_min_km": round(walk_pace_dec, 2) if walk_pace_dec else None,
        "walk_pace_str": format_pace(walk_pace_dec),
        "idle_duration_min": round(idle_sec / 60.0, 1),
    }


def extract_trackpoints_and_details(client, summary_df):
    """Extract raw time-series trackpoints, HR zones, and Run/Walk segmentation for each activity, and dump full raw JSON."""
    all_trackpoints = []
    enriched_summary = []

    for idx, row in summary_df.iterrows():
        act_id = row["activity_id"]
        start_time = row["start_time"]
        act_name = row["activity_name"]

        print(f"[{idx+1}/{len(summary_df)}] Fetching details for activity {act_id} ({act_name} - {start_time})...")

        # 1. Fetch Full Raw Activity JSON payload endpoints
        full_summary_raw = None
        splits_raw = None
        weather_raw = None
        hr_zones_raw = None

        try:
            full_summary_raw = client.get_activity(act_id)
        except Exception as e:
            print(f"  Warning: Full activity summary failed for {act_id}: {e}")

        try:
            splits_raw = client.get_activity_splits(act_id)
        except Exception as e:
            print(f"  Warning: Activity splits failed for {act_id}: {e}")

        try:
            weather_raw = client.get_activity_weather(act_id)
        except Exception as e:
            print(f"  Warning: Activity weather failed for {act_id}: {e}")

        try:
            hr_zones_raw = client.get_activity_hr_in_timezones(act_id)
        except Exception as e:
            print(f"  Warning: HR zones failed for {act_id}: {e}")

        # Parse HR zones into dict
        hr_z_dict = {"hr_z1_secs": 0, "hr_z2_secs": 0, "hr_z3_secs": 0, "hr_z4_secs": 0, "hr_z5_secs": 0}
        if hr_zones_raw and isinstance(hr_zones_raw, list):
            for z in hr_zones_raw:
                z_num = z.get("zoneNumber")
                if z_num in [1, 2, 3, 4, 5]:
                    hr_z_dict[f"hr_z{z_num}_secs"] = round(z.get("secsInZone", 0), 1)

        # 2. Fetch Activity detail trackpoints
        act_tps = []
        details_raw = None
        try:
            details_raw = client.get_activity_details(act_id)
            if details_raw and "activityDetailMetrics" in details_raw:
                descriptors = {
                    d["metricsIndex"]: d["key"]
                    for d in details_raw.get("metricDescriptors", [])
                }

                for item in details_raw.get("activityDetailMetrics", []):
                    vals = item.get("metrics", [])
                    m_dict = {descriptors.get(i, f"idx_{i}"): vals[i] if i < len(vals) else None for i in range(len(vals))}

                    ts_raw = m_dict.get("directTimestamp")
                    if ts_raw is None:
                        continue

                    ts_dt = pd.to_datetime(ts_raw, unit="ms", errors="coerce")

                    speed_mps = m_dict.get("directSpeed")
                    pace_min_km = (1000.0 / speed_mps) / 60.0 if speed_mps and speed_mps > 0 else None

                    cadence = m_dict.get("directDoubleCadence")
                    if cadence is None or cadence == 0:
                        single_cadence = m_dict.get("directRunCadence")
                        if single_cadence is not None:
                            cadence = single_cadence * 2

                    stride_cm = m_dict.get("directStrideLength")
                    if stride_cm is not None and stride_cm > 0:
                        stride_m = stride_cm / 100.0
                    elif speed_mps and speed_mps > 0 and cadence and cadence > 0:
                        stride_m = speed_mps / (cadence / 60.0)
                    else:
                        stride_m = None

                    tp_obj = {
                        "activity_id": act_id,
                        "start_time": start_time,
                        "timestamp": ts_dt,
                        "distance_m": m_dict.get("sumDistance"),
                        "duration_s": m_dict.get("sumDuration"),
                        "speed_mps": speed_mps,
                        "pace_min_km": round(pace_min_km, 3) if pace_min_km else None,
                        "heart_rate_bpm": m_dict.get("directHeartRate"),
                        "cadence_spm": cadence,
                        "stride_length_m": round(stride_m, 2) if stride_m else None,
                        "elevation_m": m_dict.get("directElevation"),
                        "latitude": m_dict.get("directLatitude"),
                        "longitude": m_dict.get("directLongitude"),
                    }
                    all_trackpoints.append(tp_obj)
                    act_tps.append(tp_obj)
        except Exception as e:
            print(f"  Warning: Details extraction failed for {act_id}: {e}")

        # Save Raw Activity JSON payload to data/raw_activity_{act_id}.json
        try:
            raw_payload = {
                "activity_id": act_id,
                "summary": full_summary_raw,
                "splits": splits_raw,
                "weather": weather_raw,
                "hr_zones": hr_zones_raw,
                "details_sample": act_tps[::5] if len(act_tps) > 100 else act_tps
            }
            raw_json_path = DATA_DIR / f"raw_activity_{act_id}.json"
            with open(raw_json_path, "w") as f:
                json.dump(raw_payload, f, indent=2, default=str)
            print(f"  Saved raw JSON payload to {raw_json_path}")
        except Exception as e:
            print(f"  Warning: Failed saving raw JSON for {act_id}: {e}")

        # Compute Run/Walk Segmentation
        act_tp_df = pd.DataFrame(act_tps) if act_tps else pd.DataFrame()
        segment_dict = process_run_walk_segmentation(act_tp_df)

        # Merge summary record
        row_dict = row.to_dict()
        row_dict.update(hr_z_dict)
        row_dict.update(segment_dict)
        enriched_summary.append(row_dict)

    return pd.DataFrame(enriched_summary), pd.DataFrame(all_trackpoints)


def fetch_garmin_data():
    """Main execution function to fetch and save Garmin runs, trackpoints, HR zones, and full raw JSON payloads."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    client = get_garmin_client()

    print("Fetching activities from Garmin Connect...")
    activities = client.get_activities(0, 100)
    print(f"Retrieved {len(activities)} total activities.")

    raw_summary_df = parse_runs(activities)
    print(f"Filtered {len(raw_summary_df)} running activities.")

    if raw_summary_df.empty:
        print("No running activities found.")
        return False

    print("\nExtracting trackpoints, HR zones, Run/Walk segmentation & raw JSON payloads...")
    summary_df, trackpoints_df = extract_trackpoints_and_details(client, raw_summary_df)

    runs_summary_path = DATA_DIR / "runs_summary.csv"
    summary_df.to_csv(runs_summary_path, index=False)
    print(f"Saved activity summaries to {runs_summary_path}")

    raw_trackpoints_path = DATA_DIR / "raw_trackpoints.csv"
    trackpoints_df.to_csv(raw_trackpoints_path, index=False)
    print(f"Saved {len(trackpoints_df)} raw trackpoints to {raw_trackpoints_path}")

    print("\nExtraction Summary:")
    print(f"Total Runs Parsed: {len(summary_df)}")
    print(f"Total Trackpoints Saved: {len(trackpoints_df)}")
    return True


if __name__ == "__main__":
    fetch_garmin_data()
