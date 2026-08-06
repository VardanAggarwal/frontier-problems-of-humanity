# Ken vs Betwa rainfall trend check (cheap public-data pass)

Question: does the 1980 National Perspective Plan's "Ken = surplus, Betwa = deficit"
classification still make sense, using only rainfall as a cheap proxy for river flow?

## Method
- Data: Open-Meteo historical archive API (ERA5 reanalysis-based), daily precipitation,
  1981-01-01 to 2025-12-31, no API key needed.
- 5 representative points per basin (Ken: Panna, Chhatarpur, Damoh, Sagar, Banda/confluence
  area; Betwa: Vidisha, Raisen, Jhansi, Tikamgarh, Betul/origin area), simple average = basin proxy.
- Annual and monsoon (Jun-Sep) totals per year, per basin.
- Trend tests: Mann-Kendall (rank-based, robust to non-normality) + linear regression slope.
- Magnitude check: 1981-1990 mean vs 2016-2025 mean.

## Findings

**Both basins show a statistically significant increasing rainfall trend since 1981** —
this is consistent with well-documented broader trends of intensifying Indian monsoon
rainfall in central India in recent decades. Not basin-specific behavior.

| Basin | Period | MK p-value | Trend | Slope (mm/yr) | 1981-90 mean | 2016-25 mean | Change |
|---|---|---|---|---|---|---|---|
| Ken | annual | 0.0027 | increasing | +7.15 | 940 mm | 1213 mm | +29.0% |
| Ken | monsoon | 0.0056 | increasing | +6.37 | 838 mm | 1103 mm | +31.7% |
| Betwa | annual | 0.0008 | increasing | +9.59 | 931 mm | 1277 mm | +37.2% |
| Betwa | monsoon | 0.0009 | increasing | +9.50 | 837 mm | 1192 mm | +42.4% |

**The key comparative signal:** Betwa's rainfall is increasing *faster* than Ken's.

- Ken/Betwa annual rainfall ratio, 1981-90: **1.010** (roughly equal — matches the
  original "similar rainfall, different downstream demand" framing that historically
  justified the surplus/deficit split being about basin size/demand, not rainfall).
- Ken/Betwa annual rainfall ratio, 2016-25: **0.950** — Betwa now receives ~5-6% *more*
  rainfall than Ken on average, a reversal from parity.

**Directional read:** this cheap pass does **not** support "Ken has dried up while Betwa
stayed dry" — both are wetter than the 1980s baseline. But it mildly undercuts the
surplus/deficit framing from a different angle: if Betwa's own rainfall has grown even
more than Ken's, the case that Betwa structurally *needs* imported water (rather than
better local capture/storage of its own increased rainfall) looks weaker than it did in
1980, not stronger.

## Caveats (read before citing this anywhere)

- **This is rainfall, not streamflow.** The 1980 surplus/deficit classification was built
  on measured discharge, not rainfall. Land-use change, groundwater extraction, deforestation,
  and evapotranspiration changes all break the rainfall→flow relationship, potentially
  significantly. A rainfall increase does not guarantee a proportional runoff/discharge
  increase — could be absorbed by higher ET, more groundwater draw, degraded infiltration, etc.
- **ERA5-based reanalysis (which Open-Meteo's archive uses) has known biases vs. ground
  stations in India**, especially pre-2000 and in complex terrain — treat magnitudes as
  approximate, trend *direction* as the more trustworthy signal.
- **5 points per basin is a coarse proxy**, not a proper area-weighted basin average.
  Basin boundaries weren't rigorously delineated (used rough town coordinates, not actual
  watershed shapefiles).
- This is a directional gut-check, explicitly not a rigorous hydrological study.

## Next step (full version, ~3-4 weeks) needed to actually confirm/refute

To turn this into something citable, need actual discharge data:
- CWC/India-WRIS gauge records for Ken (e.g. Bariarpur) and Betwa, daily/monthly, as long
  a record as available.
- Proper basin delineation (HydroSHEDS or WRIS watershed boundaries) for area-weighted
  rainfall aggregation instead of point sampling.
- A real water-balance model (rainfall - ET - storage change = runoff) rather than rainfall
  alone, to see whether increased rainfall is translating into increased river flow or
  being absorbed elsewhere (groundwater, agriculture, evapotranspiration).

## Files
- `fetch_rainfall.py` — pulls data, saves basin CSVs
- `analyze_trends.py` — trend tests + comparison
- `ken_basin_rainfall.csv`, `betwa_basin_rainfall.csv` — raw daily data per point + basin average
