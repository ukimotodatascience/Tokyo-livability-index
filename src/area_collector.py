import logging
import re
import sys
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.config import DATA_RAW_DIR, GSI_AREA_DATA_URL, TOKYO_23_WARDS

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

AREA_COLUMN_PATTERN = re.compile(r"令和.+\(k㎡\)")


def fetch_area_data(output_path=None):
    """Fetch official ward areas from GSI's municipal area CSV."""
    logging.info("Downloading ward area data from: %s", GSI_AREA_DATA_URL)
    try:
        response = requests.get(GSI_AREA_DATA_URL, timeout=20)
        response.raise_for_status()
        content = response.content.decode("cp932", errors="ignore")
        df_raw = pd.read_csv(StringIO(content), skiprows=4, dtype=str)
    except Exception as exc:
        raise RuntimeError("Failed to download ward area data.") from exc

    area_columns = [
        column for column in df_raw.columns if AREA_COLUMN_PATTERN.fullmatch(column)
    ]
    if not area_columns:
        raise ValueError("GSI area CSV does not contain an area column.")

    latest_area_column = area_columns[0]
    code_column = "標準地域コード"
    ward_column = "市区町村"
    required_columns = {code_column, ward_column, latest_area_column}
    missing_columns = sorted(required_columns - set(df_raw.columns))
    if missing_columns:
        raise ValueError(
            f"GSI area CSV is missing columns: {', '.join(missing_columns)}"
        )

    df_raw[code_column] = df_raw[code_column].astype(str).str.strip()
    df = df_raw[df_raw[code_column].isin(TOKYO_23_WARDS)].copy()
    df["ward_area_km2"] = pd.to_numeric(
        df[latest_area_column].str.replace(",", "").str.strip(),
        errors="coerce",
    )
    df["ward_name"] = df[code_column].map(TOKYO_23_WARDS)
    df["source_ward_name"] = df[ward_column].astype(str).str.strip()

    mismatched_names = df[df["ward_name"] != df["source_ward_name"]]
    if not mismatched_names.empty:
        mismatches = ", ".join(
            f"{row[code_column]}:{row['source_ward_name']}"
            for _, row in mismatched_names.iterrows()
        )
        raise ValueError(f"GSI area CSV has unexpected ward names: {mismatches}")

    if df["ward_area_km2"].isna().any() or (df["ward_area_km2"] <= 0).any():
        raise ValueError("GSI area CSV contains invalid ward area values.")

    found_codes = set(df[code_column])
    missing_codes = sorted(set(TOKYO_23_WARDS) - found_codes)
    if missing_codes:
        missing_labels = ", ".join(
            f"{code}:{TOKYO_23_WARDS[code]}" for code in missing_codes
        )
        raise ValueError(f"Missing ward area data for: {missing_labels}")

    df = df.rename(columns={code_column: "code"})
    df = df[["code", "ward_name", "ward_area_km2"]].sort_values("code")
    df = df.reset_index(drop=True)

    if output_path is None:
        output_path = DATA_RAW_DIR / "area_data.csv"
    output_path = Path(output_path)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    logging.info("Saved official ward area data: %s", output_path)
    return df


if __name__ == "__main__":
    fetch_area_data()
