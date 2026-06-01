import os
import requests
import json
from pathlib import Path

# e-Stat API 設定
ESTAT_API_KEY = os.getenv("ESTAT_API_KEY", "")
ESTAT_API_URL = "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData"

TOKYO_23_WARDS = {"13101": "千代田区", "13102": "中央区"}


def test_api():
    if not ESTAT_API_KEY:
        print("ESTAT_API_KEY is not defined in env")
        return

    print(
        f"Using ESTAT_API_KEY: {ESTAT_API_KEY[:3]}***{ESTAT_API_KEY[-3:] if len(ESTAT_API_KEY) > 6 else '***'}"
    )

    # 接続テスト
    params = {
        "appId": ESTAT_API_KEY,
        "statsDataId": "0003445076",
        "cdArea": ",".join(TOKYO_23_WARDS.keys()),
        "metaGetFlg": "Y",
        "cntGetFlg": "N",
    }

    try:
        response = requests.get(ESTAT_API_URL, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        # キー構造を表示
        print("Root keys:", data.keys())
        if "GET_STATS_DATA" in data:
            gsd = data["GET_STATS_DATA"]
            print("GET_STATS_DATA keys:", gsd.keys())
            if "RESULT" in gsd:
                print("RESULT status:", gsd["RESULT"])
            if "STATISTICAL_DATA" in gsd:
                sd = gsd["STATISTICAL_DATA"]
                print("STATISTICAL_DATA keys:", sd.keys())
                if "CLASS_INF" in sd:
                    class_info_path = (
                        Path(__file__).resolve().parent / "estat_class_info.json"
                    )
                    with open(class_info_path, "w", encoding="utf-8") as f:
                        json.dump(sd["CLASS_INF"], f, indent=2, ensure_ascii=False)
                    print(f"CLASS_INF details written to {class_info_path}")
                if "DATA_INF" in sd:
                    print("DATA_INF keys:", sd["DATA_INF"].keys())
                    if "VALUE" in sd["DATA_INF"]:
                        print("Number of VALUE records:", len(sd["DATA_INF"]["VALUE"]))
                        print("First 3 VALUE records:")
                        print(
                            json.dumps(
                                sd["DATA_INF"]["VALUE"][:3],
                                indent=2,
                                ensure_ascii=False,
                            )
                        )

    except Exception as e:
        print("API request failed:", e)


if __name__ == "__main__":
    test_api()
