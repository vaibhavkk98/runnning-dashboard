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


def extract_native_hr_zones(client, act_id, act_tps=None):
    """Fetch official native HR zones directly from Garmin API, with robust list/dict handling and trackpoint fallback."""
    hr_z_dict = {"hr_z1_secs": 0.0, "hr_z2_secs": 0.0, "hr_z3_secs": 0.0, "hr_z4_secs": 0.0, "hr_z5_secs": 0.0}
    hr_zones_raw = None
    try:
        hr_zones_raw = client.get_activity_hr_in_timezones(act_id)
        if hr_zones_raw:
            if isinstance(hr_zones_raw, list):
                for z in hr_zones_raw:
                    if isinstance(z, dict):
                        z_num = z.get("zoneNumber") or z.get("zoneIndex")
                        secs = float(z.get("secsInZone") or z.get("secs") or z.get("duration") or 0.0)
                        if z_num in [1, 2, 3, 4, 5]:
                            hr_z_dict[f"hr_z{z_num}_secs"] = round(secs, 1)
            elif isinstance(hr_zones_raw, dict):
                for k, v in hr_zones_raw.items():
                    if "z" in k.lower() or "zone" in k.lower():
                        for z_num in range(1, 6):
                            if str(z_num) in k:
                                secs = float(v.get("secsInZone") or v if isinstance(v, (int, float)) else 0.0)
                                hr_z_dict[f"hr_z{z_num}_secs"] = round(secs, 1)
    except Exception as e:
        print(f"  Warning: HR zones API failed for {act_id}: {e}")

    # Fallback to trackpoint heart rate values if all HR zones remain 0
    tot_secs = sum(hr_z_dict.values())
    if tot_secs == 0 and act_tps:
        tp_df = pd.DataFrame(act_tps).dropna(subset=["heart_rate_bpm"])
        if not tp_df.empty:
            max_hr = tp_df["heart_rate_bpm"].max()
            if max_hr and max_hr > 100:
                z1_b, z2_b, z3_b, z4_b = max_hr * 0.60, max_hr * 0.70, max_hr * 0.80, max_hr * 0.90
                hrs = tp_df["heart_rate_bpm"]
                hr_z_dict["hr_z1_secs"] = float(len(hrs[hrs < z1_b]) * 2)
                hr_z_dict["hr_z2_secs"] = float(len(hrs[(hrs >= z1_b) & (hrs < z2_b)]) * 2)
                hr_z_dict["hr_z3_secs"] = float(len(hrs[(hrs >= z2_b) & (hrs < z3_b)]) * 2)
                hr_z_dict["hr_z4_secs"] = float(len(hrs[(hrs >= z3_b) & (hrs < z4_b)]) * 2)
                hr_z_dict["hr_z5_secs"] = float(len(hrs[hrs >= z4_b]) * 2)

    return hr_z_dict, hr_zones_raw


