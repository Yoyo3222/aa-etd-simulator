import json
from datetime import datetime
from typing import List, Dict, Any, Optional

import pandas as pd


# ---------------- FILE PATHS ----------------

CLEAN_FLIGHTS_FILE = "aa_flights_clean.json"
RAW_AA_FILE = "Clean_AA_FlightData.txt"

_RAW_AA_DF: Optional[pd.DataFrame] = None


# ---------------- GENERIC HELPERS ----------------


def format_dt(dt_obj: datetime) -> str:
    """Format datetime as YYYY-MM-DD HH:MM for the ops timeline."""
    return dt_obj.strftime("%Y-%m-%d %H:%M")


def load_clean_flights(filename: str = CLEAN_FLIGHTS_FILE) -> List[Dict[str, Any]]:
    """Load the summarized flights list used by the UI."""
    with open(filename, "r", encoding="utf-8") as f:
        flights = json.load(f)
    return flights


def _load_raw_aa_data() -> pd.DataFrame:
    """
    Lazily load the full AA ETD history and parse the timestamps.
    This is the source of truth for ETD updates.
    """
    global _RAW_AA_DF
    if _RAW_AA_DF is not None:
        return _RAW_AA_DF

    df = pd.read_csv(
        RAW_AA_FILE,
        dtype=str,
        on_bad_lines="skip",
    )

    df = df[df["Key"].notna()].copy()
    df = df[df["SCHD_LEG_DEP_TMS"].notna()].copy()

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


# ---------------- CONFIDENCE & BUCKETS ----------------


def confidence_bucket(score: int) -> str:
    """
    Map a numeric confidence score into one of the four buckets
    that the UI actually shows.
    """
    if score >= 75:
        return "HIGH"
    if score >= 55:
        return "MEDIUM"
    if score >= 35:
        return "LOW"
    return "VERY LOW"


def compute_confidence(
    minutes_before_sched: int,
    est_delay_min: int,
    num_changes: int,
    error_to_actual_min: Optional[int],
    stability_change_min: Optional[int],
    max_change_seen: int,
) -> int:
    """
    Compute an ETD confidence score based on operational signals.

    FIXED: Added max_change_seen to detect volatility patterns
    FIXED: Better scoring logic for proximity and stability
    """
    score = 50  # neutral baseline

    # 1) Proximity to scheduled departure (closer = more accurate)
    if minutes_before_sched >= 180:  # 3+ hours out
        score += 5
    elif minutes_before_sched >= 120:  # 2-3 hours
        score += 10
    elif minutes_before_sched >= 60:  # 1-2 hours
        score += 15
    elif minutes_before_sched >= 30:  # 30-60 min
        score += 20
    elif minutes_before_sched >= 0:  # 0-30 min before sched
        score += 25
    else:  # Past scheduled time
        score += 30

    # 2) Historical accuracy vs actual departure (when known)
    if error_to_actual_min is not None:
        if error_to_actual_min <= 3:
            score += 25
        elif error_to_actual_min <= 8:
            score += 15
        elif error_to_actual_min <= 15:
            score += 5
        elif error_to_actual_min <= 30:
            score -= 5
        else:
            score -= 15

    # 3) Stability - recent change magnitude
    if stability_change_min is not None:
        if stability_change_min == 0:  # No change
            score += 8
        elif stability_change_min <= 5:
            score += 5
        elif stability_change_min <= 15:
            score += 0
        elif stability_change_min <= 30:
            score -= 8
        else:  # Big recent jump
            score -= 15

    # 4) Overall volatility - largest change seen
    if max_change_seen <= 5:
        score += 5
    elif max_change_seen <= 15:
        score += 0
    elif max_change_seen <= 30:
        score -= 5
    else:
        score -= 10

    # 5) Number of changes (too many = unstable)
    if num_changes <= 2:
        score += 5
    elif num_changes <= 4:
        score += 0
    elif num_changes <= 6:
        score -= 5
    else:
        score -= (num_changes - 6) * 3

    # 6) Very long delays are inherently unpredictable
    if est_delay_min >= 120:
        score -= 12
    elif est_delay_min >= 90:
        score -= 8
    elif est_delay_min >= 60:
        score -= 5

    return max(0, min(100, score))


# ---------------- DELAY DRIVERS ----------------


