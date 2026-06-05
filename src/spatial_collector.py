import logging
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.config import DATA_RAW_DIR, OVERPASS_API_URL, TOKYO_23_WARDS

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

OVERPASS_HEADERS = {"User-Agent": "TokyoLivabilityIndexBot/1.0 (contact: fuben@github)"}
OUTPUT_PATH = DATA_RAW_DIR / "spatial_data.csv"
OUTPUT_COLUMNS = ["code", "ward_name", "station_count", "line_count", "shelter_count"]


def validate_complete_snapshot(df, label):
    missing_columns = [column for column in OUTPUT_COLUMNS if column not in df.columns]
    if missing_columns:
        raise ValueError(f"{label} is missing columns: {', '.join(missing_columns)}")

    df["code"] = df["code"].astype(str)
    codes = set(df["code"])
    missing_codes = sorted(set(TOKYO_23_WARDS) - codes)
    extra_codes = sorted(codes - set(TOKYO_23_WARDS))
    if missing_codes or extra_codes or len(df) != len(TOKYO_23_WARDS):
        raise ValueError(
            f"{label} must contain exactly Tokyo 23 wards. "
            f"missing={missing_codes}, extra={extra_codes}, rows={len(df)}"
        )

    return df[OUTPUT_COLUMNS].sort_values("code").reset_index(drop=True)


def load_existing_snapshot():
    if not OUTPUT_PATH.exists():
        raise FileNotFoundError(f"OSM spatial snapshot not found: {OUTPUT_PATH}")

    df = pd.read_csv(OUTPUT_PATH, dtype={"code": str})
    return validate_complete_snapshot(df, "OSM spatial snapshot")


def fetch_overpass_counts_with_retry(query, expected_counts, max_retries=5):
    """Return Overpass count results, failing instead of using static data."""
    for attempt in range(1, max_retries + 1):
        try:
            time.sleep(1.0)
            response = requests.post(
                OVERPASS_API_URL,
                data={"data": query},
                headers=OVERPASS_HEADERS,
                timeout=45,
            )
            response.raise_for_status()
            counts = [
                element.get("tags", {}).get("total")
                for element in response.json().get("elements", [])
            ]
            if len(counts) != expected_counts or any(count is None for count in counts):
                raise ValueError("Overpass response did not include expected counts.")
            return [int(count) for count in counts]
        except Exception as exc:
            if attempt == max_retries:
                raise RuntimeError("Overpass count request failed.") from exc
            backoff_seconds = min(2**attempt, 30)
            logging.warning(
                "Overpass request failed (%s/%s): %s", attempt, max_retries, exc
            )
            time.sleep(backoff_seconds)


def build_spatial_query(ward_name):
    return f"""
    [out:json][timeout:25];
    area["name"="東京都"]->.tokyo;
    area["name"="{ward_name}"]["admin_level"="7"]->.ward;
    (
      node["railway"="station"](area.ward);
      way["railway"="station"](area.ward);
      relation["railway"="station"](area.ward);
    );
    out count;
    (
      relation["type"="route"]["route"~"^(train|subway|light_rail|monorail|tram)$"](area.ward);
    );
    out count;
    (
      node["amenity"="shelter"](area.ward);
      way["amenity"="shelter"](area.ward);
      relation["amenity"="shelter"](area.ward);
    );
    out count;
    """


def fetch_spatial_data(use_existing_on_failure=True):
    """Fetch OSM spatial counts, reusing only a validated prior snapshot on outage."""
    rows = []

    try:
        for code, name in TOKYO_23_WARDS.items():
            station_count, line_count, shelter_count = fetch_overpass_counts_with_retry(
                build_spatial_query(name), expected_counts=3
            )
            rows.append(
                {
                    "code": code,
                    "ward_name": name,
                    "station_count": station_count,
                    "line_count": line_count,
                    "shelter_count": shelter_count,
                }
            )
    except Exception:
        if not use_existing_on_failure:
            raise
        logging.warning(
            "OSM spatial live refresh failed. Using validated existing snapshot: %s",
            OUTPUT_PATH,
        )
        return load_existing_snapshot()

    df = validate_complete_snapshot(pd.DataFrame(rows), "OSM spatial live data")
    df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    logging.info("Saved OSM spatial data: %s", OUTPUT_PATH)
    return df


if __name__ == "__main__":
    fetch_spatial_data()
