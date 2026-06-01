import logging
import random
import sys
from pathlib import Path
import pandas as pd
import requests
from io import StringIO

# プロジェクトのルートディレクトリを sys.path に追加
sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.config import CRIME_DATA_URL, DATA_RAW_DIR, TOKYO_23_WARDS

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

# 23区別のリアルな年間犯罪発生件数の目安（治安状況のモックデータ用）
# 人口あたりの犯罪率を表現するための、おおよその年間刑法犯認知件数
MOCK_CRIME_STATS = {
    "13101": {
        "total_crime": 2500,
        "serious_crime": 35,
    },  # 千代田区 (昼間人口が多く犯罪率は高め)
    "13102": {"total_crime": 2100, "serious_crime": 20},  # 中央区
    "13103": {"total_crime": 3200, "serious_crime": 45},  # 港区
    "13104": {
        "total_crime": 5800,
        "serious_crime": 95,
    },  # 新宿区 (歌舞伎町などがあり認知件数最多)
    "13105": {
        "total_crime": 1100,
        "serious_crime": 10,
    },  # 文京区 (最も治安が良いとされる)
    "13106": {
        "total_crime": 3100,
        "serious_crime": 40,
    },  # 台東区 (上野・浅草があり人口比では高め)
    "13107": {"total_crime": 2200, "serious_crime": 25},  # 墨田区
    "13108": {"total_crime": 2900, "serious_crime": 30},  # 江東区
    "13109": {"total_crime": 2300, "serious_crime": 25},  # 品川区
    "13110": {"total_crime": 1600, "serious_crime": 15},  # 目黒区
    "13111": {"total_crime": 4500, "serious_crime": 40},  # 大田区
    "13112": {
        "total_crime": 4800,
        "serious_crime": 45,
    },  # 世田谷区 (分母人口が多いが治安は良い)
    "13113": {"total_crime": 4900, "serious_crime": 75},  # 渋谷区 (繁華街があり多め)
    "13114": {"total_crime": 2100, "serious_crime": 20},  # 中野区
    "13115": {
        "total_crime": 2300,
        "serious_crime": 20,
    },  # 杉並区 (閑静な住宅街で治安良好)
    "13116": {"total_crime": 4200, "serious_crime": 60},  # 豊島区 (池袋があり多め)
    "13117": {"total_crime": 2000, "serious_crime": 18},  # 北区
    "13118": {"total_crime": 1400, "serious_crime": 12},  # 荒川区
    "13119": {"total_crime": 3300, "serious_crime": 30},  # 板橋区
    "13120": {"total_crime": 2900, "serious_crime": 25},  # 練馬区 (治安良好)
    "13121": {
        "total_crime": 5200,
        "serious_crime": 65,
    },  # 足立区 (件数自体は多めだが近年は減少傾向)
    "13122": {"total_crime": 3600, "serious_crime": 35},  # 葛飾区
    "13123": {"total_crime": 4300, "serious_crime": 40},  # 江戸川区
}


def generate_mock_data():
    """リアルな治安データをモック生成してCSVに保存する"""
    logging.info("犯罪データのモックデータを生成します。")

    rows = []
    for code, name in TOKYO_23_WARDS.items():
        stats = MOCK_CRIME_STATS[code]
        # 1〜5%程度のランダム揺らぎを追加
        total = int(stats["total_crime"] * random.uniform(0.95, 1.05))
        serious = int(stats["serious_crime"] * random.uniform(0.95, 1.05))

        # 罪種別（非侵入窃盗、粗暴犯等）の内訳を適当に割り振り
        violent_crime = int(total * random.uniform(0.10, 0.15))
        theft_crime = int(total * random.uniform(0.65, 0.75))
        other_crime = total - violent_crime - theft_crime

        rows.append(
            {
                "code": code,
                "ward_name": name,
                "total_crime_cases": total,
                "serious_crime_cases": serious,
                "violent_crime_cases": violent_crime,
                "theft_crime_cases": theft_crime,
                "other_crime_cases": other_crime,
            }
        )

    df = pd.DataFrame(rows)
    output_path = DATA_RAW_DIR / "crime_data.csv"
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    logging.info(f"犯罪データを保存しました: {output_path}")
    return df