def extract_native_typed_splits(client, act_id, summary_raw=None, act_tps=None):
    """Fetch official native Run/Walk/Stand typed splits directly from Garmin API with multi-schema fallback."""
    res = {
        "run_duration_min": 0.0,
        "run_distance_km": 0.0,
        "run_pace_min_km": None,
        "run_pace_str": "N/A",
        "walk_duration_min": 0.0,
        "walk_distance_km": 0.0,
        "walk_pace_min_km": None,
        "walk_pace_str": "N/A",
        "idle_duration_min": 0.0
    }
    typed_splits_raw = None

    # 1. Try splitSummaries in summary_raw
    if summary_raw and isinstance(summary_raw, dict):
        split_summaries = summary_raw.get("splitSummaries")
        if split_summaries and isinstance(split_summaries, list):
            run_dur_s, run_dist_m = 0.0, 0.0
            walk_dur_s, walk_dist_m = 0.0, 0.0
            found_splits = False
            for s in split_summaries:
                stype = str(s.get("splitType") or s.get("typeKey") or s.get("type") or "").upper()
                dur = float(s.get("duration", 0.0) or 0.0)
                dist = float(s.get("distance", 0.0) or 0.0)
                if "RUN" in stype:
                    run_dur_s += dur
                    run_dist_m += dist
                    found_splits = True
                elif "WALK" in stype:
                    walk_dur_s += dur
                    walk_dist_m += dist
                    found_splits = True

            if found_splits and (run_dur_s > 0 or walk_dur_s > 0):
                res["run_duration_min"] = round(run_dur_s / 60.0, 1)
                res["run_distance_km"] = round(run_dist_m / 1000.0, 2)
                if run_dur_s > 0 and run_dist_m > 0:
                    p_dec = (1000.0 / (run_dist_m / run_dur_s)) / 60.0
                    res["run_pace_min_km"] = round(p_dec, 2)
                    res["run_pace_str"] = format_pace(p_dec)

                res["walk_duration_min"] = round(walk_dur_s / 60.0, 1)
                res["walk_distance_km"] = round(walk_dist_m / 1000.0, 2)
                if walk_dur_s > 0 and walk_dist_m > 0:
                    p_dec = (1000.0 / (walk_dist_m / walk_dur_s)) / 60.0
                    res["walk_pace_min_km"] = round(p_dec, 2)
                    res["walk_pace_str"] = format_pace(p_dec)
                return res, typed_splits_raw

    # 2. Try typed_splits endpoint
    try:
        typed_splits_raw = client.get_activity_typed_splits(act_id)
        splits = typed_splits_raw.get("splits", []) if isinstance(typed_splits_raw, dict) else []

        run_dur_s, run_dist_m = 0.0, 0.0
        walk_dur_s, walk_dist_m = 0.0, 0.0
        stand_dur_s = 0.0
        found_splits = False

        for s in splits:
            stype = str(s.get("type") or s.get("splitType") or s.get("typeKey") or "").upper()
            dur = float(s.get("duration", 0.0) or 0.0)
            dist = float(s.get("distance", 0.0) or 0.0)
            if "RUN" in stype:
                run_dur_s += dur
                run_dist_m += dist
                found_splits = True
            elif "WALK" in stype:
                walk_dur_s += dur
                walk_dist_m += dist
                found_splits = True
            elif "STAND" in stype or "IDLE" in stype:
                stand_dur_s += dur

        if found_splits and (run_dur_s > 0 or walk_dur_s > 0):
            res["run_duration_min"] = round(run_dur_s / 60.0, 1)
            res["run_distance_km"] = round(run_dist_m / 1000.0, 2)
            if run_dur_s > 0 and run_dist_m > 0:
                p_dec = (1000.0 / (run_dist_m / run_dur_s)) / 60.0
                res["run_pace_min_km"] = round(p_dec, 2)
                res["run_pace_str"] = format_pace(p_dec)

            res["walk_duration_min"] = round(walk_dur_s / 60.0, 1)
            res["walk_distance_km"] = round(walk_dist_m / 1000.0, 2)
            if walk_dur_s > 0 and walk_dist_m > 0:
                p_dec = (1000.0 / (walk_dist_m / walk_dur_s)) / 60.0
                res["walk_pace_min_km"] = round(p_dec, 2)
                res["walk_pace_str"] = format_pace(p_dec)

            res["idle_duration_min"] = round(stand_dur_s / 60.0, 1)
            return res, typed_splits_raw
    except Exception as e:
        print(f"  Warning: Typed splits API failed for {act_id}: {e}")

    # 3. Fallback to second-by-second trackpoint thresholding (< 7.0 km/h or speed_mps < 1.94 m/s = Walk)
    if act_tps:
        tp_df = pd.DataFrame(act_tps)
        if not tp_df.empty:
            cad = tp_df.get("cadence_spm", pd.Series(dtype=float)).fillna(0)
            speed = tp_df.get("speed_mps", pd.Series(dtype=float)).fillna(0)

            walk_mask = (cad > 0) & (cad < 120) | ((speed > 0) & (speed < 1.94))
            run_mask = (cad >= 120) | (speed >= 1.94)

            tp_run = tp_df[run_mask]
            tp_walk = tp_df[walk_mask]

            run_sec = len(tp_run) * 2
            walk_sec = len(tp_walk) * 2

            run_dist_m = tp_run["speed_mps"].sum() * 2
            walk_dist_m = tp_walk["speed_mps"].sum() * 2

            run_spd_avg = tp_run["speed_mps"].mean() if len(tp_run) > 0 else 0
            walk_spd_avg = tp_walk["speed_mps"].mean() if len(tp_walk) > 0 else 0

            res["run_duration_min"] = round(run_sec / 60.0, 1)
            res["run_distance_km"] = round(run_dist_m / 1000.0, 2)
            if run_spd_avg > 0:
                p_dec = (1000.0 / run_spd_avg) / 60.0
                res["run_pace_min_km"] = round(p_dec, 2)
                res["run_pace_str"] = format_pace(p_dec)

            res["walk_duration_min"] = round(walk_sec / 60.0, 1)
            res["walk_distance_km"] = round(walk_dist_m / 1000.0, 2)
            if walk_spd_avg > 0:
                p_dec = (1000.0 / walk_spd_avg) / 60.0
                res["walk_pace_min_km"] = round(p_dec, 2)
                res["walk_pace_str"] = format_pace(p_dec)

    return res, typed_splits_raw


