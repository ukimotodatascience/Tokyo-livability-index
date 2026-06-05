import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

DATA_DIR = ROOT_DIR / "data"
DATA_RAW_DIR = DATA_DIR / "raw"
DATA_PROCESSED_DIR = DATA_DIR / "processed"

DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

ESTAT_API_KEY = os.getenv("ESTAT_API_KEY", "")
ESTAT_API_URL = "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData"

OVERPASS_API_URL = "https://overpass-api.de/api/interpreter"

CRIME_DATA_URL = (
    "https://www.keishicho.metro.tokyo.lg.jp/about_mpd/jokyo_tokei/"
    "jokyo/ninchikensu.files/R5.csv"
)

TOKYO_23_WARDS = {
    "13101": "千代田区",
    "13102": "中央区",
    "13103": "港区",
    "13104": "新宿区",
    "13105": "文京区",
    "13106": "台東区",
    "13107": "墨田区",
    "13108": "江東区",
    "13109": "品川区",
    "13110": "目黒区",
    "13111": "大田区",
    "13112": "世田谷区",
    "13113": "渋谷区",
    "13114": "中野区",
    "13115": "杉並区",
    "13116": "豊島区",
    "13117": "北区",
    "13118": "荒川区",
    "13119": "板橋区",
    "13120": "練馬区",
    "13121": "足立区",
    "13122": "葛飾区",
    "13123": "江戸川区",
}

WARD_NAMES = set(TOKYO_23_WARDS.values())
