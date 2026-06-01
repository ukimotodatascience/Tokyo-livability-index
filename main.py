import argparse
import logging
import sys
from pathlib import Path

# プロジェクトのルートディレクトリを sys.path に追加
sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.config import DATA_PROCESSED_DIR
from src.estat_collector import fetch_estat_data
from src.crime_collector import fetch_crime_data
from src.osm_collector import fetch_osm_data
from src.spatial_collector import fetch_spatial_data

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)


def min_max_normalize(series, invert=False):
    """シリーズの値を0〜1に正規化する。invert=Trueで悪い指標を良いスコアに反転する。"""
    min_val = series.min()
    max_val = series.max()

    if max_val == min_val:
        return series.apply(lambda x: 0.5)

    normalized = (series - min_val) / (max_val - min_val)
    if invert:
        return 1.0 - normalized
    return normalized


def add_ward_characteristics(df):
    """各区のスコア特徴から、一人暮らし向きの推薦文/特徴テキストを追加する"""
    characteristics = []
    for _, row in df.iterrows():
        afford = row["score_affordability"]
        access = row["score_accessibility"]
        safety = row["score_safety"]
        conv = row["score_convenience"]

        # スコアに基づいた推薦ロジック
        traits = []
        if afford >= 0.8:
            traits.append("家賃が非常に安く、初期費用を抑えたいコスパ重視派に最適。")
        elif afford <= 0.2:
            traits.append(
                "家賃相場は非常に高いが、それに見合うステータスと高い利便性がある。"
            )

        if access >= 0.8:
            traits.append(
                "主要駅へのアクセスが抜群で、通勤・通学やアクティブな移動が多い人向き。"
            )

        if safety >= 0.8:
            traits.append(
                "治安が極めて良く静かで、初めての一人暮らしや女性にも非常に安心。"
            )
        elif safety <= 0.3:
            traits.append(
                "人通りが多く賑やかだが、防犯意識や住むエリアの選定は念入りに。"
            )

        if conv >= 0.8:
            traits.append(
                "コンビニ・スーパーや医療機関が密集しており、日々の生活で不便を感じない。"
            )

        if len(traits) == 0:
            traits.append(
                "家賃・治安・利便性のバランスが取れており、誰にでも住みやすいエリア。"
            )

        characteristics.append(" ".join(traits))

    df["recommended_profile"] = characteristics
    return df


