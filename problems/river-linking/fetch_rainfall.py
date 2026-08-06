"""
Pull daily precipitation from Open-Meteo historical archive API (ERA5-based)
for representative points across the Ken and Betwa river basins, 1981-2025.
No API key needed. Saves per-basin daily CSVs (averaged across basin points).
"""
import requests
import pandas as pd
import time
import sys

KEN_POINTS = {
    "panna": (24.72, 80.18),
    "chhatarpur": (24.92, 79.59),
    "damoh": (23.83, 79.44),
    "sagar": (23.83, 78.74),
    "banda_confluence": (25.5, 80.4),
}

BETWA_POINTS = {
    "vidisha": (23.53, 77.81),
    "raisen": (23.39, 77.78),
    "jhansi": (25.45, 78.58),
    "tikamgarh": (24.74, 78.83),
    "betul_origin": (23.0, 78.0),
}

START = "1981-01-01"
END = "2025-12-31"
BASE_URL = "https://archive-api.open-meteo.com/v1/archive"


def fetch_point(lat, lon, start=START, end=END, max_retries=5):
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start,
        "end_date": end,
        "daily": "precipitation_sum",
        "timezone": "Asia/Kolkata",
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
            else:
                print(f"  status {r.status_code}, retry {attempt+1}", file=sys.stderr)
        except Exception as e:
            print(f"  error {e}, retry {attempt+1}", file=sys.stderr)
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {lat},{lon} after {max_retries} retries")


def fetch_basin(points, name):
    frames = []
    for pname, (lat, lon) in points.items():
        print(f"Fetching {name}/{pname} ({lat},{lon})...")
        df = fetch_point(lat, lon)
        df = df.rename(columns={"precip_mm": pname})
        frames.append(df.set_index("date"))
        time.sleep(1.5)  # be polite
    merged = pd.concat(frames, axis=1)
    merged["basin_avg_mm"] = merged.mean(axis=1)
    merged = merged.reset_index()
    return merged


if __name__ == "__main__":
    ken_df = fetch_basin(KEN_POINTS, "ken")
    ken_df.to_csv("/Users/vardanaggarwal/fph/problems/river-linking/ken_basin_rainfall.csv", index=False)
    print(f"Saved Ken basin rainfall: {len(ken_df)} rows")

    betwa_df = fetch_basin(BETWA_POINTS, "betwa")
    betwa_df.to_csv("/Users/vardanaggarwal/fph/problems/river-linking/betwa_basin_rainfall.csv", index=False)
    print(f"Saved Betwa basin rainfall: {len(betwa_df)} rows")
