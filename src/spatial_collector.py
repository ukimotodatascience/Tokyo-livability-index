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


def ward_name_regex():
    return "^(" + "|".join(TOKYO_23_WARDS.values()) + ")$"


def fetch_overpass_counts_with_retry(query, expected_counts, max_retries=5):
    """Return Overpass count results, failing instead of using static data."""
    for attempt in range(1, max_retries + 1):
        try:
            time.sleep(1.0)
            response = requests.post(
                OVERPASS_API_URL,
                data={"data": query},
                headers=OVERPASS_HEADERS,
                timeout=180,
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


def fetch_bulk_counts(query, label, max_retries=5):
    for attempt in range(1, max_retries + 1):
        try:
            time.sleep(1.0)
            response = requests.post(
                OVERPASS_API_URL,
                data={"data": query},
                headers=OVERPASS_HEADERS,
                timeout=180,
            )
            response.raise_for_status()
            return parse_bulk_count_response(response.json(), label)
        except Exception as exc:
            if attempt == max_retries:
                raise RuntimeError(f"Overpass {label} bulk request failed.") from exc
            backoff_seconds = min(2**attempt, 30)
            logging.warning(
                "Overpass bulk request failed (%s/%s) for %s: %s",
                attempt,
                max_retries,
                label,
                exc,
            )
            time.sleep(backoff_seconds)


def build_bulk_spatial_query(filter_block):
    return f"""
    [out:json][timeout:180];
    area["name"="東京都"]->.tokyo;
    area(area.tokyo)["admin_level"="7"]["name"~"{ward_name_regex()}"]->.wards;
    foreach.wards->.ward(
      .ward out tags;
      (
        {filter_block}
      );
      out count;
    );
    """


def fetch_spatial_data(output_path=None):
    """Fetch OSM spatial counts without local fallback values."""
    station_counts = fetch_bulk_counts(
        build_bulk_spatial_query(
            """
      node["railway"="station"](area.ward);
      way["railway"="station"](area.ward);
      relation["railway"="station"](area.ward);
            """
        ),
        "station",
    )
    line_counts = fetch_bulk_counts(
        build_bulk_spatial_query(
            """
      relation["type"="route"]["route"~"^(train|subway|light_rail|monorail|tram)$"](area.ward);
            """
        ),
        "railway route",
    )
    shelter_counts = fetch_bulk_counts(
        build_bulk_spatial_query(
            """
      node["amenity"="shelter"](area.ward);
      way["amenity"="shelter"](area.ward);
      relation["amenity"="shelter"](area.ward);
            """
        ),
        "shelter",
    )

    rows = []
    for code, name in TOKYO_23_WARDS.items():
        rows.append(
            {
                "code": code,
                "ward_name": name,
                "station_count": station_counts[code],
                "line_count": line_counts[code],
                "shelter_count": shelter_counts[code],
            }
        )

    df = validate_complete_data(pd.DataFrame(rows), "OSM spatial live data")
    if output_path is None:
        output_path = OUTPUT_PATH
    output_path = Path(output_path)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    logging.info("Saved OSM spatial data: %s", output_path)
    return df


if __name__ == "__main__":
    fetch_spatial_data()
