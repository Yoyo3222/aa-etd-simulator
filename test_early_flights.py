import sys
import os
from sim_core import load_clean_flights, generate_timeline_for_flight, format_dt

# Allow running from aa-etd-tests folder
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

def find_early_flights(flights):
    """
    Scan all flights and return any with cause_tag == 'early'.
    """
    early_list = []

    for idx, flight in enumerate(flights):
        timeline = generate_timeline_for_flight(flight)

        for step in timeline:
            if step.get("cause_tag") == "early":
                early_list.append({
                    "index": idx,
                    "flight": flight.get("flight_iata"),
                    "route": f"{flight.get('dep_iata')} → {flight.get('arr_iata')}",
                    "t_minus": step.get("minutes_before_sched"),
                    "predicted_etd": format_dt(step.get("predicted_etd")),
                    "est_delay": step.get("estimated_delay"),
                    "confidence": step.get("confidence_bucket")
                })
                break

    return early_list


def main():
    print("\n🔎 Running early-flight diagnostics...\n")

    flights = load_clean_flights()

    if not flights:
        print("ERROR: Could not load aa_flights_clean.json")
        return

    early_flights = find_early_flights(flights)

    if not early_flights:
        print("No flights were classified as EARLY under current rules.")
        print("Rule currently = ETD more than 5 minutes earlier than schedule.")
        return

    print(f"Found {len(early_flights)} early flights:\n")
    for f in early_flights:
        print("--------------------------------------------")
        print(f"Index:          {f['index']}")
        print(f"Flight:         {f['flight']}")
        print(f"Route:          {f['route']}")
        print(f"T-minus:        {f['t_minus']} min")
        print(f"Predicted ETD:  {f['predicted_etd']}")
        print(f"Est. Delay:     {f['est_delay']} min")
        print(f"Confidence:     {f['confidence']}")
    print("--------------------------------------------")


if __name__ == "__main__":
    main()