def _infer_cause_tag(
    est_delay_min: int,
    num_changes: int,
    max_change_seen: int,
    changes_list: List[int],
) -> str:
    """
    Map delay patterns into one of four driver labels.

    FIXED: Now considers change patterns, not just magnitude
    - On Time: minimal delay and stable
    - Turn Delay: small delay with gradual changes
    - Late Inbound: moderate delay, often with one significant jump
    - Weather: large delay or highly volatile pattern
    """

    # ON TIME: very small delay and stable
    if abs(est_delay_min) <= 10 and num_changes <= 3 and max_change_seen <= 10:
        return "On Time"

    # WEATHER: Very large delays or highly volatile patterns
    if est_delay_min >= 90 or max_change_seen >= 45:
        return "Weather"
    
    # Check for sudden large jump pattern (typical of weather/ATC)
    if len(changes_list) > 0:
        big_jumps = sum(1 for c in changes_list if c >= 30)
        if big_jumps >= 1 and est_delay_min >= 45:
            return "Weather"

    # LATE INBOUND: moderate delay (30-90 min range)
    if 30 <= est_delay_min < 90:
        # If there was one significant change but then stabilized
        if num_changes <= 5:
            return "Late Inbound"
        # Many small changes suggests turn issues
        if max_change_seen <= 20:
            return "Turn Delay"
        return "Late Inbound"

    # TURN DELAY: small to moderate delay with gradual changes
    if est_delay_min < 30:
        return "Turn Delay"

    # Default fallback
    return "Turn Delay"


def explain_cause(cause_tag: str) -> str:
    """Passenger-facing explanation for each delay driver."""
    if cause_tag == "On Time":
        return (
            "Your flight is operating on or very close to schedule. Ground and air "
            "operations are running smoothly with only minor adjustments."
        )
    if cause_tag == "Turn Delay":
        return (
            "Ground operations like cleaning, fueling, catering, or baggage loading "
            "are taking longer than planned. These are routine adjustments that happen "
            "during the turnaround between flights."
        )
    if cause_tag == "Late Inbound":
        return (
            "The aircraft for your flight is running behind schedule from its previous "
            "flight. Once it arrives and completes its turnaround, your flight will depart."
        )
    if cause_tag == "Weather":
        return (
            "Weather conditions, air traffic control restrictions, or broader airspace "
            "issues are affecting flights in the area. These delays help ensure safe operations."
        )
    return "Operational adjustments are being made before departure."


# ---------------- PASSENGER SAFE WINDOW ----------------


