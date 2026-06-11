import argparse
import logging
import sys
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.area_collector import fetch_area_data
from src.config import DATA_PROCESSED_DIR, DATA_RAW_DIR, TOKYO_23_WARDS, ROOT_DIR
from src.crime_collector import fetch_crime_data
from src.estat_collector import fetch_estat_data
from src.osm_collector import fetch_osm_data
from src.spatial_collector import fetch_spatial_data

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

RAW_OUTPUT_PATHS = {
    "estat": DATA_RAW_DIR / "estat_data.csv",
    "crime": DATA_RAW_DIR / "crime_data.csv",
    "osm": DATA_RAW_DIR / "osm_poi_data.csv",
    "spatial": DATA_RAW_DIR / "spatial_data.csv",
    "area": DATA_RAW_DIR / "area_data.csv",
}
PROCESSED_OUTPUT_PATH = DATA_PROCESSED_DIR / "tokyo_livability_index.csv"


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

        if row["score_affordability"] >= 75:
            traits.append("家賃相場が比較的安く、住居コストを抑えられます。")
        elif row["score_affordability"] <= 35:
            traits.append("家賃相場が高いため、十分な予算設計が必要です。")

        if row["score_accessibility"] >= 75:
            traits.append(
                "主要駅へのアクセスが良く、通勤・通学の鉄道利便性を重視する人に向いています。"
            )
        if row["score_safety"] >= 75:
            traits.append("人口あたりの犯罪件数が比較的少ない治安の良いエリアです。")
        elif row["score_safety"] <= 35:
            traits.append(
                "犯罪件数は人口比で高めに出ているため、住むエリアの確認が必要です。"
            )
        if row["score_convenience"] >= 75:
            traits.append(
                "買い物施設や医療アクセスが充実しており、日常生活の利便性が高いです。"
            )
        if row["score_resilience"] >= 75:
            traits.append(
                "水害などの災害リスクが比較的低く、避難所インフラも整っています。"
            )
        elif row["score_resilience"] <= 35:
            traits.append(
                "ハザードマップ（浸水リスク等）を確認しておくことを推奨します。"
            )
        if row["score_livability"] >= 75:
            traits.append("若い単身層が多く住んでおり、公園などの自然環境も豊かです。")

        if not traits:
            traits.append("実取得データで見ると、各指標のバランスが良いエリアです。")

        characteristics.append(" ".join(traits))

    df["recommended_profile"] = characteristics
    return df


