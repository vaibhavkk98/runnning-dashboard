import os
import sys
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

# Load environment variables
load_dotenv()

GARMIN_EMAIL = os.getenv("GARMIN_EMAIL")
GARMIN_PASSWORD = os.getenv("GARMIN_PASSWORD")
TOKEN_STORE = os.path.expanduser("~/.garminconnect")
DATA_DIR = Path("data")


def get_garmin_client() -> Garmin:
    """Log into Garmin Connect with session token caching."""
    if not GARMIN_EMAIL or not GARMIN_PASSWORD or GARMIN_EMAIL == "your_email@example.com":
        raise ValueError("GARMIN_EMAIL and GARMIN_PASSWORD must be configured in .env file.")

    print(f"Connecting to Garmin Connect for user: {GARMIN_EMAIL}...")
    client = Garmin(GARMIN_EMAIL, GARMIN_PASSWORD)

    try:
        # Attempts to load cached tokens first to avoid rate limiting
        client.login(tokenstore=TOKEN_STORE)
        print("Successfully logged into Garmin Connect!")
        return client
    except GarminConnectTooManyRequestsError:
        print("Rate limit reached (429). Please wait a few minutes before trying again.")
        sys.exit(1)
    except GarminConnectAuthenticationError as e:
        print(f"Authentication error: {e}")
        sys.exit(1)
    except GarminConnectConnectionError as e:
        print(f"Connection error: {e}")
        sys.exit(1)


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

        distance_km = round(distance_m / 1000.0, 3)
        duration_min = round(duration_s / 60.0, 2)

        # Average pace in min/km
        if avg_speed_mps > 0:
            avg_pace_dec = (1000.0 / avg_speed_mps) / 60.0
            pace_mins = int(avg_pace_dec)
            pace_secs = int(round((avg_pace_dec - pace_mins) * 60))
            if pace_secs == 60:
                pace_mins += 1
                pace_secs = 0
            avg_pace_str = f"{pace_mins}:{pace_secs:02d}"
        else:
            avg_pace_dec = None
            avg_pace_str = "N/A"

        summary_list.append({
            "activity_id": act_id,
            "activity_name": act.get("activityName"),
            "start_time": start_time,
            "distance_km": distance_km,
            "duration_min": duration_min,
            "elapsed_duration_min": round((act.get("elapsedDuration", 0) or 0) / 60.0, 2),
            "avg_pace_min_km": round(avg_pace_dec, 2) if avg_pace_dec else None,
            "avg_pace_str": avg_pace_str,
            "avg_heart_rate": act.get("averageHR"),
            "max_heart_rate": act.get("maxHR"),
            "avg_cadence_spm": act.get("averageRunningCadenceInStepsPerMinute"),
            "stride_length_cm": act.get("strideLength"),
            "elevation_gain_m": act.get("elevationGain"),
            "calories": act.get("calories"),
            "vo2_max": act.get("vO2MaxValue"),
        })

    return pd.DataFrame(summary_list)


def extract_trackpoints(client, summary_df):
    """Extract raw time-series trackpoints for each running activity."""
    all_trackpoints = []

    for idx, row in summary_df.iterrows():
        act_id = row["activity_id"]
        start_time = row["start_time"]
        act_name = row["activity_name"]

        print(f"[{idx+1}/{len(summary_df)}] Fetching trackpoints for activity {act_id} ({act_name} - {start_time})...")

        try:
            details = client.get_activity_details(act_id)
        except Exception as e:
            print(f"  Warning: Failed to get details for activity {act_id}: {e}")
            continue

        if not details or "activityDetailMetrics" not in details:
            print(f"  No detail metrics found for activity {act_id}.")
            continue

        # Map metric index to key descriptor name
        descriptors = {
            d["metricsIndex"]: d["key"]
            for d in details.get("metricDescriptors", [])
        }

        metrics_list = details.get("activityDetailMetrics", [])

        for item in metrics_list:
            vals = item.get("metrics", [])
            m_dict = {descriptors.get(i, f"idx_{i}"): vals[i] if i < len(vals) else None for i in range(len(vals))}

            ts_raw = m_dict.get("directTimestamp")
            if ts_raw is None:
                continue

            ts_dt = pd.to_datetime(ts_raw, unit="ms", errors="coerce")

            speed_mps = m_dict.get("directSpeed")
            if speed_mps is not None and speed_mps > 0:
                pace_min_km = (1000.0 / speed_mps) / 60.0
            else:
                pace_min_km = None

            # Cadence (spm)
            cadence = m_dict.get("directDoubleCadence")
            if cadence is None or cadence == 0:
                single_cadence = m_dict.get("directRunCadence")
                if single_cadence is not None:
                    cadence = single_cadence * 2

            # Stride length in meters
            stride_cm = m_dict.get("directStrideLength")
            stride_m = (stride_cm / 100.0) if stride_cm is not None else None

            all_trackpoints.append({
                "activity_id": act_id,
                "start_time": start_time,
                "timestamp": ts_dt,
                "distance_m": m_dict.get("sumDistance"),
                "duration_s": m_dict.get("sumDuration"),
                "speed_mps": speed_mps,
                "pace_min_km": round(pace_min_km, 3) if pace_min_km is not None else None,
                "heart_rate_bpm": m_dict.get("directHeartRate"),
                "cadence_spm": cadence,
                "stride_length_m": round(stride_m, 3) if stride_m is not None else None,
                "elevation_m": m_dict.get("directElevation"),
                "latitude": m_dict.get("directLatitude"),
                "longitude": m_dict.get("directLongitude"),
            })

    return pd.DataFrame(all_trackpoints)


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    client = get_garmin_client()

    print("Fetching activities from Garmin Connect...")
    activities = client.get_activities(0, 100)
    print(f"Retrieved {len(activities)} total activities.")

    summary_df = parse_runs(activities)
    print(f"Filtered {len(summary_df)} running activities.")

    if summary_df.empty:
        print("No running activities found.")
        return

    runs_summary_path = DATA_DIR / "runs_summary.csv"
    summary_df.to_csv(runs_summary_path, index=False)
    print(f"Saved activity summaries to {runs_summary_path}")

    print("\nExtracting raw trackpoints...")
    trackpoints_df = extract_trackpoints(client, summary_df)

    raw_trackpoints_path = DATA_DIR / "raw_trackpoints.csv"
    trackpoints_df.to_csv(raw_trackpoints_path, index=False)
    print(f"Saved {len(trackpoints_df)} raw trackpoints to {raw_trackpoints_path}")

    print("\nExtraction Summary:")
    print(f"Total Runs Parsed: {len(summary_df)}")
    print(f"Total Trackpoints Saved: {len(trackpoints_df)}")


if __name__ == "__main__":
    main()