def run_pipeline(use_demo=False):
    logging.info("=========================================")
    logging.info("🚀 東京23区住みやすさインデックス データパイプライン起動")
    logging.info("=========================================")

    # 1. 各データソースからデータを収集
    logging.info("Step 1: 各オープンデータソースから収集を開始します...")

    estat_df = fetch_estat_data(use_demo=use_demo)
    crime_df = fetch_crime_data(use_demo=use_demo)
    osm_df = fetch_osm_data(use_demo=use_demo)
    spatial_df = fetch_spatial_data(use_demo=use_demo)

    # 2. データのマージ
    logging.info("Step 2: 収集したデータを区コード（JISコード）でマージします...")

    # codeを文字列型に統一
    estat_df["code"] = estat_df["code"].astype(str)
    crime_df["code"] = crime_df["code"].astype(str)
    osm_df["code"] = osm_df["code"].astype(str)
    spatial_df["code"] = spatial_df["code"].astype(str)

    master_df = estat_df.merge(
        crime_df.drop(columns=["ward_name"]), on="code", how="outer"
    )
    master_df = master_df.merge(
        osm_df.drop(columns=["ward_name"]), on="code", how="outer"
    )
    master_df = master_df.merge(
        spatial_df.drop(columns=["ward_name"]), on="code", how="outer"
    )

    # 3. 生指標から比較用の密度/比率指標を加工算出
    logging.info("Step 3: 比較用の中間指標（密度、発生率など）を加工算出します...")

    # 面積あたりの駅密度・施設密度
    master_df["station_density"] = (
        master_df["station_count"] / master_df["average_floor_space"]
    )
    master_df["convenience_density"] = (
        master_df["convenience_count"] / master_df["average_floor_space"]
    )
    master_df["supermarket_density"] = (
        master_df["supermarket_count"] / master_df["average_floor_space"]
    )
    master_df["medical_density"] = (
        master_df["medical_facility_count"] / master_df["average_floor_space"]
    )
    master_df["daily_facility_density"] = (
        master_df["daily_facility_count"] / master_df["average_floor_space"]
    )

    # 人口あたりの犯罪率 (人口1,000人あたり)
    master_df["crime_rate_per_1000"] = (
        master_df["total_crime_cases"] / master_df["population"]
    ) * 1000
    master_df["serious_crime_rate_per_10000"] = (
        master_df["serious_crime_cases"] / master_df["population"]
    ) * 10000

    # 人口あたりの避難所数 (人口10,000人あたり)
    master_df["shelter_rate_per_10000"] = (
        master_df["shelter_count"] / master_df["population"]
    ) * 10000

    # 家賃負担感指標 (家賃 / 所得 proxy)
    # ※所得単位は万円、家賃は円なので調整
    master_df["rent_burden_index"] = master_df["average_rent"] / (
        master_df["income_proxy"] * 10000
    )

    # 4. 指標の正規化 (0.0 〜 1.0)
    logging.info("Step 4: 各種指標を0〜1の範囲に正規化します...")

    # 4.1 住居コスト関連
    master_df["norm_rent"] = min_max_normalize(
        master_df["average_rent"], invert=True
    )  # 低いほど高得点
    master_df["norm_single_house_rate"] = min_max_normalize(
        master_df["single_household_rate"], invert=False
    )
    master_df["norm_rent_burden"] = min_max_normalize(
        master_df["rent_burden_index"], invert=True
    )  # 低いほど高得点

    # 4.2 交通利便性関連
    master_df["norm_station_density"] = min_max_normalize(
        master_df["station_density"], invert=False
    )
    master_df["norm_line_count"] = min_max_normalize(
        master_df["line_count"], invert=False
    )
    master_df["norm_access_time"] = min_max_normalize(
        master_df["average_access_time_min"], invert=True
    )  # 短いほど高得点

    # 4.3 治安関連
    master_df["norm_total_crime"] = min_max_normalize(
        master_df["crime_rate_per_1000"], invert=True
    )  # 低いほど高得点
    master_df["norm_serious_crime"] = min_max_normalize(
        master_df["serious_crime_rate_per_10000"], invert=True
    )

    # 4.4 生活利便性関連
    master_df["norm_convenience"] = min_max_normalize(
        master_df["convenience_density"], invert=False
    )
    master_df["norm_supermarket"] = min_max_normalize(
        master_df["supermarket_density"], invert=False
    )
    master_df["norm_medical"] = min_max_normalize(
        master_df["medical_density"], invert=False
    )
    master_df["norm_daily_access"] = min_max_normalize(
        master_df["daily_facility_density"], invert=False
    )

    # 4.5 居住環境関連
    master_df["norm_single_household"] = min_max_normalize(
        master_df["single_household_rate"], invert=False
    )
    master_df["norm_floor_space"] = min_max_normalize(
        master_df["average_floor_space"], invert=False
    )
    # 築年や公園面積は、今回は簡易的に単身世帯比率と部屋面積の平均で代替補正
    master_df["norm_livability_comfort"] = (
        master_df["norm_single_household"] + master_df["norm_floor_space"]
    ) / 2

    # 4.6 リスク関連
    master_df["norm_flood_risk"] = min_max_normalize(
        master_df["flood_risk_area_rate"], invert=True
    )  # 低いほど高得点
    master_df["norm_earthquake_risk"] = min_max_normalize(
        master_df["earthquake_hazard_rank"], invert=True
    )
    master_df["norm_shelter"] = min_max_normalize(
        master_df["shelter_rate_per_10000"], invert=False
    )

    # 5. カテゴリスコアの計算 (設計書に基づく重み付き平均)
    logging.info(
        "Step 5: 設計書で定義された重みに基づいてカテゴリ別スコアを計算します..."
    )

    # 5.1 住居コスト
    master_df["score_affordability"] = (
        0.5 * master_df["norm_rent"]
        + 0.3 * master_df["norm_single_house_rate"]
        + 0.2 * master_df["norm_rent_burden"]
    )

    # 5.2 交通利便性
    master_df["score_accessibility"] = (
        0.4 * master_df["norm_station_density"]
        + 0.2 * master_df["norm_line_count"]
        + 0.4 * master_df["norm_access_time"]
    )

    # 5.3 治安
    master_df["score_safety"] = (
        0.7 * master_df["norm_total_crime"] + 0.3 * master_df["norm_serious_crime"]
    )

    # 5.4 生活利便性
    master_df["score_convenience"] = (
        0.25 * master_df["norm_convenience"]
        + 0.25 * master_df["norm_supermarket"]
        + 0.30 * master_df["norm_medical"]
        + 0.20 * master_df["norm_daily_access"]
    )

    # 5.5 居住環境
    master_df["score_livability"] = (
        0.30 * master_df["norm_single_household"]
        + 0.25 * master_df["norm_floor_space"]
        + 0.45 * master_df["norm_livability_comfort"]
    )

    # 5.6 レジリエンス(リスク)
    master_df["score_resilience"] = (
        0.40 * master_df["norm_flood_risk"]
        + 0.30 * master_df["norm_earthquake_risk"]
        + 0.30 * master_df["norm_shelter"]
    )

    # 6. 特徴要約・おすすめプロファイルの追加
    master_df = add_ward_characteristics(master_df)

    # 7. スコア出力用にカラムを厳選して整理
    final_cols = [
        "code",
        "ward_name",
        "population",
        "average_rent",
        "score_affordability",
        "score_accessibility",
        "score_safety",
        "score_convenience",
        "score_livability",
        "score_resilience",
        "recommended_profile",
    ]

    output_df = master_df[final_cols].copy()

    # 各スコアをわかりやすく100点満点表記（小数第1位）に変換
    score_cols = [col for col in output_df.columns if col.startswith("score_")]
    for col in score_cols:
        output_df[col] = (output_df[col] * 100).round(1)

    output_path = DATA_PROCESSED_DIR / "tokyo_livability_index.csv"
    output_df.to_csv(output_path, index=False, encoding="utf-8-sig")

    logging.info("=========================================")
    logging.info("🎉 処理が完了しました！")
    logging.info(f"保存先: {output_path}")
    logging.info("=========================================")

    # プレビュー表示
    print("\n【出力データプレビュー (一部)】")
    print(output_df.head(5).to_string(index=False))
    return output_df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="東京23区住みやすさインデックス集計パイプライン"
    )
    parser.add_argument(
        "--real",
        action="store_true",
        default=False,
        help="モックではなく実データ（e-Stat API, OSM等）を使用して実行する",
    )
    args = parser.parse_args()

    # --real が指定された場合は実データモード（use_demo=False）、指定なしはデモモード（use_demo=True）
    use_demo = not args.real
    run_pipeline(use_demo=use_demo)