def merge_source_data(estat_df, crime_df, osm_df, spatial_df, area_df, master_raw_df):
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
                "violent_crime_count",
                "theft_count",
                "bicycle_theft_count",
                "burglary_count",
                "crime_yoy_rate",
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
        (
            "master raw data",
            master_raw_df,
            [
                "code",
                "household_total",
                "age_20s_ratio",
                "age_30s_ratio",
                "elderly_ratio",
                "day_night_population_ratio",
                "rent_monthly_avg",
                "rent_per_tatami",
                "vacant_house_ratio",
                "land_price_avg",
                "time_to_tokyo_min",
                "time_to_shinjuku_min",
                "time_to_shibuya_min",
                "time_to_ikebukuro_min",
                "time_to_shinagawa_min",
                "avg_time_to_major_stations_min",
                "avg_transfer_count",
                "evacuation_place_count",
                "avg_distance_to_shelter_m",
                "max_distance_to_shelter_m",
                "flood_risk_area_ratio",
                "flood_depth_avg",
                "flood_depth_max",
                "population_in_flood_area_ratio",
                "storm_surge_risk_area_ratio",
                "storm_surge_depth_max",
                "liquefaction_high_area_ratio",
                "liquefaction_medium_area_ratio",
                "landslide_warning_area_ratio",
                "elevation_avg",
                "elevation_min",
                "lowland_area_ratio",
                "park_count",
                "park_area_total",
                "park_area_per_capita",
                "green_land_ratio",
                "water_area_ratio",
                "residential_land_ratio",
                "commercial_land_ratio",
                "industrial_land_ratio",
                "major_road_length_km",
                "major_road_density",
                "railway_length_km",
            ],
        ),
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
    master_df = master_df.merge(master_raw_df, on="code", how="inner")
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

    # Calculate additional metrics requested from table definitions
    master_df["population_total"] = master_df["population"].astype(int)
    master_df["area_km2"] = master_df["ward_area_km2"]
    master_df["population_density"] = (
        master_df["population"] / master_df["ward_area_km2"]
    )
    master_df["avg_household_size"] = (
        master_df["population"] / master_df["household_total"]
    )

    master_df["supermarket_per_10k"] = (
        master_df["supermarket_count"] / master_df["population"]
    ) * 10000
    master_df["supermarket_per_km2"] = (
        master_df["supermarket_count"] / master_df["ward_area_km2"]
    )
    master_df["convenience_store_count"] = master_df["convenience_count"]
    master_df["convenience_store_per_10k"] = (
        master_df["convenience_count"] / master_df["population"]
    ) * 10000
    master_df["convenience_store_per_km2"] = (
        master_df["convenience_count"] / master_df["ward_area_km2"]
    )
    master_df["medical_facility_per_10k"] = (
        master_df["medical_facility_count"] / master_df["population"]
    ) * 10000
    master_df["medical_facility_per_km2"] = (
        master_df["medical_facility_count"] / master_df["ward_area_km2"]
    )

    master_df["crime_total_per_10k"] = (
        master_df["crime_total_count"] / master_df["population"]
    ) * 10000
    master_df["crime_density_per_km2"] = (
        master_df["crime_total_count"] / master_df["ward_area_km2"]
    )
    master_df["violent_crime_per_10k"] = (
        master_df["violent_crime_count"] / master_df["population"]
    ) * 10000
    master_df["theft_per_10k"] = (
        master_df["theft_count"] / master_df["population"]
    ) * 10000
    master_df["bicycle_theft_per_10k"] = (
        master_df["bicycle_theft_count"] / master_df["population"]
    ) * 10000
    master_df["burglary_per_10k"] = (
        master_df["burglary_count"] / master_df["population"]
    ) * 10000

    master_df["shelter_per_10k"] = (
        master_df["shelter_count"] / master_df["population"]
    ) * 10000
    master_df["shelter_density"] = (
        master_df["shelter_count"] / master_df["ward_area_km2"]
    )

    master_df["major_road_density"] = (
        master_df["major_road_length_km"] / master_df["ward_area_km2"]
    )

    # 1. 交通アクセス (駅密度40%, 路線密度20%, 主要駅アクセス時間40%)
    access_time_score = min_max_normalize(
        master_df["avg_time_to_major_stations_min"], invert=True
    )
    master_df["score_accessibility"] = (
        0.4 * min_max_normalize(master_df["station_density"])
        + 0.2 * min_max_normalize(master_df["line_density"])
        + 0.4 * access_time_score
    )

    # 2. 治安 (総犯罪率70%, 重大犯罪率30%)
    master_df["score_safety"] = 0.7 * min_max_normalize(
        master_df["crime_rate_per_1000"], invert=True
    ) + 0.3 * min_max_normalize(master_df["serious_crime_rate_per_10000"], invert=True)

    # 3. 生活利便性 (コンビニ25%, スーパー25%, 医療30%, 日常施設20%)
    master_df["score_convenience"] = (
        0.25 * min_max_normalize(master_df["convenience_density"])
        + 0.25 * min_max_normalize(master_df["supermarket_density"])
        + 0.30 * min_max_normalize(master_df["medical_density"])
        + 0.20 * min_max_normalize(master_df["daily_facility_density"])
    )

    # 4. 防災・災害スコア (洪水リスク40%, 避難所密度30%, 液状化リスク30%)
    flood_score = min_max_normalize(master_df["flood_risk_area_ratio"], invert=True)
    shelter_score = min_max_normalize(master_df["shelter_rate_per_10000"])
    liquefaction_score = min_max_normalize(
        master_df["liquefaction_high_area_ratio"], invert=True
    )
    master_df["score_resilience"] = (
        0.40 * flood_score + 0.30 * shelter_score + 0.30 * liquefaction_score
    )

    # 5. 住居コストスコア (平均家賃60%, 畳あたり家賃40%)
    rent_score = min_max_normalize(master_df["rent_monthly_avg"], invert=True)
    rent_tatami_score = min_max_normalize(master_df["rent_per_tatami"], invert=True)
    master_df["score_affordability"] = 0.60 * rent_score + 0.40 * rent_tatami_score

    # 6. 住環境・ライフスタイルスコア (20代30代若年層割合50%, 人口1人あたり公園面積50%)
    young_ratio = master_df["age_20s_ratio"] + master_df["age_30s_ratio"]
    young_score = min_max_normalize(young_ratio)
    park_score = min_max_normalize(master_df["park_area_per_capita"])
    master_df["score_livability"] = 0.50 * young_score + 0.50 * park_score

    score_cols = [column for column in master_df.columns if column.startswith("score_")]
    for column in score_cols:
        master_df[column] = (master_df[column] * 100).round(1)

    return add_ward_characteristics(master_df)


