import argparse
import logging
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.config import DATA_PROCESSED_DIR
from src.crime_collector import fetch_crime_data
from src.estat_collector import fetch_estat_data
from src.osm_collector import fetch_osm_data
from src.spatial_collector import fetch_spatial_data

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)


def min_max_normalize(series, invert=False):
    min_val = series.min()
    max_val = series.max()

    if max_val == min_val:
        return series.apply(lambda _value: 0.5)

    normalized = (series - min_val) / (max_val - min_val)
    if invert:
        return 1.0 - normalized
    return normalized


def per_capita_rate(count_series, population_series, scale):
    return (count_series / population_series) * scale


def require_columns(df, columns, label):
    missing = sorted(set(columns) - set(df.columns))
    if missing:
        raise ValueError(f"{label} is missing columns: {', '.join(missing)}")


def validate_complete_wards(df, label):
    if df["code"].nunique() != 23 or len(df) != 23:
        raise ValueError(f"{label} must contain exactly 23 unique ward rows.")


def add_ward_characteristics(df):
    characteristics = []
    for _, row in df.iterrows():
        traits = []

        if row["score_accessibility"] >= 80:
            traits.append("駅数が多く、鉄道アクセスを重視する人に向いています。")
        if row["score_safety"] >= 80:
            traits.append("人口あたりの犯罪件数が比較的少ないエリアです。")
        if row["score_convenience"] >= 80:
            traits.append(
                "生活施設が多く、日常の買い物や医療アクセスを確保しやすいです。"
            )
        if row["score_resilience"] >= 80:
            traits.append("人口あたりの避難所数が比較的多いエリアです。")

        if not traits:
            traits.append("実取得データで見ると、各指標のバランス型エリアです。")

        characteristics.append(" ".join(traits))

    df["recommended_profile"] = characteristics
    return df


def run_pipeline():
    logging.info("Starting Tokyo livability data pipeline.")

    estat_df = fetch_estat_data()
    crime_df = fetch_crime_data()
    osm_df = fetch_osm_data()
    spatial_df = fetch_spatial_data()

    require_columns(estat_df, ["code", "ward_name", "population"], "e-Stat data")
    require_columns(
        crime_df,
        [
            "code",
            "total_crime_cases",
            "serious_crime_cases",
            "violent_crime_cases",
            "theft_crime_cases",
            "other_crime_cases",
        ],
        "crime data",
    )
    require_columns(
        osm_df,
        [
            "code",
            "convenience_count",
            "supermarket_count",
            "medical_facility_count",
            "daily_facility_count",
        ],
        "OSM POI data",
    )
    require_columns(
        spatial_df,
        ["code", "station_count", "shelter_count"],
        "OSM spatial data",
    )

    for label, df in (
        ("e-Stat data", estat_df),
        ("crime data", crime_df),
        ("OSM POI data", osm_df),
        ("OSM spatial data", spatial_df),
    ):
        df["code"] = df["code"].astype(str)
        validate_complete_wards(df, label)

    master_df = estat_df.merge(
        crime_df.drop(columns=["ward_name"], errors="ignore"), on="code", how="inner"
    )
    master_df = master_df.merge(
        osm_df.drop(columns=["ward_name"], errors="ignore"), on="code", how="inner"
    )
    master_df = master_df.merge(
        spatial_df.drop(columns=["ward_name"], errors="ignore"), on="code", how="inner"
    )
    validate_complete_wards(master_df, "merged data")

    master_df["crime_rate_per_1000"] = per_capita_rate(
        master_df["total_crime_cases"], master_df["population"], 1000
    )
    master_df["serious_crime_rate_per_10000"] = per_capita_rate(
        master_df["serious_crime_cases"], master_df["population"], 10000
    )
    master_df["station_rate_per_100000"] = per_capita_rate(
        master_df["station_count"], master_df["population"], 100000
    )
    master_df["shelter_rate_per_100000"] = per_capita_rate(
        master_df["shelter_count"], master_df["population"], 100000
    )
    master_df["convenience_rate_per_100000"] = per_capita_rate(
        master_df["convenience_count"], master_df["population"], 100000
    )
    master_df["supermarket_rate_per_100000"] = per_capita_rate(
        master_df["supermarket_count"], master_df["population"], 100000
    )
    master_df["medical_rate_per_100000"] = per_capita_rate(
        master_df["medical_facility_count"], master_df["population"], 100000
    )
    master_df["daily_facility_rate_per_100000"] = per_capita_rate(
        master_df["daily_facility_count"], master_df["population"], 100000
    )

    master_df["norm_station"] = min_max_normalize(master_df["station_rate_per_100000"])
    master_df["norm_total_crime"] = min_max_normalize(
        master_df["crime_rate_per_1000"], invert=True
    )
    master_df["norm_serious_crime"] = min_max_normalize(
        master_df["serious_crime_rate_per_10000"], invert=True
    )
    master_df["norm_convenience"] = min_max_normalize(
        master_df["convenience_rate_per_100000"]
    )
    master_df["norm_supermarket"] = min_max_normalize(
        master_df["supermarket_rate_per_100000"]
    )
    master_df["norm_medical"] = min_max_normalize(master_df["medical_rate_per_100000"])
    master_df["norm_daily_access"] = min_max_normalize(
        master_df["daily_facility_rate_per_100000"]
    )
    master_df["norm_shelter"] = min_max_normalize(master_df["shelter_rate_per_100000"])

    master_df["score_accessibility"] = master_df["norm_station"]
    master_df["score_safety"] = (
        0.7 * master_df["norm_total_crime"] + 0.3 * master_df["norm_serious_crime"]
    )
    master_df["score_convenience"] = (
        0.25 * master_df["norm_convenience"]
        + 0.25 * master_df["norm_supermarket"]
        + 0.30 * master_df["norm_medical"]
        + 0.20 * master_df["norm_daily_access"]
    )
    master_df["score_resilience"] = master_df["norm_shelter"]

    score_cols = [
        "score_accessibility",
        "score_safety",
        "score_convenience",
        "score_resilience",
    ]
    for col in score_cols:
        master_df[col] = (master_df[col] * 100).round(1)

    master_df = add_ward_characteristics(master_df)

    final_cols = [
        "code",
        "ward_name",
        "population",
        "score_accessibility",
        "score_safety",
        "score_convenience",
        "score_resilience",
        "recommended_profile",
    ]
    output_df = master_df[final_cols].copy()

    output_path = DATA_PROCESSED_DIR / "tokyo_livability_index.csv"
    output_df.to_csv(output_path, index=False, encoding="utf-8-sig")
    logging.info("Saved processed livability index: %s", output_path)
    print(output_df.head(5).to_string(index=False))
    return output_df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch real source data and build Tokyo 23 ward livability scores."
    )
    parser.add_argument(
        "--real",
        action="store_true",
        default=False,
        help="Kept for CLI compatibility; the pipeline always uses real source data.",
    )
    parser.parse_args()
    run_pipeline()
