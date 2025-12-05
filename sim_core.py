import json
from datetime import datetime
from typing import List, Dict, Any, Optional

import pandas as pd


# Files
CLEAN_FLIGHTS_FILE = "aa_flights_clean.json"     # summary list, one row per Key
RAW_AA_FILE = "Clean_AA_FlightData.txt"         # full AA ETD history

# Cached raw AA dataframe
_RAW_AA_DF: Optional[pd.DataFrame] = None


# ---------------- BASIC HELPERS ----------------


def format_dt(dt_obj: datetime) -> str:
    """Format datetime nicely for display."""
    return dt_obj.strftime("%Y-%m-%d %H:%M")


def load_clean_flights(filename: str = CLEAN_FLIGHTS_FILE) -> List[Dict[str, Any]]:
    """
    Load the summarized flights list (one row per Key) that the UI uses
    to populate the flight selector.
    """
    with open(filename, "r", encoding="utf-8") as f:
        flights = json.load(f)
    return flights


def _load_raw_aa_data() -> pd.DataFrame:
    """
    Lazily load the full AA ETD dataset and precompute datetime columns.

    This is where we get the true ETD history:
    - multiple rows per Key
    - each with its own EST_LEG_DEP_TMS and LAST_UPDT_TMS_LCL
    """
    global _RAW_AA_DF
    if _RAW_AA_DF is not None:
        return _RAW_AA_DF

    df = pd.read_csv(
        RAW_AA_FILE,
        dtype=str,
        on_bad_lines="skip",
    )

    # Only keep rows with a Key and scheduled departure time
    df = df[df["Key"].notna()].copy()
    df = df[df["SCHD_LEG_DEP_TMS"].notna()].copy()

    # Parse datetimes
    df["LAST_UPDT_TMS_LCL_dt"] = pd.to_datetime(
        df["LAST_UPDT_TMS_LCL"], errors="coerce"
    )
    df["SCHD_LEG_DEP_TMS_dt"] = pd.to_datetime(
        df["SCHD_LEG_DEP_TMS"], errors="coerce"
    )
    df["EST_LEG_DEP_TMS_dt"] = pd.to_datetime(
        df["EST_LEG_DEP_TMS"], errors="coerce"
    )
    df["ACTL_LEG_DEP_TMS_dt"] = pd.to_datetime(
        df["ACTL_LEG_DEP_TMS"], errors="coerce"
    )

    _RAW_AA_DF = df
    return _RAW_AA_DF


# ---------------- CONFIDENCE & MESSAGING ----------------


def confidence_bucket(score: int) -> str:
    """
    Map numeric confidence scores to buckets.

    - HIGH:    70 - 100
    - MEDIUM:  50 - 69
    - LOW:     30 - 49
    - VERY LOW: 0 - 29
    """
    if score >= 70:
        return "HIGH"
    if score >= 50:
        return "MEDIUM"
    if score >= 30:
        return "LOW"
    return "VERY LOW"


def explain_cause(cause_tag: str) -> str:
    """Map internal cause tags to passenger-friendly text."""
    if cause_tag == "late_inbound":
        return (
            "The aircraft operating your flight is arriving later than scheduled "
            "from its previous flight."
        )
    if cause_tag == "weather":
        return "Weather conditions in the area are causing delays to departures."
    if cause_tag == "turn_delay":
        return (
            "Ground preparations such as cleaning, fueling, or baggage loading "
            "are taking longer than expected."
        )
    if cause_tag == "early":
        return (
            "Ground and air operations are running smoothly, allowing for an "
            "on-time or slightly early departure."
        )
    return "Operational adjustments are being made before departure."


def safe_window_message(minutes_until_etd: int, confidence: int) -> str:
    """Generate a simple safe window message for passengers."""
    if confidence >= 80 and minutes_until_etd > 25:
        return (
            "You likely have about 15–25 minutes before boarding begins. "
            "It is safe to briefly explore nearby options in the terminal."
        )
    if confidence >= 60 and minutes_until_etd > 10:
        return (
            "You likely have roughly 10–15 minutes before boarding begins. "
            "Please stay in the gate area."
        )
    if minutes_until_etd <= 10:
        return (
            "Boarding may begin soon. Please remain near the gate and watch "
            "for announcements."
        )
    return (
        "Conditions are changing. We recommend staying close to the gate and "
        "checking for updates regularly."
    )


def _infer_cause_tag(est_delay_min: int) -> str:
    """
    Simple cause inference based on magnitude/sign of delay.
    Demo-only heuristic.
    """
    if est_delay_min < -5:
        return "early"
    if est_delay_min <= 5:
        return "turn_delay"
    if est_delay_min < 30:
        return "late_inbound"
    return "weather"


