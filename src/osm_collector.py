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

POI_FILTERS = {
    "convenience": ['node["shop"="convenience"]', 'way["shop"="convenience"]'],
    "supermarket": ['node["shop"="supermarket"]', 'way["shop"="supermarket"]'],
    "clinic": [
        'node["amenity"="clinic"]',
        'way["amenity"="clinic"]',
        'node["amenity"="doctors"]',
        'way["amenity"="doctors"]',
        'node["amenity"="hospital"]',
        'way["amenity"="hospital"]',
    ],
    "post_office": [
        'node["amenity"="post_office"]',
        'way["amenity"="post_office"]',
    ],
}


def build_filter_block(poi_type):
    return "\n      ".join(
        f"{filter_expr}(area.ward);" for filter_expr in POI_FILTERS[poi_type]
    )


def build_overpass_count_query(ward_name):
    return f"""
    [out:json][timeout:25];
    area["name"="東京都"]->.tokyo;
    area["name"="{ward_name}"]["admin_level"="7"]->.ward;
    (
      {build_filter_block("convenience")}
    );
    out count;
    (
      {build_filter_block("supermarket")}
    );
    out count;
    (
      {build_filter_block("clinic")}
    );
    out count;
    (
      {build_filter_block("post_office")}
    );
    out count;
    """


def query_overpass_for_ward(ward_name, max_retries=5):
    """Count all POI categories for one ward via Overpass API."""
    query = build_overpass_count_query(ward_name)
    headers = {"User-Agent": "TokyoLivabilityIndexBot/1.0 (contact: fuben@github)"}

    for attempt in range(1, max_retries + 1):
        try:
            time.sleep(1.0)
            response = requests.post(
                OVERPASS_API_URL, data={"data": query}, headers=headers, timeout=45
            )
            response.raise_for_status()
            counts = [
                element.get("tags", {}).get("total")
                for element in response.json().get("elements", [])
            ]
            if len(counts) != 4 or any(count is None for count in counts):
                raise ValueError("Overpass response did not include expected counts.")
            return {
                "convenience": int(counts[0]),
                "supermarket": int(counts[1]),
                "clinic": int(counts[2]),
                "post_office": int(counts[3]),
            }
        except Exception as exc:
            if attempt == max_retries:
                raise RuntimeError(
                    f"Failed to fetch OSM POI counts for {ward_name}."
                ) from exc
            backoff_seconds = min(2**attempt, 30)
            logging.warning(
                "Overpass query failed (%s/%s) for %s: %s",
                attempt,
                max_retries,
                ward_name,
                exc,
            )
            time.sleep(backoff_seconds)


def fetch_osm_data():
    """Fetch POI counts from OpenStreetMap without local fallback values."""
    rows = []
    for code, name in TOKYO_23_WARDS.items():
        counts = query_overpass_for_ward(name)
        rows.append(
            {
                "code": code,
                "ward_name": name,
                "convenience_count": counts["convenience"],
                "supermarket_count": counts["supermarket"],
                "medical_facility_count": counts["clinic"],
                "daily_facility_count": counts["convenience"]
                + counts["supermarket"]
                + counts["post_office"],
            }
        )

    df = pd.DataFrame(rows)
    output_path = DATA_RAW_DIR / "osm_poi_data.csv"
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    logging.info("Saved OSM POI data: %s", output_path)
    return df


if __name__ == "__main__":
    fetch_osm_data()
