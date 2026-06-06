import json
import logging
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.config import DATA_RAW_DIR, ROOT_DIR, TOKYO_23_WARDS

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

TOKYO_WARDS_GEOJSON = ROOT_DIR / "data" / "raw" / "gis" / "tokyo_23wards.geojson"
EARTH_RADIUS_KM = 6371.0088
TOKYO_REFERENCE_LATITUDE = math.radians(35.68)


def project_lon_lat(longitude, latitude):
    x = EARTH_RADIUS_KM * math.radians(longitude) * math.cos(TOKYO_REFERENCE_LATITUDE)
    y = EARTH_RADIUS_KM * math.radians(latitude)
    return x, y


def ring_area_km2(ring):
    """Approximate local projected ring area using lon/lat coordinates."""
    if len(ring) < 4:
        return 0.0

    projected = [project_lon_lat(lon, lat) for lon, lat in ring]
    origin_x, origin_y = projected[0]
    projected = [(x - origin_x, y - origin_y) for x, y in projected]
    total = 0.0
    for index, (x1, y1) in enumerate(projected):
        x2, y2 = projected[(index + 1) % len(projected)]
        total += x1 * y2 - x2 * y1

    return abs(total) / 2


def polygon_area_km2(polygon):
    if not polygon:
        return 0.0

    outer_area = ring_area_km2(polygon[0])
    holes_area = sum(ring_area_km2(ring) for ring in polygon[1:])
    area = outer_area - holes_area
    if area > 0:
        return area

    return sum(ring_area_km2(ring) for ring in polygon)


def geometry_area_km2(geometry):
    if geometry["type"] == "Polygon":
        return polygon_area_km2(geometry["coordinates"])
    if geometry["type"] == "MultiPolygon":
        return sum(polygon_area_km2(polygon) for polygon in geometry["coordinates"])
    raise ValueError(f"Unsupported geometry type: {geometry['type']}")


def fetch_area_data(output_path=None):
    """Calculate ward areas from the bundled Tokyo 23 ward GeoJSON."""
    if not TOKYO_WARDS_GEOJSON.exists():
        raise FileNotFoundError(f"Ward GeoJSON not found: {TOKYO_WARDS_GEOJSON}")

    with TOKYO_WARDS_GEOJSON.open(encoding="utf-8") as geojson_file:
        geojson = json.load(geojson_file)

    rows = []
    for feature in geojson.get("features", []):
        code = str(feature.get("properties", {}).get("code", ""))
        if code not in TOKYO_23_WARDS:
            continue

        area = round(geometry_area_km2(feature["geometry"]), 2)
        if area <= 0:
            raise ValueError(f"Calculated non-positive area for {code}.")

        rows.append(
            {
                "code": code,
                "ward_name": TOKYO_23_WARDS[code],
                "ward_area_km2": area,
            }
        )

    found_codes = {row["code"] for row in rows}
    missing_codes = sorted(set(TOKYO_23_WARDS) - found_codes)
    if missing_codes:
        missing_labels = ", ".join(
            f"{code}:{TOKYO_23_WARDS[code]}" for code in missing_codes
        )
        raise ValueError(f"Missing ward geometry for: {missing_labels}")

    df = pd.DataFrame(sorted(rows, key=lambda row: row["code"]))
    if output_path is None:
        output_path = DATA_RAW_DIR / "area_data.csv"
    output_path = Path(output_path)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    logging.info("Saved calculated ward area data: %s", output_path)
    return df


if __name__ == "__main__":
    fetch_area_data()
