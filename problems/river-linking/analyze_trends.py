"""
Analyze Ken vs Betwa basin rainfall trends 1981-2025:
- annual & monsoon (Jun-Sep) totals per basin
- Mann-Kendall trend test (manual implementation)
- linear regression slope + p-value
- decade comparison: 1981-1990 vs 2016-2025
"""
import pandas as pd
import numpy as np
from scipy import stats

def mann_kendall(x):
    x = np.asarray(x)
    n = len(x)
    s = 0
    for k in range(n - 1):
        s += np.sum(np.sign(x[k+1:] - x[k]))
    # variance (no tie correction needed for float rainfall totals, ties unlikely)
    var_s = n * (n - 1) * (2 * n + 5) / 18.0
    if s > 0:
        z = (s - 1) / np.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / np.sqrt(var_s)
    else:
        z = 0
    p = 2 * (1 - stats.norm.cdf(abs(z)))
    return s, z, p


def annual_and_monsoon(df):
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    # drop incomplete years (1981 and 2025 should be complete per request, but check)
    annual = df.groupby("year")["basin_avg_mm"].sum()
    monsoon = df[df["month"].between(6, 9)].groupby("year")["basin_avg_mm"].sum()
    return annual, monsoon


def report(name, series, label):
    years = series.index.values
    vals = series.values
    s, z, p = mann_kendall(vals)
    slope, intercept, r, p_lr, se = stats.linregress(years, vals)
    dec1 = series[(series.index >= 1981) & (series.index <= 1990)].mean()
    dec2 = series[(series.index >= 2016) & (series.index <= 2025)].mean()
    pct_change = (dec2 - dec1) / dec1 * 100
    print(f"\n--- {name} ({label}) ---")
    print(f"years: {years.min()}-{years.max()}, n={len(years)}")
    print(f"Mann-Kendall: S={s}, Z={z:.3f}, p={p:.4f} -> {'significant' if p<0.05 else 'not significant'} "
          f"({'increasing' if s>0 else 'decreasing' if s<0 else 'no trend'})")
    print(f"Linear trend: slope={slope:.2f} mm/year, p={p_lr:.4f}")
    print(f"1981-1990 mean: {dec1:.0f} mm | 2016-2025 mean: {dec2:.0f} mm | change: {pct_change:+.1f}%")
    return {
        "mk_s": s, "mk_z": z, "mk_p": p,
        "lr_slope": slope, "lr_p": p_lr,
        "dec1_mean": dec1, "dec2_mean": dec2, "pct_change": pct_change,
    }


if __name__ == "__main__":
    ken = pd.read_csv("/Users/vardanaggarwal/fph/problems/river-linking/ken_basin_rainfall.csv")
    betwa = pd.read_csv("/Users/vardanaggarwal/fph/problems/river-linking/betwa_basin_rainfall.csv")

    ken_annual, ken_monsoon = annual_and_monsoon(ken)
    betwa_annual, betwa_monsoon = annual_and_monsoon(betwa)

    print("=" * 60)
    print("KEN BASIN")
    print("=" * 60)
    r1 = report("Ken", ken_annual, "annual")
    r2 = report("Ken", ken_monsoon, "monsoon Jun-Sep")

    print("\n" + "=" * 60)
    print("BETWA BASIN")
    print("=" * 60)
    r3 = report("Betwa", betwa_annual, "annual")
    r4 = report("Betwa", betwa_monsoon, "monsoon Jun-Sep")

    print("\n" + "=" * 60)
    print("KEN vs BETWA — relative surplus check")
    print("=" * 60)
    ratio_annual_early = ken_annual[(ken_annual.index>=1981)&(ken_annual.index<=1990)].mean() / \
                          betwa_annual[(betwa_annual.index>=1981)&(betwa_annual.index<=1990)].mean()
    ratio_annual_late = ken_annual[(ken_annual.index>=2016)&(ken_annual.index<=2025)].mean() / \
                         betwa_annual[(betwa_annual.index>=2016)&(betwa_annual.index<=2025)].mean()
    print(f"Ken/Betwa annual rainfall ratio 1981-90: {ratio_annual_early:.3f}")
    print(f"Ken/Betwa annual rainfall ratio 2016-25: {ratio_annual_late:.3f}")
    print(f"Ratio change: {(ratio_annual_late-ratio_annual_early)/ratio_annual_early*100:+.1f}%")
