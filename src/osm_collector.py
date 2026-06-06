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


def validate_complete_data(df, label):
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


def build_filter_block(poi_type):
    return "\n      ".join(
        f"{filter_expr}(area.ward);" for filter_expr in POI_FILTERS[poi_type]
    )


def ward_name_regex():
    return "^(" + "|".join(TOKYO_23_WARDS.values()) + ")$"


def build_bulk_overpass_count_query(poi_type):
    return f"""
    [out:json][timeout:180];
    area["name"="東京都"]->.tokyo;
    area(area.tokyo)["admin_level"="7"]["name"~"{ward_name_regex()}"]->.wards;
    foreach.wards->.ward(
      .ward out tags;
      (
        {build_filter_block(poi_type)}
      );
      out count;
    );
    """


def parse_bulk_count_response(data, label):
    name_to_code = {name: code for code, name in TOKYO_23_WARDS.items()}
    counts = {}
    current_code = None

    for element in data.get("elements", []):
        tags = element.get("tags", {})
        ward_name = tags.get("name")
        if ward_name in name_to_code:
            current_code = name_to_code[ward_name]
            continue

        total = tags.get("total")
        if total is not None and current_code is not None:
            counts[current_code] = int(total)
            current_code = None

    missing_codes = sorted(set(TOKYO_23_WARDS) - set(counts))
    if missing_codes:
        missing_labels = ", ".join(
            f"{code}:{TOKYO_23_WARDS[code]}" for code in missing_codes
        )
        raise ValueError(f"{label} bulk response is missing: {missing_labels}")

    return counts


def query_overpass_for_category(poi_type, max_retries=5):
    """Count one POI category for all wards in a single Overpass request."""
    query = build_bulk_overpass_count_query(poi_type)
    headers = {"User-Agent": "TokyoLivabilityIndexBot/1.0 (contact: fuben@github)"}

    for attempt in range(1, max_retries + 1):
        try:
            time.sleep(1.0)
            response = requests.post(
                OVERPASS_API_URL, data={"data": query}, headers=headers, timeout=180
            )
            response.raise_for_status()
            return parse_bulk_count_response(response.json(), f"OSM {poi_type}")
        except Exception as exc:
            if attempt == max_retries:
                raise RuntimeError(
                    f"Failed to fetch OSM {poi_type} counts for all wards."
                ) from exc
            backoff_seconds = min(2**attempt, 30)
            logging.warning(
                "Overpass query failed (%s/%s) for %s: %s",
                attempt,
                max_retries,
                poi_type,
                exc,
            )
            time.sleep(backoff_seconds)


def fetch_osm_data(output_path=None):
    """Fetch POI counts from OSM without local fallback values."""
    category_counts = {
        poi_type: query_overpass_for_category(poi_type)
        for poi_type in ("convenience", "supermarket", "clinic", "post_office")
    }
    rows = []
    for code, name in TOKYO_23_WARDS.items():
        rows.append(
            {
                "code": code,
                "ward_name": name,
                "convenience_count": category_counts["convenience"][code],
                "supermarket_count": category_counts["supermarket"][code],
                "medical_facility_count": category_counts["clinic"][code],
                "daily_facility_count": category_counts["convenience"][code]
                + category_counts["supermarket"][code]
                + category_counts["post_office"][code],
            }
        )

    df = validate_complete_data(pd.DataFrame(rows), "OSM POI live data")
    if output_path is None:
        output_path = OUTPUT_PATH
    output_path = Path(output_path)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    logging.info("Saved OSM POI data: %s", output_path)
    return df


if __name__ == "__main__":
    fetch_osm_data()
