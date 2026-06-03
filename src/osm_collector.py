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

MOCK_OSM_STATS = {
    "13101": {"convenience": 180, "supermarket": 20, "clinic": 150},
    "13102": {"convenience": 250, "supermarket": 45, "clinic": 280},
    "13103": {"convenience": 320, "supermarket": 60, "clinic": 390},
    "13104": {"convenience": 450, "supermarket": 85, "clinic": 580},
    "13105": {"convenience": 130, "supermarket": 35, "clinic": 290},
    "13106": {"convenience": 170, "supermarket": 38, "clinic": 190},
    "13107": {"convenience": 180, "supermarket": 42, "clinic": 210},
    "13108": {"convenience": 260, "supermarket": 75, "clinic": 340},
    "13109": {"convenience": 240, "supermarket": 70, "clinic": 310},
    "13110": {"convenience": 170, "supermarket": 48, "clinic": 220},
    "13111": {"convenience": 380, "supermarket": 110, "clinic": 510},
    "13112": {"convenience": 420, "supermarket": 150, "clinic": 720},
    "13113": {"convenience": 310, "supermarket": 55, "clinic": 410},
    "13114": {"convenience": 220, "supermarket": 50, "clinic": 280},
    "13115": {"convenience": 290, "supermarket": 95, "clinic": 480},
    "13116": {"convenience": 280, "supermarket": 65, "clinic": 370},
    "13117": {"convenience": 160, "supermarket": 50, "clinic": 260},
    "13118": {"convenience": 110, "supermarket": 30, "clinic": 150},
    "13119": {"convenience": 270, "supermarket": 90, "clinic": 390},
    "13120": {"convenience": 310, "supermarket": 115, "clinic": 460},
    "13121": {"convenience": 350, "supermarket": 105, "clinic": 420},
    "13122": {"convenience": 220, "supermarket": 65, "clinic": 270},
    "13123": {"convenience": 310, "supermarket": 85, "clinic": 360},
}

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


def generate_mock_data():
    """Generate deterministic demo POI data and save it as CSV."""
    rows = []
    for code, name in TOKYO_23_WARDS.items():
        stats = MOCK_OSM_STATS[code]
        convenience_count = stats["convenience"]
        supermarket_count = stats["supermarket"]
        clinic_count = stats["clinic"]
        post_office_count = int(convenience_count * 0.10)

        rows.append(
            {
                "code": code,
                "ward_name": name,
                "convenience_count": convenience_count,
                "supermarket_count": supermarket_count,
                "medical_facility_count": clinic_count,
                "daily_facility_count": convenience_count
                + supermarket_count
                + post_office_count,
            }
        )

    df = pd.DataFrame(rows)
    output_path = DATA_RAW_DIR / "osm_poi_data.csv"
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    logging.info("Saved deterministic OSM demo data: %s", output_path)
    return df


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
            result = response.json()
            count = result.get("elements", [{}])[0].get("tags", {}).get("total", 0)
            return int(count)
        except Exception as exc:
            if attempt == max_retries:
                logging.error(
                    "Overpass query failed after %s attempts (%s, %s): %s",
                    max_retries,
                    ward_name,
                    poi_type,
                    exc,
                )
                return None
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
    """Fetch POI counts from OSM."""

    rows = []
    for code, name in TOKYO_23_WARDS.items():
        counts = {}
        for poi_type in ("convenience", "supermarket", "clinic", "post_office"):
            time.sleep(0.3)
            count = query_overpass_for_ward(name, poi_type)
            if count is None:
                raise RuntimeError(f"Failed to fetch OSM {poi_type} count for {name}.")
            counts[poi_type] = count

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
    logging.info("Saved OSM data: %s", output_path)
    return df


if __name__ == "__main__":
    fetch_osm_data()
