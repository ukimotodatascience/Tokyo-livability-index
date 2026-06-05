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


def fetch_spatial_data():
    """Fetch station, railway route, and shelter counts from OpenStreetMap."""
    rows = []

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

    df = pd.DataFrame(rows)
    output_path = DATA_RAW_DIR / "spatial_data.csv"
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    logging.info("Saved OSM spatial data: %s", output_path)
    return df


if __name__ == "__main__":
    fetch_spatial_data()