def safe_window_message(minutes_until_etd: int, bucket: str, est_delay_min: int) -> str:
    """
    FIXED: Passenger safe-window messaging based on:
    - minutes_until_etd: time remaining until current ETD estimate
    - bucket: confidence level
    - est_delay_min: helps contextualize the situation
    
    Key fix: This now properly considers TIME REMAINING, not historical time
    """

    # Already at or past the ETD
    if minutes_until_etd <= 0:
        return (
            "⚠️ Your flight's departure time has arrived or passed. Please stay at the "
            "gate and listen for boarding announcements. Check with gate agents if you "
            "have questions about the current status."
        )

    t = minutes_until_etd

    # ---- IMMINENT: 0-15 minutes ----
    if t < 15:
        if bucket in ("HIGH", "MEDIUM"):
            return (
                "🚨 Boarding is happening now or will begin within minutes. Stay at the "
                "gate with your boarding pass ready. Do not leave the area."
            )
        return (
            "🚨 Your flight may board at any moment, though timing is still adjusting. "
            "Stay at the gate and monitor announcements closely."
        )

    # ---- VERY SOON: 15-30 minutes ----
    if 15 <= t < 30:
        if bucket == "HIGH":
            return (
                "✈️ Boarding should begin in 10-20 minutes. Stay in the gate area and "
                "have your boarding pass ready."
            )
        if bucket == "MEDIUM":
            return (
                "✈️ Boarding may begin in 10-25 minutes. Stay near the gate and watch "
                "for your boarding group to be called."
            )
        return (
            "⚠️ Boarding could start soon, but timing is still changing. Please remain "
            "at the gate and watch the displays."
        )

    # ---- APPROACHING: 30-60 minutes ----
    if 30 <= t < 60:
        if bucket == "HIGH":
            return (
                "✅ You have 30-45 minutes before boarding typically begins. Quick restroom "
                "trips are fine, but stay in the gate area and keep checking displays."
            )
        if bucket == "MEDIUM":
            return (
                "✅ You likely have 20-40 minutes before boarding. Stay close to the gate "
                "area—quick trips are okay, but monitor screens frequently."
            )
        return (
            "⚠️ You may have 20-40 minutes, but timing is shifting. Stay in the immediate "
            "gate area and check screens regularly."
        )

    # ---- MODERATE WINDOW: 60-90 minutes ----
    if 60 <= t < 90:
        if bucket == "HIGH":
            return (
                "✅ You have about 1-1.5 hours before departure. Safe to visit nearby shops "
                "or grab food, but stay in the same terminal and return to the gate area "
                "30-40 minutes before departure."
            )
        if bucket == "MEDIUM":
            return (
                "✅ You have roughly 1-1.5 hours. Brief trips to nearby food/shops are okay, "
                "but check screens regularly and return to the gate area 30 minutes before "
                "the current departure time."
            )
        return (
            "⚠️ You may have 1-1.5 hours, but the schedule keeps changing. Stay in your "
            "terminal, avoid going far, and check for updates frequently."
        )

    # ---- GOOD WINDOW: 90-150 minutes ----
    if 90 <= t < 150:
        if bucket == "HIGH":
            return (
                "✅ You have 1.5-2.5 hours before departure. Safe to explore the terminal, "
                "get food, or shop. Return to your gate area about 45 minutes before departure "
                "and check screens periodically."
            )
        if bucket == "MEDIUM":
            return (
                "✅ You have roughly 1.5-2.5 hours. You can explore the terminal or grab a meal, "
                "but check the app or airport screens every 20-30 minutes for updates."
            )
        return (
            "⚠️ You may have 1.5-2+ hours, but timing has been volatile. It's okay to move "
            "around the terminal, but monitor screens often and avoid leaving your terminal."
        )

    # ---- EXTENDED: 150+ minutes (2.5+ hours) ----
    if bucket == "HIGH":
        return (
            "✅ You have 2.5+ hours before departure and the timing looks stable. Safe to "
            "explore the airport, but check the app or screens every 30-45 minutes and "
            "plan to return to your gate about 45-60 minutes before departure."
        )
    if bucket == "MEDIUM":
        return (
            "✅ You have 2.5+ hours before departure. You can explore the airport, but "
            "check for updates regularly—we recommend every 30-45 minutes via app or screens."
        )
    return (
        "⚠️ You have 2+ hours before the current departure time, but the schedule has been "
        "changing. You can move around the airport, but check for updates frequently—at "
        "least every 20-30 minutes—and stay alert for sudden changes."
    )


# ---------------- TIMELINE CONSTRUCTION ----------------


