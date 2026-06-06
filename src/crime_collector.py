import logging
import sys
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.config import CRIME_DATA_URL, DATA_RAW_DIR, TOKYO_23_WARDS

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

SOURCE_COLUMNS = {
    "address": "市区町丁",
    "total": "総合計",
    "serious": "凶悪犯計",
    "violent": "粗暴犯計",
    "burglary": "侵入窃盗計",
    "non_burglary": "非侵入窃盗計",
    "other": "その他計",
}


def fetch_crime_data(output_path=None):
    """Fetch and aggregate ward crime data from the Metropolitan Police CSV."""
    logging.info("Downloading crime data from: %s", CRIME_DATA_URL)
    try:
        response = requests.get(CRIME_DATA_URL, timeout=15)
        response.raise_for_status()
        content = response.content.decode("cp932", errors="ignore")
        df_raw = pd.read_csv(StringIO(content))
    except Exception as exc:
        raise RuntimeError("Failed to download crime data.") from exc

    df_raw.columns = df_raw.columns.str.strip()
    required_columns = set(SOURCE_COLUMNS.values())
    missing_columns = sorted(required_columns - set(df_raw.columns))
    if missing_columns:
        raise ValueError(f"Crime CSV is missing columns: {', '.join(missing_columns)}")

    def map_to_ward(address):
        if not isinstance(address, str):
            return None
        for code, name in TOKYO_23_WARDS.items():
            if address.startswith(name):
                return code
        return None

    df_raw["code"] = df_raw[SOURCE_COLUMNS["address"]].apply(map_to_ward)
    df_wards = df_raw[df_raw["code"].notna()].copy()
    address_col = SOURCE_COLUMNS["address"]
    subtotal_labels = set(TOKYO_23_WARDS.values()) | {
        f"{name}計" for name in TOKYO_23_WARDS.values()
    }
    df_wards = df_wards[~df_wards[address_col].isin(subtotal_labels)].copy()

    numeric_cols = [
        SOURCE_COLUMNS["total"],
        SOURCE_COLUMNS["serious"],
        SOURCE_COLUMNS["violent"],
        SOURCE_COLUMNS["burglary"],
        SOURCE_COLUMNS["non_burglary"],
        SOURCE_COLUMNS["other"],
    ]
    for col in numeric_cols:
        df_wards[col] = df_wards[col].astype(str).str.replace(",", "").str.strip()
        df_wards[col] = (
            pd.to_numeric(df_wards[col], errors="coerce").fillna(0).astype(int)
        )

    grouped = df_wards.groupby("code").sum(numeric_only=True).reset_index()
    missing_codes = sorted(set(TOKYO_23_WARDS) - set(grouped["code"]))
    if missing_codes:
        missing_labels = ", ".join(
            f"{code}:{TOKYO_23_WARDS[code]}" for code in missing_codes
        )
        raise ValueError(f"Missing crime data for: {missing_labels}")

    grouped["ward_name"] = grouped["code"].map(TOKYO_23_WARDS)
    grouped["total_crime_cases"] = grouped[SOURCE_COLUMNS["total"]]
    grouped["serious_crime_cases"] = grouped[SOURCE_COLUMNS["serious"]]
    grouped["violent_crime_cases"] = grouped[SOURCE_COLUMNS["violent"]]
    grouped["theft_crime_cases"] = (
        grouped[SOURCE_COLUMNS["burglary"]] + grouped[SOURCE_COLUMNS["non_burglary"]]
    )
    grouped["other_crime_cases"] = grouped[SOURCE_COLUMNS["other"]]

    final_cols = [
        "code",
        "ward_name",
        "total_crime_cases",
        "serious_crime_cases",
        "violent_crime_cases",
        "theft_crime_cases",
        "other_crime_cases",
    ]
    df = grouped[final_cols].sort_values("code").reset_index(drop=True)

    if output_path is None:
        output_path = DATA_RAW_DIR / "crime_data.csv"
    output_path = Path(output_path)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    logging.info("Saved crime data: %s", output_path)
    return df


if __name__ == "__main__":
    fetch_crime_data()
