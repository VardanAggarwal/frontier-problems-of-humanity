"""
Rainfall profile along the Ken-Betwa canal route (straight-line approximation)
and across the wider claimed-beneficiary district list.
Reuses the Open-Meteo historical archive API (ERA5-based), no key needed.
"""
import requests
import pandas as pd
import numpy as np
import time
import sys

BASE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Canal alignment anchor towns (documented waypoints)
CANAL_ANCHORS = [
    ("daudhan_dam_panna", 24.72, 80.18),
    ("chhatarpur", 24.92, 79.59),
    ("tikamgarh", 24.74, 78.83),
    ("lalitpur_terminus", 24.68, 78.41),
]

def interpolate(p1, p2, n):
    """n intermediate points strictly between p1 and p2 (exclusive)."""
    lat1, lon1 = p1
    lat2, lon2 = p2
    pts = []
    for i in range(1, n + 1):
        f = i / (n + 1)
        pts.append((lat1 + f * (lat2 - lat1), lon1 + f * (lon2 - lon1)))
    return pts

def build_canal_route():
    route = []
    dist_km_cum = 0.0
    coords_only = [(a[1], a[2]) for a in CANAL_ANCHORS]
    names = [a[0] for a in CANAL_ANCHORS]
    for i in range(len(coords_only) - 1):
        route.append((names[i], coords_only[i]))
        mids = interpolate(coords_only[i], coords_only[i + 1], 2)
        for j, m in enumerate(mids):
            route.append((f"{names[i]}_to_{names[i+1]}_mid{j+1}", m))
    route.append((names[-1], coords_only[-1]))
    return route

WIDER_DISTRICTS = {
    "sagar": (23.83, 78.74),
    "damoh": (23.83, 79.44),
    "datia": (25.68, 78.46),
    "shivpuri": (25.43, 77.66),
    "vidisha": (23.53, 77.81),
    "raisen": (23.39, 77.78),
    "banda": (25.48, 80.34),
    "mahoba": (25.29, 79.87),
    "jhansi": (25.45, 78.58),
}

def fetch_point(lat, lon, start, end, max_retries=5):
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
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Failed {lat},{lon}")

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
    route = build_canal_route()
    rows = []
    print(f"Fetching {len(route)} canal-route points...")
    for i, (name, (lat, lon)) in enumerate(route):
        df = fetch_point(lat, lon, "1981-01-01", "2025-12-31")
        recent = annual_means(df, 2016, 2025)
        base = annual_means(df, 1981, 1990)
        rows.append({
            "point": name, "lat": lat, "lon": lon, "route_order": i,
            "type": "canal_route",
            "mean_annual_mm_2016_2025": round(recent, 1),
            "mean_annual_mm_1981_1990": round(base, 1),
            "classification": classify(recent),
        })
        time.sleep(1)
    canal_df = pd.DataFrame(rows)
    canal_df.to_csv("canal_route_rainfall.csv", index=False)
    print(canal_df.to_string(index=False))

    rows2 = []
    print(f"\nFetching {len(WIDER_DISTRICTS)} wider-district points...")
    for name, (lat, lon) in WIDER_DISTRICTS.items():
        df = fetch_point(lat, lon, "1981-01-01", "2025-12-31")
        recent = annual_means(df, 2016, 2025)
        base = annual_means(df, 1981, 1990)
        rows2.append({
            "point": name, "lat": lat, "lon": lon,
            "type": "phase2_or_wider_district",
            "mean_annual_mm_2016_2025": round(recent, 1),
            "mean_annual_mm_1981_1990": round(base, 1),
            "classification": classify(recent),
        })
        time.sleep(1)
    wider_df = pd.DataFrame(rows2)
    wider_df.to_csv("wider_district_rainfall.csv", index=False)
    print(wider_df.to_string(index=False))

if __name__ == "__main__":
    run()
