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


def fetch_overpass_count_with_retry(query, headers, max_retries=3, backoff_seconds=2.0):
    """Return an Overpass count result, failing instead of falling back to static data."""
    for attempt in range(1, max_retries + 1):
        try:
            time.sleep(0.3)
            response = requests.post(
                OVERPASS_API_URL, data={"data": query}, headers=headers, timeout=20
            )
            response.raise_for_status()
            count = (
                response.json().get("elements", [{}])[0].get("tags", {}).get("total")
            )
            if count is None:
                raise ValueError("Overpass response did not include a total count.")
            return int(count)
        except Exception as exc:
            if attempt == max_retries:
                raise RuntimeError("Overpass count request failed.") from exc
            logging.warning(
                "Overpass request failed (%s/%s): %s", attempt, max_retries, exc
            )
            time.sleep(backoff_seconds)


def build_count_query(ward_name, filter_block):
    return f"""
    [out:json][timeout:25];
    area["name"="東京都"]->.tokyo;
    area["name"="{ward_name}"]["admin_level"="7"]->.ward;
    (
      {filter_block}
    );
    out count;
    """


def fetch_spatial_data():
    """Fetch only station and shelter counts from OpenStreetMap."""
    headers = {"User-Agent": "TokyoLivabilityIndexBot/1.0 (contact: fuben@github)"}
    rows = []

    for code, name in TOKYO_23_WARDS.items():
        station_query = build_count_query(
            name,
            """
      node["railway"="station"](area.ward);
      way["railway"="station"](area.ward);
      relation["railway"="station"](area.ward);
            """,
        )
        shelter_query = build_count_query(
            name,
            """
      node["amenity"="shelter"](area.ward);
      way["amenity"="shelter"](area.ward);
      relation["amenity"="shelter"](area.ward);
            """,
        )

        rows.append(
            {
                "code": code,
                "ward_name": name,
                "station_count": fetch_overpass_count_with_retry(
                    station_query, headers
                ),
                "shelter_count": fetch_overpass_count_with_retry(
                    shelter_query, headers
                ),
            }
        )

    df = pd.DataFrame(rows)
    output_path = DATA_RAW_DIR / "spatial_data.csv"
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    logging.info("Saved OSM spatial data: %s", output_path)
    return df


if __name__ == "__main__":
    fetch_spatial_data()