def extract_trackpoints_and_details(client, summary_df):
    """Extract raw trackpoints, native HR zones, native typed splits, and dump full raw JSON for each activity."""
    all_trackpoints = []
    enriched_summary = []

    for idx, row in summary_df.iterrows():
        act_id = row["activity_id"]
        start_time = row["start_time"]
        act_name = row["activity_name"]

        print(f"[{idx+1}/{len(summary_df)}] Ingesting native Garmin API data for activity {act_id} ({act_name} - {start_time})...")

        # 1. Full Summary Endpoint
        full_summary_raw = None
        try:
            full_summary_raw = client.get_activity(act_id)
        except Exception:
            pass

        # 2. Activity Detail Trackpoints
        act_tps = []
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

        # 3. Direct Native HR Zone Ingestion (with trackpoint fallback)
        hr_z_dict, hr_zones_raw = extract_native_hr_zones(client, act_id, act_tps)

        # 4. Direct Native Run/Walk Typed Splits Ingestion (with multi-schema fallback)
        segment_dict, typed_splits_raw = extract_native_typed_splits(client, act_id, full_summary_raw, act_tps)

        # 5. Fetch Splits & Weather
        splits_raw = None
        weather_raw = None
        try:
            splits_raw = client.get_activity_splits(act_id)
        except Exception:
            pass

        try:
            weather_raw = client.get_activity_weather(act_id)
        except Exception:
            pass

        # Save Official Raw Activity JSON payload to data/raw_activity_{act_id}.json
        try:
            raw_payload = {
                "activity_id": act_id,
                "summary": full_summary_raw,
                "splits": splits_raw,
                "typed_splits": typed_splits_raw,
                "weather": weather_raw,
                "hr_zones": hr_zones_raw,
                "details_sample": act_tps[::5] if len(act_tps) > 100 else act_tps
            }
            raw_json_path = DATA_DIR / f"raw_activity_{act_id}.json"
            with open(raw_json_path, "w") as f:
                json.dump(raw_payload, f, indent=2, default=str)
            print(f"  Saved official raw JSON payload to {raw_json_path}")
        except Exception as e:
            print(f"  Warning: Failed saving raw JSON for {act_id}: {e}")

        # Merge summary record
        row_dict = row.to_dict()
        row_dict.update(hr_z_dict)
        row_dict.update(segment_dict)
        enriched_summary.append(row_dict)

    return pd.DataFrame(enriched_summary), pd.DataFrame(all_trackpoints)


def fetch_garmin_data(force_resync=True):
    """Main execution function with incremental sync capability for Garmin Connect runs."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    summary_file = DATA_DIR / "runs_summary.csv"
    trackpoints_file = DATA_DIR / "raw_trackpoints.csv"

    existing_summary_df = pd.DataFrame()
    existing_act_ids = set()

    if summary_file.exists() and not force_resync:
        try:
            existing_summary_df = pd.read_csv(summary_file)
            if "activity_id" in existing_summary_df.columns:
                existing_act_ids = set(existing_summary_df["activity_id"].astype(str))
        except Exception:
            pass

    client = get_garmin_client()

    print("Fetching activities list from Garmin Connect...")
    activities = client.get_activities(0, 100)
    print(f"Retrieved {len(activities)} total activities.")

    raw_summary_df = parse_runs(activities)
    print(f"Filtered {len(raw_summary_df)} running activities.")

    if raw_summary_df.empty:
        print("No running activities found.")
        return False

    # Incremental sync filter: only fetch new activities unless force_resync=True
    if existing_act_ids and not force_resync:
        summary_to_process = raw_summary_df[~raw_summary_df["activity_id"].astype(str).isin(existing_act_ids)]
        if summary_to_process.empty:
            print("All activities are up to date! No new runs to fetch.")
            return True
        print(f"Incremental sync: Found {len(summary_to_process)} new activities to fetch.")
    else:
        summary_to_process = raw_summary_df

    print(f"\nIngesting native Garmin HR zones & typed splits for {len(summary_to_process)} activities...")
    new_summary_df, new_trackpoints_df = extract_trackpoints_and_details(client, summary_to_process)

    # Merge with existing summary if incremental
    if not existing_summary_df.empty and not force_resync:
        combined_summary_df = pd.concat([new_summary_df, existing_summary_df], ignore_index=True)
        combined_summary_df = combined_summary_df.drop_duplicates(subset=["activity_id"], keep="first")
    else:
        combined_summary_df = new_summary_df

    combined_summary_df.to_csv(summary_file, index=False)
    print(f"Saved {len(combined_summary_df)} activity summaries to {summary_file}")

    # Merge trackpoints if incremental
    if trackpoints_file.exists() and not force_resync and not new_trackpoints_df.empty:
        existing_tp_df = pd.read_csv(trackpoints_file)
        combined_tp_df = pd.concat([new_trackpoints_df, existing_tp_df], ignore_index=True)
        combined_tp_df = combined_tp_df.drop_duplicates(subset=["activity_id", "timestamp"], keep="first")
    else:
        combined_tp_df = new_trackpoints_df

    combined_tp_df.to_csv(trackpoints_file, index=False)
    print(f"Saved {len(combined_tp_df)} raw trackpoints to {trackpoints_file}")

    print("\nExtraction Summary:")
    print(f"Total Runs Synced: {len(combined_summary_df)}")
    print(f"Total Trackpoints Synced: {len(combined_tp_df)}")
    return True


if __name__ == "__main__":
    fetch_garmin_data(force_resync=True)
