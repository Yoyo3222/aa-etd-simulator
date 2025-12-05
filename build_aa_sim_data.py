import json
import pandas as pd

INPUT_FILE = "Clean_AA_FlightData.txt"
OUTPUT_FILE = "aa_flights_clean.json"


def load_aa_data() -> pd.DataFrame:
    """
    Load the cleaned AA ETD dataset from the TXT/CSV file.

    We use on_bad_lines='skip' to ignore any malformed rows.
    Then we drop rows that don't have a scheduled departure time.
    """
    df = pd.read_csv(
        INPUT_FILE,
        dtype=str,
        on_bad_lines="skip"
    )

    required_cols = [
        "OPERAT_CARRIER_CD",
        "Key",
        "OPERAT_FLIGHT_NBR",
        "SCHD_DEP_DT",
        "SCHD_DEP_AIRPRT_IATA_CD",
        "ARVL_AIRPRT_IATA_CD",
        "SCHD_LEG_DEP_TMS",
        "EST_LEG_DEP_TMS",
        "ACTL_LEG_DEP_TMS",
        "SCHD_LEG_ARVL_TMS",
        "EST_LEG_ARVL_TMS",
        "ACTL_LEG_ARVL_TMS",
        "LAST_UPDT_TMS_LCL",
        "CURR_STATUS_IND",
    ]

    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing expected columns in {INPUT_FILE}: {missing}")

    # Drop junk rows that don't even have a scheduled departure time
    df = df[df["SCHD_LEG_DEP_TMS"].notna()].copy()

    # Prepare datetime column for sorting
    df["LAST_UPDT_TMS_LCL_dt"] = pd.to_datetime(
        df["LAST_UPDT_TMS_LCL"], errors="coerce"
    )

    return df


def clean_str(v) -> str:
    """Convert a value to a safe stripped string, handling NaN."""
    if pd.isna(v):
        return ""
    return str(v).strip()


def summarize_flights(df: pd.DataFrame):
    """
    Aggregate the raw AA ETD rows into one summary row per flight (per Key).

    For each Key:
      - Prefer the row where CURR_STATUS_IND == 'Y' (final record)
      - If no 'Y' row exists, use the latest LAST_UPDT_TMS_LCL row
    """
    flights = []

    for key, g in df.groupby("Key"):
        # final record row(s)
        final_rows = g[g["CURR_STATUS_IND"] == "Y"].copy()
        if not final_rows.empty:
            final_row = final_rows.sort_values("LAST_UPDT_TMS_LCL_dt").iloc[-1]
        else:
            final_row = g.sort_values("LAST_UPDT_TMS_LCL_dt").iloc[-1]

        carrier = clean_str(final_row["OPERAT_CARRIER_CD"])
        flight_nbr = clean_str(final_row["OPERAT_FLIGHT_NBR"])
        dep_iata = clean_str(final_row["SCHD_DEP_AIRPRT_IATA_CD"])
        arr_iata = clean_str(final_row["ARVL_AIRPRT_IATA_CD"])

        # Build a simple flight code like AA1001; if carrier/number missing, fall back to Key
        flight_code = f"{carrier}{flight_nbr}" if (carrier or flight_nbr) else key

        airline_name = "American Airlines" if carrier == "AA" else carrier

        dep_scheduled = clean_str(final_row["SCHD_LEG_DEP_TMS"])
        dep_estimated = clean_str(final_row["EST_LEG_DEP_TMS"])
        dep_actual = clean_str(final_row["ACTL_LEG_DEP_TMS"])

        status = "completed" if dep_actual else "scheduled"

        flights.append(
            {
                "key": key,
                "flight_iata": flight_code,
                "flight_number": flight_nbr,
                "airline": airline_name,
                "dep_airport": dep_iata,  # we only have IATA; using it for both
                "dep_iata": dep_iata,
                "arr_iata": arr_iata,
                "dep_scheduled": dep_scheduled,
                "dep_estimated": dep_estimated,
                "dep_actual": dep_actual,
                "status": status,
            }
        )

    return flights


def save_clean_flights(flights):
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(flights, f, indent=2)
    print(f"Saved {len(flights)} flights to {OUTPUT_FILE}")


def main():
    print(f"Loading AA dataset from {INPUT_FILE} ...")
    df = load_aa_data()
    print(f"Loaded {len(df):,} raw rows (after dropping empty schedule rows).")

    print("Summarizing to one row per flight (Key)...")
    flights = summarize_flights(df)
    print(f"Built {len(flights):,} flight records for simulator input.")

    save_clean_flights(flights)


if __name__ == "__main__":
    main()
