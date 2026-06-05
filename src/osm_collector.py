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


def build_overpass_count_query(ward_name, poi_type):
    if poi_type not in POI_FILTERS:
        raise ValueError(f"Unsupported POI type: {poi_type}")

    filter_block = "\n      ".join(
        f"{filter_expr}(area.ward);" for filter_expr in POI_FILTERS[poi_type]
    )
    return f"""
    [out:json][timeout:25];
    area["name"="東京都"]->.tokyo;
    area["name"="{ward_name}"]["admin_level"="7"]->.ward;
    (
      {filter_block}
    );
    out count;
    """


def query_overpass_for_ward(ward_name, poi_type, max_retries=3, backoff_seconds=2.0):
    """Count a POI category for one ward via Overpass API."""
    query = build_overpass_count_query(ward_name, poi_type)
    headers = {"User-Agent": "TokyoLivabilityIndexBot/1.0 (contact: fuben@github)"}

    for attempt in range(1, max_retries + 1):
        try:
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
                raise RuntimeError(
                    f"Failed to fetch OSM {poi_type} count for {ward_name}."
                ) from exc
            logging.warning(
                "Overpass query failed (%s/%s) for %s %s: %s",
                attempt,
                max_retries,
                ward_name,
                poi_type,
                exc,
            )
            time.sleep(backoff_seconds)


def fetch_osm_data():
    """Fetch POI counts from OpenStreetMap without local fallback values."""
    rows = []
    for code, name in TOKYO_23_WARDS.items():
        counts = {}
        for poi_type in ("convenience", "supermarket", "clinic", "post_office"):
            time.sleep(0.3)
            counts[poi_type] = query_overpass_for_ward(name, poi_type)

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
