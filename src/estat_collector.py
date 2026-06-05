import logging
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.config import DATA_RAW_DIR, ESTAT_API_KEY, ESTAT_API_URL, TOKYO_23_WARDS

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)


def fetch_estat_data(api_key=ESTAT_API_KEY):
    """Fetch ward population from e-Stat without local fallback values."""
    if not api_key:
        raise ValueError("ESTAT_API_KEY is required to fetch e-Stat data.")

    params = {
        "appId": api_key,
        "statsDataId": "0003445094",
        "cdArea": ",".join(TOKYO_23_WARDS.keys()),
        "metaGetFlg": "Y",
        "cntGetFlg": "N",
    }

    data = None
    max_retries = 3
    backoff_seconds = 2.0
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(ESTAT_API_URL, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            break
        except Exception as exc:
            if attempt == max_retries:
                raise RuntimeError("Failed to fetch e-Stat data.") from exc
            logging.warning(
                "e-Stat API request failed (%s/%s): %s",
                attempt,
                max_retries,
                exc,
            )
            time.sleep(backoff_seconds)

    result_status = data.get("GET_STATS_DATA", {}).get("RESULT", {}).get("STATUS", -1)
    if result_status != 0:
        error_msg = (
            data.get("GET_STATS_DATA", {})
            .get("RESULT", {})
            .get("ERROR_MSG", "Unknown Error")
        )
        raise ValueError(f"e-Stat API Error (Status {result_status}): {error_msg}")

    values = (
        data.get("GET_STATS_DATA", {})
        .get("STATISTICAL_DATA", {})
        .get("DATA_INF", {})
        .get("VALUE", [])
    )
    if not values:
        raise ValueError("e-Stat API response contains no value records.")

    ward_data = {}
    for value in values:
        area_code = value.get("@area")
        if area_code not in TOKYO_23_WARDS:
            continue

        cat01 = value.get("@cat01")
        cat02 = value.get("@cat02")
        if cat01 != "0" or cat02 != "0":
            continue

        try:
            population = int(value.get("$", "0"))
        except ValueError:
            population = 0

        if population > 0:
            ward_data[area_code] = {
                "code": area_code,
                "ward_name": TOKYO_23_WARDS[area_code],
                "population": population,
            }

    missing_codes = sorted(set(TOKYO_23_WARDS) - set(ward_data))
    if missing_codes:
        missing_labels = ", ".join(
            f"{code}:{TOKYO_23_WARDS[code]}" for code in missing_codes
        )
        raise ValueError(f"Missing e-Stat population data for: {missing_labels}")

    df = pd.DataFrame([ward_data[code] for code in TOKYO_23_WARDS])
    output_path = DATA_RAW_DIR / "estat_data.csv"
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    logging.info("Saved e-Stat population data: %s", output_path)
    return df


if __name__ == "__main__":
    fetch_estat_data()