def compute_confidence(
    minutes_before_sched: int,
    est_delay_min: int,
    num_changes: int,
    error_to_actual_min: Optional[int],
    stability_change_min: Optional[int],
) -> int:
    """
    Confidence logic driven by real AA ETD history.

    Factors:
    - How close we are to scheduled departure.
    - How accurate ETD is vs actual departure (if known).
    - How big the last ETD jump was.
    - How many ETD changes so far.
    - Size of delay.
    """
    score = 50

    # Lead-time effect: closer to scheduled → we "should" know more.
    if minutes_before_sched >= 120:
        score += 0
    elif minutes_before_sched >= 60:
        score += 5
    elif minutes_before_sched >= 30:
        score += 10
    elif minutes_before_sched >= 0:
        score += 15
    else:
        # Updates after scheduled departure (e.g., at gate) should be very confident.
        score += 20

    # Accuracy vs actual departure (retrospective).
    if error_to_actual_min is not None:
        if error_to_actual_min <= 5:
            score += 25
        elif error_to_actual_min <= 10:
            score += 15
        elif error_to_actual_min <= 20:
            score += 5
        else:
            score -= 10

    # Last ETD change size.
    if stability_change_min is not None:
        if stability_change_min <= 5:
            score += 10
        elif stability_change_min > 20:
            score -= 10

    # Penalize many ETD changes (beyond the first).
    if num_changes > 1:
        score -= (num_changes - 1) * 3

    # Very large delays tend to be less predictable.
    if est_delay_min > 30:
        score -= 5

    # Clamp to [0, 100]
    return max(0, min(100, score))


# ---------------- TIMELINE USING REAL AA HISTORY ----------------


