import argparse
import logging
import sys
from pathlib import Path


sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.area_collector import fetch_area_data
from src.config import DATA_PROCESSED_DIR, TOKYO_23_WARDS
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


def require_columns(df, columns, label):
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f"{label} is missing columns: {', '.join(missing)}")


def require_complete_wards(df, label):
    codes = set(df["code"].astype(str))
    expected_codes = set(TOKYO_23_WARDS)
    missing = sorted(expected_codes - codes)
    extra = sorted(codes - expected_codes)
    if missing or extra or len(df) != len(expected_codes):
        raise ValueError(
            f"{label} must contain exactly Tokyo 23 wards. "
            f"missing={missing}, extra={extra}, rows={len(df)}"
        )


def add_ward_characteristics(df):
    characteristics = []
    for _, row in df.iterrows():
        traits = []

        if row["score_accessibility"] >= 75:
            traits.append(
                "人口あたりの駅数・路線数が多く、鉄道アクセスを重視する人に向いています。"
            )
        if row["score_safety"] >= 75:
            traits.append("人口あたりの犯罪件数が比較的少ないエリアです。")
        elif row["score_safety"] <= 35:
            traits.append(
                "犯罪件数は人口比で高めに出ているため、住むエリアの確認が必要です。"
            )
        if row["score_convenience"] >= 75:
            traits.append(
                "人口あたりの生活施設が多く、日常の買い物や医療アクセスを確保しやすいです。"
            )
        if row["score_resilience"] >= 75:
            traits.append("人口あたりの避難所数が比較的多いエリアです。")

        if not traits:
            traits.append("実取得データで見ると、各指標のバランス型エリアです。")

        characteristics.append(" ".join(traits))

    df["recommended_profile"] = characteristics
    return df


def merge_source_data(estat_df, crime_df, osm_df, spatial_df, area_df):
    source_requirements = [
        ("e-Stat data", estat_df, ["code", "ward_name", "population"]),
        (
            "crime data",
            crime_df,
            [
                "code",
                "ward_name",
                "total_crime_cases",
                "serious_crime_cases",
                "violent_crime_cases",
                "theft_crime_cases",
                "other_crime_cases",
            ],
        ),
        (
            "OSM POI data",
            osm_df,
            [
                "code",
                "ward_name",
                "convenience_count",
                "supermarket_count",
                "medical_facility_count",
                "daily_facility_count",
            ],
        ),
        (
            "spatial data",
            spatial_df,
            ["code", "ward_name", "station_count", "line_count", "shelter_count"],
        ),
        ("area data", area_df, ["code", "ward_name", "ward_area_km2"]),
    ]

    for label, df, columns in source_requirements:
        require_columns(df, columns, label)
        df["code"] = df["code"].astype(str)
        require_complete_wards(df, label)

    master_df = estat_df.merge(
        crime_df.drop(columns=["ward_name"]), on="code", how="inner"
    )
    master_df = master_df.merge(
        osm_df.drop(columns=["ward_name"]), on="code", how="inner"
    )
    master_df = master_df.merge(
        spatial_df.drop(columns=["ward_name"]), on="code", how="inner"
    )
    master_df = master_df.merge(
        area_df.drop(columns=["ward_name"]), on="code", how="inner"
    )
    require_complete_wards(master_df, "merged source data")
    return master_df


def build_scores(master_df):
    master_df["station_density"] = (
        master_df["station_count"] / master_df["ward_area_km2"]
    )
    master_df["line_density"] = master_df["line_count"] / master_df["ward_area_km2"]
    master_df["convenience_density"] = (
        master_df["convenience_count"] / master_df["ward_area_km2"]
    )
    master_df["supermarket_density"] = (
        master_df["supermarket_count"] / master_df["ward_area_km2"]
    )
    master_df["medical_density"] = (
        master_df["medical_facility_count"] / master_df["ward_area_km2"]
    )
    master_df["daily_facility_density"] = (
        master_df["daily_facility_count"] / master_df["ward_area_km2"]
    )

    master_df["crime_rate_per_1000"] = (
        master_df["total_crime_cases"] / master_df["population"]
    ) * 1000
    master_df["serious_crime_rate_per_10000"] = (
        master_df["serious_crime_cases"] / master_df["population"]
    ) * 10000
    master_df["shelter_rate_per_10000"] = (
        master_df["shelter_count"] / master_df["population"]
    ) * 10000

    master_df["score_accessibility"] = 0.7 * min_max_normalize(
        master_df["station_density"]
    ) + 0.3 * min_max_normalize(master_df["line_density"])
    master_df["score_safety"] = 0.7 * min_max_normalize(
        master_df["crime_rate_per_1000"], invert=True
    ) + 0.3 * min_max_normalize(master_df["serious_crime_rate_per_10000"], invert=True)
    master_df["score_convenience"] = (
        0.25 * min_max_normalize(master_df["convenience_density"])
        + 0.25 * min_max_normalize(master_df["supermarket_density"])
        + 0.30 * min_max_normalize(master_df["medical_density"])
        + 0.20 * min_max_normalize(master_df["daily_facility_density"])
    )
    master_df["score_resilience"] = min_max_normalize(
        master_df["shelter_rate_per_10000"]
    )

    score_cols = [column for column in master_df.columns if column.startswith("score_")]
    for column in score_cols:
        master_df[column] = (master_df[column] * 100).round(1)

    return add_ward_characteristics(master_df)


def run_pipeline():
    logging.info("Starting Tokyo livability data pipeline.")

    estat_df = fetch_estat_data()
    crime_df = fetch_crime_data()
    osm_df = fetch_osm_data()
    spatial_df = fetch_spatial_data()
    area_df = fetch_area_data()

    master_df = merge_source_data(estat_df, crime_df, osm_df, spatial_df, area_df)
    output_df = build_scores(master_df)

    final_cols = [
        "code",
        "ward_name",
        "population",
        "ward_area_km2",
        "score_accessibility",
        "score_safety",
        "score_convenience",
        "score_resilience",
        "recommended_profile",
    ]

    output_path = DATA_PROCESSED_DIR / "tokyo_livability_index.csv"
    output_df[final_cols].to_csv(output_path, index=False, encoding="utf-8-sig")
    logging.info("Saved processed livability index: %s", output_path)
    print(output_df[final_cols].head(5).to_string(index=False))
    return output_df[final_cols]


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
