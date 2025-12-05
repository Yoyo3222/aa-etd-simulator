import streamlit as st
from datetime import datetime

from sim_core import (
    load_clean_flights,
    generate_timeline_for_flight,
    format_dt,  # 24h + date, used for ops timeline
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
    """Render a colored confidence chip with only the bucket (no numeric score)."""
    color_map = {
        "HIGH": "#2ecc71",      # green
        "MEDIUM": "#f1c40f",    # yellow
        "LOW": "#e67e22",       # orange
        "VERY LOW": "#e74c3c",  # red
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
        page_icon=None,
        layout="wide",
    )

    inject_custom_css()

    # Load flights from aa_flights_clean.json
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
                American Airlines simulator for passengers to see how departure time, confidence,
                and messaging evolve before takeoff, with an operations view built in.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("")

    # ---------------- SIDEBAR: FLIGHT SELECTION ----------------
    st.sidebar.header("Flight Selection")

    num_flights = len(flights)
    st.sidebar.write(f"Flights loaded: {num_flights}")

    # Keyboard-friendly selector: click once, then use up/down arrow keys
    flight_index = st.sidebar.number_input(
        "Flight index (use ↑ / ↓ keys)",
        min_value=0,
        max_value=max(0, num_flights - 1),
        value=0,
        step=1,
        help="Click here once, then use your keyboard arrow keys to move through flights.",
    )
    flight_index = int(flight_index)

    flight = flights[flight_index]

    sidebar_label = (
        f"{flight.get('flight_iata', 'N/A')} | "
        f"{flight.get('dep_iata', '---')} → {flight.get('arr_iata', '---')} | "
        f"{flight.get('dep_scheduled', '')}"
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("**Currently selected flight:**")
    st.sidebar.markdown(f"`[{flight_index}]` {sidebar_label}")

    # Build ETD timeline for this flight
    timeline = generate_timeline_for_flight(flight)
    if not timeline:
        st.error("No timeline data available for this flight.")
        return

    # Slider values
    minutes_options = [step["minutes_before_sched"] for step in timeline]
    minutes_options_sorted = sorted(minutes_options, reverse=True)

    st.sidebar.markdown("---")
    st.sidebar.markdown("### Time Before Departure")

    with st.sidebar.container():
        st.markdown(
            '<div style="font-size:0.85rem; opacity:0.8;">'
            "Move the slider closer to departure to see how ETD and messaging change."
            "</div>",
            unsafe_allow_html=True,
        )

        unique_minutes = sorted(set(minutes_options_sorted), reverse=True)

        if len(unique_minutes) == 1:
            selected_minutes = unique_minutes[0]
            st.markdown(
                f"*Only one ETD snapshot available for this flight (T-{selected_minutes} minutes).*"
            )
        else:
            min_val = min(minutes_options_sorted)
            max_val = max(minutes_options_sorted)

            step = 5
            if max_val - min_val < step:
                step = 1

            st.markdown('<div class="plane-slider">', unsafe_allow_html=True)
            selected_minutes = st.slider(
                "Minutes before scheduled departure",
                min_value=min_val,
                max_value=max_val,
                value=max_val,
                step=step,
            )
            st.markdown("</div>", unsafe_allow_html=True)

    # Choose closest snapshot
    current_step = min(
        timeline,
        key=lambda s: abs(s["minutes_before_sched"] - selected_minutes),
    )

    # Parse schedule and snapshot/predicted times for passenger-facing display
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
            f'<div class="aa-label" style="margin-top:0.4rem;">Status (from AA data)</div>'
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
            f'<div class="aa-label" style="margin-top:0.4rem;">Departure Time</div>'
            f'<div class="aa-value">{fmt_12h(sched_dt)}</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            f'<div class="aa-label" style="margin-top:0.6rem;">Snapshot</div>'
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

    # ETD Confidence (bucket only)
    with col_c:
        st.markdown('<div class="aa-card">', unsafe_allow_html=True)
        st.markdown(
            '<div class="aa-card-title-badge">ETD Confidence</div>',
            unsafe_allow_html=True,
        )
        render_confidence_pill(current_step["confidence_bucket"])
        st.markdown(
            f'<div class="aa-label" style="margin-top:0.7rem;">ETD changes so far</div>'
            f'<div class="aa-value">{current_step["num_changes"]}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="aa-label" style="margin-top:0.4rem;">Delay driver</div>'
            f'<div class="aa-value">{current_step["cause_tag"]}</div>',
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("")

    # ---------------- PASSENGER VIEW: TWO CARDS SIDE BY SIDE ----------------
    p_col1, p_col2 = st.columns(2)

    with p_col1:
        st.markdown('<div class="aa-card">', unsafe_allow_html=True)
        st.markdown(
            '<div class="aa-card-title-badge">Passenger-Friendly Delay Explanation</div>',
            unsafe_allow_html=True,
        )
        st.info(current_step["cause_text"])
        st.markdown("</div>", unsafe_allow_html=True)

    with p_col2:
        st.markdown('<div class="aa-card">', unsafe_allow_html=True)
        st.markdown(
            '<div class="aa-card-title-badge">Passenger Safe Window Messaging</div>',
            unsafe_allow_html=True,
        )
        st.success(current_step["safe_window_message"])
        st.markdown("</div>", unsafe_allow_html=True)

    # ---------------- OPS VIEW CARD ----------------
    st.markdown("")
    st.markdown('<div class="aa-card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="aa-card-title-badge">Operational View Notes</div>',
        unsafe_allow_html=True,
    )
    st.write(
        "This view is designed for gate and operations staff to understand how "
        "ETD has moved over time and how reliable the current estimate is."
    )
    st.write(
        "- Times in the table below use a 24-hour clock.\n"
        "- High confidence with few ETD changes suggests a stable departure.\n"
        "- Low confidence or many ETD changes signal that staff should be proactive with updates."
    )
    st.markdown("</div>", unsafe_allow_html=True)

    # ---------------- OPS TIMELINE ----------------
    st.markdown("")
    st.subheader("Operational ETD History (24-hour Ops View)")
    st.markdown(
        "The table below shows every ETD update for this flight as recorded in AA data. "
        "T-minus indicates how many minutes before or after scheduled departure the update was made."
    )

    timeline_rows = []
    for step in timeline:
        timeline_rows.append(
            {
                "T-minus (min)": step["minutes_before_sched"],
                "Snapshot time": format_dt(step["snapshot_time"]),  # 24h ops view
                "Predicted ETD": format_dt(step["predicted_etd"]),  # 24h ops view
                "Est. delay (min)": step["estimated_delay"],
                "Conf. score": step["confidence"],
                "Conf. bucket": step["confidence_bucket"],
                "ETD changes so far": step["num_changes"],
            }
        )

    st.markdown('<div class="aa-table">', unsafe_allow_html=True)
    st.dataframe(timeline_rows, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()