def generate_timeline_for_flight(flight: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Build an ETD timeline for one flight using real AA ETD history.

    For each Key:
      - Pull all rows from Clean_AA_FlightData.txt
      - Sort by LAST_UPDT_TMS_LCL (chronological AA updates)
      - For each snapshot, compute:
          - minutes_before_sched
          - estimated_delay (EST - SCHD)
          - error_to_actual (if ACTL exists)
          - ETD changes so far and last-change magnitude
          - confidence, bucket, cause, passenger message
    """
    key = flight.get("key")
    raw_df = _load_raw_aa_data()

    if not key:
        return _fallback_single_snapshot_timeline(flight)

    g = raw_df[raw_df["Key"] == key].copy()
    if g.empty:
        return _fallback_single_snapshot_timeline(flight)

    # Need valid times
    g = g[
        g["LAST_UPDT_TMS_LCL_dt"].notna()
        & g["SCHD_LEG_DEP_TMS_dt"].notna()
        & g["EST_LEG_DEP_TMS_dt"].notna()
    ].copy()

    if g.empty:
        return _fallback_single_snapshot_timeline(flight)

    # Sort by when AA updated the ETD
    g = g.sort_values("LAST_UPDT_TMS_LCL_dt")

    timeline: List[Dict[str, Any]] = []
    prev_est_dt: Optional[datetime] = None
    num_changes = 0

    for _, row in g.iterrows():
        snapshot_time = row["LAST_UPDT_TMS_LCL_dt"]
        sched_dt = row["SCHD_LEG_DEP_TMS_dt"]
        est_dt = row["EST_LEG_DEP_TMS_dt"]
        act_dt = row["ACTL_LEG_DEP_TMS_dt"]

        if pd.isna(snapshot_time) or pd.isna(sched_dt) or pd.isna(est_dt):
            continue

        # Minutes before scheduled departure (can be negative if after sched)
        minutes_before_sched = int((sched_dt - snapshot_time).total_seconds() // 60)

        # Estimated delay relative to schedule
        est_delay_min = int((est_dt - sched_dt).total_seconds() // 60)

        # Track ETD changes and magnitude of last change
        stability_change_min: Optional[int] = None
        if prev_est_dt is None:
            num_changes = 1
        else:
            if est_dt != prev_est_dt:
                num_changes += 1
                stability_change_min = int(
                    abs((est_dt - prev_est_dt).total_seconds()) // 60
                )
            else:
                stability_change_min = 0

        prev_est_dt = est_dt

        # Retrospective error to actual departure
        error_to_actual_min: Optional[int] = None
        if not pd.isna(act_dt):
            error_to_actual_min = int(
                abs((est_dt - act_dt).total_seconds()) // 60
            )

        # Minutes from snapshot to current ETD
        minutes_until_etd = int((est_dt - snapshot_time).total_seconds() // 60)

        # Compute confidence
        conf_score = compute_confidence(
            minutes_before_sched=minutes_before_sched,
            est_delay_min=est_delay_min,
            num_changes=num_changes,
            error_to_actual_min=error_to_actual_min,
            stability_change_min=stability_change_min,
        )
        bucket = confidence_bucket(conf_score)

        cause_tag = _infer_cause_tag(est_delay_min)
        cause_text = explain_cause(cause_tag)
        safe_msg = safe_window_message(minutes_until_etd, conf_score)

        timeline.append(
            {
                "snapshot_time": snapshot_time,
                "minutes_before_sched": minutes_before_sched,
                "predicted_etd": est_dt,
                "estimated_delay": est_delay_min,
                "confidence": conf_score,
                "confidence_bucket": bucket,
                "cause_tag": cause_tag,
                "cause_text": cause_text,
                "safe_window_message": safe_msg,
                "num_changes": num_changes,
            }
        )

    if not timeline:
        return _fallback_single_snapshot_timeline(flight)

    return timeline


def _fallback_single_snapshot_timeline(flight: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    If we cannot build a real timeline (missing Key or raw data),
    generate a simple one-step snapshot using the summarized flight record.
    """
    dep_sched_str = flight.get("dep_scheduled")
    dep_est_str = flight.get("dep_estimated") or dep_sched_str
    dep_act_str = flight.get("dep_actual") or dep_est_str

    try:
        sched_dt = datetime.fromisoformat(dep_sched_str)
    except Exception:
        sched_dt = datetime.now()
    try:
        est_dt = datetime.fromisoformat(dep_est_str)
    except Exception:
        est_dt = sched_dt
    try:
        act_dt = datetime.fromisoformat(dep_act_str)
    except Exception:
        act_dt = None

    snapshot_time = sched_dt
    minutes_before_sched = 0
    est_delay_min = int((est_dt - sched_dt).total_seconds() // 60)

    error_to_actual_min: Optional[int] = None
    if act_dt is not None:
        error_to_actual_min = int(
            abs((est_dt - act_dt).total_seconds()) // 60
        )

    conf_score = compute_confidence(
        minutes_before_sched=minutes_before_sched,
        est_delay_min=est_delay_min,
        num_changes=1,
        error_to_actual_min=error_to_actual_min,
        stability_change_min=0,
    )
    bucket = confidence_bucket(conf_score)
    minutes_until_etd = int((est_dt - snapshot_time).total_seconds() // 60)

    cause_tag = _infer_cause_tag(est_delay_min)
    cause_text = explain_cause(cause_tag)
    safe_msg = safe_window_message(minutes_until_etd, conf_score)

    return [
        {
            "snapshot_time": snapshot_time,
            "minutes_before_sched": minutes_before_sched,
            "predicted_etd": est_dt,
            "estimated_delay": est_delay_min,
            "confidence": conf_score,
            "confidence_bucket": bucket,
            "cause_tag": cause_tag,
            "cause_text": cause_text,
            "safe_window_message": safe_msg,
            "num_changes": 1,
        }
    ]


# ---------------- CLI DEMO ----------------


def demo_one_flight(index: int = 0) -> None:
    """
    Print a timeline simulation for a single flight to the terminal,
    driven by real AA ETD history.
    """
    flights = load_clean_flights()
    if not flights:
        print("No flights found in aa_flights_clean.json")
        return

    if index < 0 or index >= len(flights):
        print(f"Index {index} out of range. There are {len(flights)} flights.")
        return

    flight = flights[index]
    print("=== Flight Selected for Simulation ===")
    print(f"Key: {flight.get('key')}")
    print(f"Flight: {flight.get('flight_iata')}  (#{flight.get('flight_number')})")
    print(f"Airline: {flight.get('airline')}")
    print(
        f"Route: {flight.get('dep_iata', '---')} → {flight.get('arr_iata', '---')}"
    )
    print(f"Scheduled Departure: {flight.get('dep_scheduled')}")
    print(f"Status (from AA data): {flight.get('status')}")
    print("======================================\n")

    timeline = generate_timeline_for_flight(flight)

    print("=== ETD Simulation Timeline (Real AA History) ===")
    for step in timeline:
        print(f"\n--- Snapshot at T-{step['minutes_before_sched']} minutes ---")
        print(f"Snapshot time:        {format_dt(step['snapshot_time'])}")
        print(f"Predicted ETD:        {format_dt(step['predicted_etd'])}")
        print(f"Estimated delay:      {step['estimated_delay']} minutes")
        print(
            f"Confidence score:     {step['confidence']} "
            f"({step['confidence_bucket']})"
        )
        print(f"ETD changes so far:   {step['num_changes']}")
        print(f"Delay explanation:    {step['cause_text']}")
        print(f"Passenger message:    {step['safe_window_message']}")
    print("\n=== End of Simulation ===")


if __name__ == "__main__":
    demo_one_flight(index=0)