def run_pipeline():
    logging.info("Starting Tokyo livability data pipeline.")

    with TemporaryDirectory(prefix=".tmp_update_", dir=DATA_RAW_DIR) as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        temp_raw_paths = {
            source_name: temp_dir / final_path.name
            for source_name, final_path in RAW_OUTPUT_PATHS.items()
        }
        temp_processed_path = temp_dir / PROCESSED_OUTPUT_PATH.name

        # e-Stat
        try:
            estat_df = fetch_estat_data(output_path=temp_raw_paths["estat"])
        except Exception as exc:
            logging.warning(
                "e-Stat API fetch failed, falling back to local raw data: %s", exc
            )
            if (DATA_RAW_DIR / "estat_data.csv").exists():
                estat_df = pd.read_csv(DATA_RAW_DIR / "estat_data.csv")
                estat_df.to_csv(
                    temp_raw_paths["estat"], index=False, encoding="utf-8-sig"
                )
            else:
                raise RuntimeError(
                    "e-Stat fetch failed and no local fallback available."
                ) from exc

        # Crime
        try:
            crime_df = fetch_crime_data(output_path=temp_raw_paths["crime"])
        except Exception as exc:
            logging.warning(
                "Crime fetch failed, falling back to local raw data: %s", exc
            )
            if (DATA_RAW_DIR / "crime_data.csv").exists():
                crime_df = pd.read_csv(DATA_RAW_DIR / "crime_data.csv")
                # Ensure local raw crime data has the new required columns, otherwise we might need to recreate them
                required_crime_cols = {
                    "crime_total_count",
                    "violent_crime_count",
                    "theft_count",
                    "bicycle_theft_count",
                    "burglary_count",
                    "crime_yoy_rate",
                }
                if not required_crime_cols.issubset(crime_df.columns):
                    logging.info(
                        "Local crime fallback CSV is outdated. Regenerating offline fallback."
                    )
                    crime_df["crime_total_count"] = crime_df["total_crime_cases"]
                    crime_df["violent_crime_count"] = (
                        crime_df["serious_crime_cases"]
                        + crime_df["violent_crime_cases"]
                    )
                    crime_df["theft_count"] = crime_df["theft_crime_cases"]
                    crime_df["bicycle_theft_count"] = 0
                    crime_df["burglary_count"] = 0
                    crime_df["crime_yoy_rate"] = 0.0
                crime_df.to_csv(
                    temp_raw_paths["crime"], index=False, encoding="utf-8-sig"
                )
            else:
                raise RuntimeError(
                    "Crime fetch failed and no local fallback available."
                ) from exc

        # OSM POI
        try:
            osm_df = fetch_osm_data(output_path=temp_raw_paths["osm"])
        except Exception as exc:
            logging.warning(
                "OSM POI fetch failed, falling back to local raw data: %s", exc
            )
            if (DATA_RAW_DIR / "osm_poi_data.csv").exists():
                osm_df = pd.read_csv(DATA_RAW_DIR / "osm_poi_data.csv")
                osm_df.to_csv(temp_raw_paths["osm"], index=False, encoding="utf-8-sig")
            else:
                raise RuntimeError(
                    "OSM POI fetch failed and no local fallback available."
                ) from exc

        # Spatial
        try:
            spatial_df = fetch_spatial_data(output_path=temp_raw_paths["spatial"])
        except Exception as exc:
            logging.warning(
                "Spatial fetch failed, falling back to local raw data: %s", exc
            )
            if (DATA_RAW_DIR / "spatial_data.csv").exists():
                spatial_df = pd.read_csv(DATA_RAW_DIR / "spatial_data.csv")
                spatial_df.to_csv(
                    temp_raw_paths["spatial"], index=False, encoding="utf-8-sig"
                )
            else:
                raise RuntimeError(
                    "Spatial fetch failed and no local fallback available."
                ) from exc

        # Area
        try:
            area_df = fetch_area_data(output_path=temp_raw_paths["area"])
        except Exception as exc:
            logging.warning(
                "Area fetch failed, falling back to local raw data: %s", exc
            )
            if (DATA_RAW_DIR / "area_data.csv").exists():
                area_df = pd.read_csv(DATA_RAW_DIR / "area_data.csv")
                area_df.to_csv(
                    temp_raw_paths["area"], index=False, encoding="utf-8-sig"
                )
            else:
                raise RuntimeError(
                    "Area fetch failed and no local fallback available."
                ) from exc

        # Load local static stats master CSV
        master_csv_path = DATA_RAW_DIR / "tokyo_wards_master.csv"
        logging.info("Loading static stats master CSV from: %s", master_csv_path)
        master_raw_df = pd.read_csv(master_csv_path)

        master_df = merge_source_data(
            estat_df, crime_df, osm_df, spatial_df, area_df, master_raw_df
        )
        output_df = build_scores(master_df)

        final_cols = [
            "code",
            "ward_name",
            "population",
            "population_total",
            "ward_area_km2",
            "area_km2",
            "population_density",
            "avg_household_size",
            "score_accessibility",
            "score_safety",
            "score_convenience",
            "score_resilience",
            "score_affordability",
            "score_livability",
            "rent_monthly_avg",
            "time_to_tokyo_min",
            "time_to_shinjuku_min",
            "time_to_shibuya_min",
            "time_to_ikebukuro_min",
            "time_to_shinagawa_min",
            "avg_time_to_major_stations_min",
            "station_density",
            "supermarket_per_10k",
            "supermarket_per_km2",
            "convenience_store_count",
            "convenience_store_per_10k",
            "convenience_store_per_km2",
            "medical_facility_per_10k",
            "medical_facility_per_km2",
            "crime_total_count",
            "crime_total_per_10k",
            "crime_density_per_km2",
            "violent_crime_count",
            "violent_crime_per_10k",
            "theft_count",
            "theft_per_10k",
            "bicycle_theft_count",
            "bicycle_theft_per_10k",
            "burglary_count",
            "burglary_per_10k",
            "crime_yoy_rate",
            "flood_risk_area_ratio",
            "liquefaction_high_area_ratio",
            "shelter_per_10k",
            "shelter_density",
            "major_road_density",
            "park_area_total",
            "recommended_profile",
        ]

        final_df = output_df[final_cols]
        final_df.to_csv(temp_processed_path, index=False, encoding="utf-8-sig")

        for source_name, final_path in RAW_OUTPUT_PATHS.items():
            temp_raw_paths[source_name].replace(final_path)
            logging.info("Saved raw %s data: %s", source_name, final_path)
        temp_processed_path.replace(PROCESSED_OUTPUT_PATH)
        logging.info("Saved processed livability index: %s", PROCESSED_OUTPUT_PATH)

    # Automatically update assets/embedded-data.js with new data for offline fallback
    logging.info("Syncing processed data into assets/embedded-data.js...")
    try:
        embedded_data = {}
        csv_mappings = {
            "indexText": PROCESSED_OUTPUT_PATH,
            "estatText": RAW_OUTPUT_PATHS["estat"],
            "spatialText": RAW_OUTPUT_PATHS["spatial"],
            "crimeText": RAW_OUTPUT_PATHS["crime"],
            "poiText": RAW_OUTPUT_PATHS["osm"],
            "areaText": RAW_OUTPUT_PATHS["area"],
        }
        for key, path in csv_mappings.items():
            if path.exists():
                with open(path, "r", encoding="utf-8-sig") as f:
                    embedded_data[key] = f.read().replace("\ufeff", "")
            else:
                logging.warning("CSV path not found for embedding: %s", path)
                embedded_data[key] = ""

        geojson_path = DATA_RAW_DIR / "gis" / "tokyo_23wards.geojson"
        if geojson_path.exists():
            with open(geojson_path, "r", encoding="utf-8") as f:
                embedded_data["geojson"] = json.load(f)
        else:
            logging.warning("GeoJSON not found for embedding: %s", geojson_path)
            embedded_data["geojson"] = {}

        js_output_path = ROOT_DIR / "assets" / "embedded-data.js"
        js_content = f"window.TOKYO_LIVABILITY_EMBEDDED_DATA = {json.dumps(embedded_data, ensure_ascii=False)};\n"
        with open(js_output_path, "w", encoding="utf-8") as f:
            f.write(js_content)
        logging.info("Successfully updated assets/embedded-data.js")
    except Exception as exc:
        logging.error("Failed to update assets/embedded-data.js: %s", exc)

    print(final_df.head(5).to_string(index=False))
    return final_df


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
