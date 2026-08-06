"""
Rainfall across each KBLP command area's bounding box (3x3 grid per box,
0.15deg spacing), using the geo-boundaries in command_area_geoboundaries.md.
Reuses the Open-Meteo historical archive API (ERA5-based), no key needed.
"""
import requests
import pandas as pd
import numpy as np
import time
import sys

BASE_URL = "https://archive-api.open-meteo.com/v1/archive"

# name, table, cca_ha, bbox (lat_min, lat_max, lon_min, lon_max)
# boxes refined against the vectorized map's own swatches/grid (see
# command_area_geoboundaries.md); UP-C (Lalitpur, 3,533 ha) dropped as
# too small to matter; MP-B vs UP-A(i) split at the 25 deg N line.
COMMANDS = [
    ("MP-A_enroute", "kb_link_main", 96751, (25.2, 25.5, 78.7, 79.0)),
    ("MP-B_highlevel_daudhan_pump", "kb_link_main", 43678, (24.6, 24.9, 79.9, 80.1)),
    ("MP-C_highlevel_kblink_pump", "kb_link_main", 42096, (24.8, 24.95, 79.9, 80.0)),
    ("MP-D_panna_hatta_lis", "kb_link_main", 90101, (23.9, 24.6, 79.6, 80.3)),
    ("MP-E_ken_lbc", "kb_link_main", 174742, (24.7, 25.3, 79.9, 80.6)),
    ("UP-Ai_enroute_jhansi_mahoba", "kb_link_main", 17488, (25.0, 25.2, 79.7, 79.9)),
    ("UP-Aii_new_mahoba", "kb_link_main", 37564, (25.25, 25.4, 79.8, 80.0)),
    ("UP-B_bariarpur_rbc_banda", "kb_link_main", 192479, (25.3, 25.9, 80.2, 80.9)),
    ("B-A_lower_orr_enroute", "betwa_projects", 90000, (24.85, 25.35, 78.05, 78.55)),
    ("B-B_kotha_barrage", "betwa_projects", 20000, (23.75, 24.05, 77.85, 78.15)),
    ("B-C_bina_complex", "betwa_projects", 96000, (23.55, 23.95, 78.6, 78.95)),
]

def grid_3x3(bbox):
    lat_min, lat_max, lon_min, lon_max = bbox
    lat_c, lon_c = (lat_min + lat_max) / 2, (lon_min + lon_max) / 2
    pts = []
    for dlat in (-0.15, 0, 0.15):
        for dlon in (-0.15, 0, 0.15):
            pts.append((round(lat_c + dlat, 3), round(lon_c + dlon, 3)))
    return pts

def fetch_point(lat, lon, start, end, max_retries=8):
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": start, "end_date": end,
        "daily": "precipitation_sum", "timezone": "Asia/Kolkata",
    }
    for attempt in range(max_retries):
        try:
            r = requests.get(BASE_URL, params=params, timeout=60)
            if r.status_code == 200:
                data = r.json()
                daily = data["daily"]
                df = pd.DataFrame({
                    "date": pd.to_datetime(daily["time"]),
                    "precip_mm": daily["precipitation_sum"],
                })
                return df
            print(f"  status {r.status_code}, retry {attempt+1}", file=sys.stderr)
        except Exception as e:
            print(f"  error {e}, retry {attempt+1}", file=sys.stderr)
        time.sleep(5 * (attempt + 1))
    return None

def annual_means(df, y0, y1):
    d = df.copy()
    d["year"] = d["date"].dt.year
    ann = d.groupby("year")["precip_mm"].sum()
    return ann[(ann.index >= y0) & (ann.index <= y1)].mean()

def classify(mm):
    if mm < 800:
        return "water-stressed (<800mm)"
    elif mm < 900:
        return "borderline (800-900mm)"
    return "not water-stressed (>900mm)"

def run():
    rows = []
    total_pts = len(COMMANDS) * 9
    done = 0
    for name, table, cca, bbox in COMMANDS:
        for lat, lon in grid_3x3(bbox):
            df = fetch_point(lat, lon, "1981-01-01", "2025-12-31")
            done += 1
            if df is None:
                print(f"[{done}/{total_pts}] {name} ({lat},{lon}) -> FAILED, skipping")
                rows.append({
                    "command": name, "table": table, "cca_ha": cca,
                    "lat": lat, "lon": lon,
                    "mean_annual_mm_2016_2025": np.nan,
                    "mean_annual_mm_1981_1990": np.nan,
                    "classification": "fetch_failed",
                })
                time.sleep(2)
                continue
            recent = annual_means(df, 2016, 2025)
            base = annual_means(df, 1981, 1990)
            rows.append({
                "command": name, "table": table, "cca_ha": cca,
                "lat": lat, "lon": lon,
                "mean_annual_mm_2016_2025": round(recent, 1),
                "mean_annual_mm_1981_1990": round(base, 1),
                "classification": classify(recent),
            })
            print(f"[{done}/{total_pts}] {name} ({lat},{lon}) -> {round(recent,1)}mm recent / {round(base,1)}mm baseline")
            time.sleep(2)

    df_all = pd.DataFrame(rows)
    df_all.to_csv("command_area_grid_rainfall.csv", index=False)

    summary = df_all.groupby(["command", "table", "cca_ha"]).agg(
        mean_annual_mm_2016_2025=("mean_annual_mm_2016_2025", "mean"),
        mean_annual_mm_1981_1990=("mean_annual_mm_1981_1990", "mean"),
    ).reset_index()
    summary["mean_annual_mm_2016_2025"] = summary["mean_annual_mm_2016_2025"].round(1)
    summary["mean_annual_mm_1981_1990"] = summary["mean_annual_mm_1981_1990"].round(1)
    summary["classification"] = summary["mean_annual_mm_2016_2025"].apply(classify)
    summary.to_csv("command_area_summary_rainfall.csv", index=False)
    print("\n=== Per-command box average ===")
    print(summary.to_string(index=False))

if __name__ == "__main__":
    run()
