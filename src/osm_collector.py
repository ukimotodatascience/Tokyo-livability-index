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

OUTPUT_PATH = DATA_RAW_DIR / "osm_poi_data.csv"
OUTPUT_COLUMNS = [
    "code",
    "ward_name",
    "convenience_count",
    "supermarket_count",
    "medical_facility_count",
    "daily_facility_count",
]


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
        raise FileNotFoundError(f"OSM POI snapshot not found: {OUTPUT_PATH}")

    df = pd.read_csv(OUTPUT_PATH, dtype={"code": str})
    return validate_complete_snapshot(df, "OSM POI snapshot")


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


def fetch_osm_data(use_existing_on_failure=True):
    """Fetch POI counts from OSM, reusing only a validated prior snapshot on outage."""
    rows = []
    try:
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
    except Exception:
        if not use_existing_on_failure:
            raise
        logging.warning(
            "OSM POI live refresh failed. Using validated existing snapshot: %s",
            OUTPUT_PATH,
        )
        return load_existing_snapshot()

    df = validate_complete_snapshot(pd.DataFrame(rows), "OSM POI live data")
    df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    logging.info("Saved OSM POI data: %s", OUTPUT_PATH)
    return df


if __name__ == "__main__":
    fetch_osm_data()