def generate_timeline_for_flight(flight: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Build an ETD timeline for one flight using real AA ETD history.

    FIXED: Now properly tracks change patterns and volatility
    """
    key = flight.get("key")
    raw_df = _load_raw_aa_data()

    if not key:
        return _fallback_single_snapshot_timeline(flight)

    g = raw_df[raw_df["Key"] == key].copy()
    if g.empty:
        return _fallback_single_snapshot_timeline(flight)

    g = g[
        g["LAST_UPDT_TMS_LCL_dt"].notna()
        & g["SCHD_LEG_DEP_TMS_dt"].notna()
        & g["EST_LEG_DEP_TMS_dt"].notna()
    ].copy()

    if g.empty:
        return _fallback_single_snapshot_timeline(flight)

    g = g.sort_values("LAST_UPDT_TMS_LCL_dt")

    timeline: List[Dict[str, Any]] = []
    prev_est_dt: Optional[datetime] = None
    num_changes = 0
    changes_list = []  # Track all change magnitudes
    max_change_seen = 0

    for _, row in g.iterrows():
        snapshot_time = row["LAST_UPDT_TMS_LCL_dt"]
        sched_dt = row["SCHD_LEG_DEP_TMS_dt"]
        est_dt = row["EST_LEG_DEP_TMS_dt"]
        act_dt = row["ACTL_LEG_DEP_TMS_dt"]

        if pd.isna(snapshot_time) or pd.isna(sched_dt) or pd.isna(est_dt):
            continue

        minutes_before_sched = int((sched_dt - snapshot_time).total_seconds() // 60)
        est_delay_min = int((est_dt - sched_dt).total_seconds() // 60)

        # Track ETD changes and magnitude
        stability_change_min: Optional[int] = None
        if prev_est_dt is None:
            num_changes = 1
        else:
            if est_dt != prev_est_dt:
                change_mag = int(abs((est_dt - prev_est_dt).total_seconds()) // 60)
                num_changes += 1
                stability_change_min = change_mag
                changes_list.append(change_mag)
                max_change_seen = max(max_change_seen, change_mag)
            else:
                stability_change_min = 0
        prev_est_dt = est_dt

        # Retrospective accuracy vs actual departure
        error_to_actual_min: Optional[int] = None
        if not pd.isna(act_dt):
            error_to_actual_min = int(abs((est_dt - act_dt).total_seconds()) // 60)

        # FIXED: Time from snapshot to ETD (for display purposes)
        minutes_until_etd = int((est_dt - snapshot_time).total_seconds() // 60)

        # Confidence
        conf_score = compute_confidence(
            minutes_before_sched=minutes_before_sched,
            est_delay_min=est_delay_min,
            num_changes=num_changes,
            error_to_actual_min=error_to_actual_min,
            stability_change_min=stability_change_min,
            max_change_seen=max_change_seen,
        )
        bucket = confidence_bucket(conf_score)

        # Delay driver (now with pattern analysis)
        cause_tag = _infer_cause_tag(
            est_delay_min, num_changes, max_change_seen, changes_list
        )
        cause_text = explain_cause(cause_tag)

        # Passenger safe window
        safe_msg = safe_window_message(minutes_until_etd, bucket, est_delay_min)

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
                "minutes_until_etd": minutes_until_etd,
                "max_change_seen": max_change_seen,
            }
        )

    if not timeline:
        return _fallback_single_snapshot_timeline(flight)

    return timeline


def _fallback_single_snapshot_timeline(flight: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Fallback when we don't have raw AA history for this Key.
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
        error_to_actual_min = int(abs((est_dt - act_dt).total_seconds()) // 60)

    conf_score = compute_confidence(
        minutes_before_sched=minutes_before_sched,
        est_delay_min=est_delay_min,
        num_changes=1,
        error_to_actual_min=error_to_actual_min,
        stability_change_min=0,
        max_change_seen=0,
    )
    bucket = confidence_bucket(conf_score)
    minutes_until_etd = int((est_dt - snapshot_time).total_seconds() // 60)

    cause_tag = _infer_cause_tag(est_delay_min, num_changes=1, max_change_seen=0, changes_list=[])
    cause_text = explain_cause(cause_tag)
    safe_msg = safe_window_message(minutes_until_etd, bucket, est_delay_min)

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
            "minutes_until_etd": minutes_until_etd,
            "max_change_seen": 0,
        }
    ]


# ---------------- CLI DEMO ----------------


def demo_one_flight(index: int = 0) -> None:
    """Terminal demo for debugging."""
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
    print(f"Route: {flight.get('dep_iata', '---')} → {flight.get('arr_iata', '---')}")
    print(f"Scheduled Departure: {flight.get('dep_scheduled')}")
    print(f"Status: {flight.get('status')}")
    print("======================================\n")

    timeline = generate_timeline_for_flight(flight)

    print("=== ETD Simulation Timeline ===")
    for i, step in enumerate(timeline):
        print(f"\n--- Update #{i+1}: T-{step['minutes_before_sched']} min ---")
        print(f"Snapshot time:     {format_dt(step['snapshot_time'])}")
        print(f"Predicted ETD:     {format_dt(step['predicted_etd'])}")
        print(f"Est. delay:        {step['estimated_delay']} min")
        print(f"Time until ETD:    {step['minutes_until_etd']} min")
        print(f"Confidence:        {step['confidence']} ({step['confidence_bucket']})")
        print(f"Changes so far:    {step['num_changes']}")
        print(f"Max change seen:   {step['max_change_seen']} min")
        print(f"Delay driver:      {step['cause_tag']}")
        print(f"Safe window:       {step['safe_window_message'][:80]}...")
    print("\n=== End of Simulation ===")


if __name__ == "__main__":
    demo_one_flight(index=0)