def fetch_crime_data(use_demo=False):
    """東京都オープンデータ（警視庁）から犯罪統計を取得する。失敗時やデモモードはモックにフォールバック。"""
    if use_demo:
        return generate_mock_data()

    logging.info(
        f"警視庁公式サイトから最新の犯罪データをダウンロードします: {CRIME_DATA_URL}"
    )
    try:
        response = requests.get(CRIME_DATA_URL, timeout=15)
        response.raise_for_status()

        # エンコーディングは Shift_JIS (cp932) でパース
        content = response.content.decode("cp932", errors="ignore")

        # CSVを読み込む
        df_raw = pd.read_csv(StringIO(content))

        # カラム名のクリーニング（余分な空白の削除など）
        df_raw.columns = df_raw.columns.str.strip()

        # 実CSVのパース・集計
        if "市区町丁" in df_raw.columns and "総合計" in df_raw.columns:
            logging.info("本物の犯罪データCSVのパースを開始します...")

            # 各行の市区町丁がどの23区に属するか判定するヘルパー関数
            def map_to_ward(address):
                if not isinstance(address, str):
                    return None
                for code, name in TOKYO_23_WARDS.items():
                    if address.startswith(name):
                        return name
                return None

            df_raw["ward_name"] = df_raw["市区町丁"].apply(map_to_ward)

            # 23区に属する行のみ抽出
            df_wards = df_raw[df_raw["ward_name"].notna()].copy()

            # 各犯罪項目の数値化（カンマ除去等）
            numeric_cols = [
                "総合計",
                "凶悪犯計",
                "粗暴犯計",
                "侵入窃盗計",
                "非侵入窃盗計",
                "その他計",
            ]
            for col in numeric_cols:
                if col in df_wards.columns:
                    df_wards[col] = (
                        df_wards[col].astype(str).str.replace(",", "").str.strip()
                    )
                    df_wards[col] = (
                        pd.to_numeric(df_wards[col], errors="coerce")
                        .fillna(0)
                        .astype(int)
                    )

            # 区ごとにグループ化して集計
            grouped = df_wards.groupby("ward_name").sum(numeric_only=True).reset_index()

            # 23区コードのマッピング
            ward_to_code = {name: code for code, name in TOKYO_23_WARDS.items()}
            grouped["code"] = grouped["ward_name"].map(ward_to_code)

            # 出力用カラムにマッピング
            grouped["total_crime_cases"] = grouped["総合計"]
            grouped["serious_crime_cases"] = grouped["凶悪犯計"]
            grouped["violent_crime_cases"] = grouped["粗暴犯計"]
            grouped["theft_crime_cases"] = (
                grouped["侵入窃盗計"] + grouped["非侵入窃盗計"]
            )
            grouped["other_crime_cases"] = grouped["その他計"]

            final_cols = [
                "code",
                "ward_name",
                "total_crime_cases",
                "serious_crime_cases",
                "violent_crime_cases",
                "theft_crime_cases",
                "other_crime_cases",
            ]
            df_result = grouped[final_cols].copy()

            # 23区すべてが揃っているか確認
            if len(df_result) == 23:
                output_path = DATA_RAW_DIR / "crime_data.csv"
                df_result.to_csv(output_path, index=False, encoding="utf-8-sig")
                logging.info(
                    f"本物の犯罪データを正常に集計・保存しました: {output_path}"
                )
                return df_result
            else:
                logging.warning(
                    f"集計された区の数（{len(df_result)}）が23区と一致しません。モックにフォールバックします。"
                )
                return generate_mock_data()
        else:
            raise ValueError("CSVに必要なカラム（市区町丁, 総合計）が見つかりません。")

    except Exception as e:
        logging.error(
            f"犯罪データのダウンロード・パース中にエラーが発生しました: {e}。モックデータにフォールバックします。"
        )
        return generate_mock_data()


if __name__ == "__main__":
    fetch_crime_data(use_demo=True)
