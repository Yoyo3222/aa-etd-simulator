import streamlit as st
from datetime import datetime

from sim_core import (
    load_clean_flights,
    generate_timeline_for_flight,
    format_dt,
)


# ---------------------- PAGE CONFIG & STYLES ----------------------


def inject_custom_css():
    """Inject custom CSS for AA-themed styling."""
    st.markdown(
        """
        <style>
        .aa-title {
            font-size: 2.2rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            background: linear-gradient(90deg, #d81f26 0%, #ffffff 40%, #0078d2 100%);
            -webkit-background-clip: text;
            color: transparent;
        }

        .aa-subtitle {
            font-size: 0.95rem;
            opacity: 0.85;
            max-width: 700px;
        }

        .aa-card-title-badge {
            display:inline-block;
            padding:0.50rem 1.4rem;
            border-radius:999px;
            border:1px solid rgba(255,255,255,0.12);
            background: radial-gradient(circle at top, #15294a 0%, #061021 70%);
            font-size:1.25rem;
            font-weight:700;
            text-transform:uppercase;
            letter-spacing:0.10em;
            opacity:0.9;
            margin-bottom:0.7rem;
        }

        .aa-flight-code {
            font-size: 1.7rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            margin-bottom: 0.3rem;
        }

        .aa-route {
            font-size: 1.0rem;
            font-weight: 500;
            margin-bottom: 0.4rem;
        }

        .aa-label {
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            opacity: 0.7;
        }

        .aa-value {
            font-size: 0.95rem;
            font-weight: 500;
        }

        .plane-slider .stSlider label {
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-size: 0.8rem;
        }

        .plane-slider .stSlider > div > div > div:nth-child(2) {
            background: linear-gradient(90deg, #d81f26 0%, #0078d2 100%);
        }

        .plane-slider .stSlider [data-baseweb="slider"] > div > div > div:nth-child(2) {
            box-shadow: 0 0 0 4px rgba(255, 255, 255, 0.15);
        }

        .aa-pill {
            display:inline-block;
            padding:0.45rem 1.1rem;
            border-radius:999px;
            font-weight:600;
            font-size:0.9rem;
        }

        .aa-table table {
            background-color: #07162f !important;
            border-radius: 12px;
            overflow: hidden;
        }
        .aa-table th, .aa-table td {
            font-size: 0.86rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_confidence_pill(bucket: str):
    """Render a colored confidence chip with only the bucket."""
    color_map = {
        "HIGH": "#2ecc71",
        "MEDIUM": "#f1c40f",
        "LOW": "#e67e22",
        "VERY LOW": "#e74c3c",
    }
    bg_color = color_map.get(bucket, "#95a5a6")

    pill_html = f"""
    <div class="aa-pill" style="
        background-color:{bg_color};
        color:#000000;
    ">
        ETD Confidence: {bucket.title()}
    </div>
    """
    st.markdown(pill_html, unsafe_allow_html=True)


# ---------------------- DATE / TIME HELPERS ----------------------


def parse_iso(dt_str: str):
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None


def fmt_12h(dt_obj: datetime) -> str:
    if dt_obj is None:
        return "N/A"
    return dt_obj.strftime("%I:%M %p").lstrip("0")


def fmt_mdy(dt_obj: datetime) -> str:
    if dt_obj is None:
        return "N/A"
    return dt_obj.strftime("%m/%d/%Y")


# ---------------------- MAIN APP ----------------------


def main():
    st.set_page_config(
        page_title="AA ETD Simulator",
        page_icon="✈️",
        layout="wide",
    )

    inject_custom_css()

    # Load flights
    flights = load_clean_flights()
    if not flights:
        st.error("No flights found in aa_flights_clean.json")
        return

    # ---------------- HEADER ----------------
    st.markdown(
        """
        <div>
            <div class="aa-title">American Airlines ETD Experience Simulator</div>
            <div class="aa-subtitle">
                Explore how departure time estimates, confidence levels, and passenger 
                messaging evolve throughout the pre-departure period using real AA flight data.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("")

    # ---------------- SIDEBAR: FLIGHT SELECTION ----------------
    st.sidebar.header("Flight Selection")

    num_flights = len(flights)
    st.sidebar.write(f"Total flights loaded: {num_flights}")

    flight_index = st.sidebar.number_input(
        "Flight index (use ↑ / ↓ keys)",
        min_value=0,
        max_value=max(0, num_flights - 1),
        value=0,
        step=1,
        help="Click here once, then use arrow keys to navigate flights.",
    )
    flight_index = int(flight_index)

    flight = flights[flight_index]

    sidebar_label = (
        f"{flight.get('flight_iata', 'N/A')} | "
        f"{flight.get('dep_iata', '---')} → {flight.get('arr_iata', '---')} | "
        f"{flight.get('dep_scheduled', '')}"
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("**Currently viewing:**")
    st.sidebar.markdown(f"`[{flight_index}]` {sidebar_label}")

    # Build timeline
    timeline = generate_timeline_for_flight(flight)
    if not timeline:
        st.error("No timeline data available for this flight.")
        return

    # FIXED: Slider now represents actual step/snapshot index (more intuitive)
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Timeline Position")

    num_snapshots = len(timeline)
    
    with st.sidebar.container():
        st.markdown(
            '<div style="font-size:0.85rem; opacity:0.8;">'
            "Move forward through time to see how ETD estimates evolved as departure approached."
            "</div>",
            unsafe_allow_html=True,
        )

        if num_snapshots == 1:
            snapshot_idx = 0
            st.markdown("*Only one snapshot available for this flight.*")
        else:
            st.markdown('<div class="plane-slider">', unsafe_allow_html=True)
            snapshot_idx = st.slider(
                f"Snapshot (1 to {num_snapshots})",
                min_value=0,
                max_value=num_snapshots - 1,
                value=0,
                step=1,
                help="Move slider right to advance through time toward departure"
            )
            st.markdown("</div>", unsafe_allow_html=True)
            
            # Show context
            current_step = timeline[snapshot_idx]
            st.sidebar.markdown(
                f"**T-{current_step['minutes_before_sched']} minutes** "
                f"({snapshot_idx + 1} of {num_snapshots} updates)"
            )

    current_step = timeline[snapshot_idx]

    # Parse times
    sched_dt = parse_iso(flight.get("dep_scheduled"))
    snapshot_dt = current_step["snapshot_time"]
    predicted_dt = current_step["predicted_etd"]

    # ---------------- TOP SUMMARY CARDS ----------------
    col_a, col_b, col_c = st.columns(3)

    # Selected Flight
    with col_a:
        st.markdown('<div class="aa-card">', unsafe_allow_html=True)
        st.markdown(
            '<div class="aa-card-title-badge">Selected Flight</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="aa-flight-code">{flight.get("flight_iata", "N/A")}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="aa-route">{flight.get("dep_iata", "---")} → {flight.get("arr_iata", "---")}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="aa-label">Airline</div><div class="aa-value">{flight.get("airline", "American Airlines")}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="aa-label" style="margin-top:0.4rem;">Final Status</div>'
            f'<div class="aa-value">{flight.get("status", "unknown")}</div>',
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    # Schedule & ETD
    with col_b:
        st.markdown('<div class="aa-card">', unsafe_allow_html=True)
        st.markdown(
            '<div class="aa-card-title-badge">Schedule &amp; ETD</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            f'<div class="aa-label">Scheduled Date</div>'
            f'<div class="aa-value">{fmt_mdy(sched_dt)}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="aa-label" style="margin-top:0.4rem;">Scheduled Departure</div>'
            f'<div class="aa-value">{fmt_12h(sched_dt)}</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            f'<div class="aa-label" style="margin-top:0.6rem;">Current Snapshot</div>'
            f'<div class="aa-value">T-{current_step["minutes_before_sched"]} minutes</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="aa-label" style="margin-top:0.25rem;">Snapshot Time</div>'
            f'<div class="aa-value">{fmt_12h(snapshot_dt)}</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            f'<div class="aa-label" style="margin-top:0.6rem;">Predicted ETD</div>'
            f'<div class="aa-value">{fmt_12h(predicted_dt)}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="aa-label" style="margin-top:0.25rem;">Estimated Delay</div>'
            f'<div class="aa-value">{current_step["estimated_delay"]} minutes</div>',
            unsafe_allow_html=True,
        )

        st.markdown("</div>", unsafe_allow_html=True)

    # ETD Confidence
    with col_c:
        st.markdown('<div class="aa-card">', unsafe_allow_html=True)
        st.markdown(
            '<div class="aa-card-title-badge">ETD Confidence</div>',
            unsafe_allow_html=True,
        )
        render_confidence_pill(current_step["confidence_bucket"])
        st.markdown(
            f'<div class="aa-label" style="margin-top:0.7rem;">ETD Updates So Far</div>'
            f'<div class="aa-value">{current_step["num_changes"]}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="aa-label" style="margin-top:0.4rem;">Largest Change</div>'
            f'<div class="aa-value">{current_step["max_change_seen"]} minutes</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="aa-label" style="margin-top:0.4rem;">Delay Category</div>'
            f'<div class="aa-value">{current_step["cause_tag"]}</div>',
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("")

    # ---------------- PASSENGER VIEW ----------------
    st.markdown("### 👤 Passenger Experience")
    st.markdown("*What a passenger would see at this point in time:*")
    st.markdown("")
    
    p_col1, p_col2 = st.columns(2)

    with p_col1:
        st.markdown('<div class="aa-card">', unsafe_allow_html=True)
        st.markdown(
            '<div class="aa-card-title-badge">Why is my flight delayed?</div>',
            unsafe_allow_html=True,
        )
        st.info(current_step["cause_text"])
        st.markdown("</div>", unsafe_allow_html=True)

    with p_col2:
        st.markdown('<div class="aa-card">', unsafe_allow_html=True)
        st.markdown(
            '<div class="aa-card-title-badge">What should I do?</div>',
            unsafe_allow_html=True,
        )
        st.success(current_step["safe_window_message"])
        st.markdown("</div>", unsafe_allow_html=True)

    # ---------------- OPS VIEW ----------------
    st.markdown("")
    st.markdown("### 👨‍✈️ Operations View")
    st.markdown(
        "This operational view shows how ETD evolved over time, helping gate staff "
        "understand reliability and communicate proactively with passengers."
    )
    st.markdown("")

    st.markdown('<div class="aa-card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="aa-card-title-badge">Operational Notes</div>',
        unsafe_allow_html=True,
    )
    
    st.write(
        "**Key Insights:**\n"
        f"- This flight had **{current_step['num_changes']}** ETD updates\n"
        f"- Largest single change: **{current_step['max_change_seen']}** minutes\n"
        f"- Current confidence: **{current_step['confidence_bucket']}** "
        f"(score: {current_step['confidence']})\n"
        f"- Delay driver: **{current_step['cause_tag']}**"
    )
    
    if current_step['confidence_bucket'] in ('LOW', 'VERY LOW'):
        st.warning(
            "⚠️ Low confidence suggests proactive passenger communication is recommended. "
            "Consider making announcements and updating gate displays frequently."
        )
    elif current_step['max_change_seen'] >= 30:
        st.warning(
            "⚠️ Large ETD changes detected. Monitor closely for additional changes and "
            "keep passengers informed."
        )
    
    st.markdown("</div>", unsafe_allow_html=True)

    # ---------------- FULL TIMELINE TABLE ----------------
    st.markdown("")
    st.subheader("📊 Complete ETD History (24-Hour Format)")
    st.markdown(
        "This table shows every ETD update AA published for this flight. "
        "Times use 24-hour format for operational clarity."
    )

    timeline_rows = []
    for i, step in enumerate(timeline):
        timeline_rows.append(
            {
                "Update #": i + 1,
                "T-minus (min)": step["minutes_before_sched"],
                "Snapshot Time": format_dt(step["snapshot_time"]),
                "Predicted ETD": format_dt(step["predicted_etd"]),
                "Delay (min)": step["estimated_delay"],
                "Conf Score": step["confidence"],
                "Conf Level": step["confidence_bucket"],
                "Changes": step["num_changes"],
                "Driver": step["cause_tag"],
            }
        )

    st.markdown('<div class="aa-table">', unsafe_allow_html=True)
    st.dataframe(timeline_rows, use_container_width=True, height=400)
    st.markdown("</div>", unsafe_allow_html=True)
    
    # Add summary stats at bottom
    st.markdown("---")
    stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
    with stat_col1:
        st.metric("Total Updates", len(timeline))
    with stat_col2:
        final_delay = timeline[-1]["estimated_delay"]
        st.metric("Final Delay", f"{final_delay} min")
    with stat_col3:
        max_change = max(s["max_change_seen"] for s in timeline)
        st.metric("Max Change", f"{max_change} min")
    with stat_col4:
        final_conf = timeline[-1]["confidence_bucket"]
        st.metric("Final Confidence", final_conf)


if __name__ == "__main__":
    main()