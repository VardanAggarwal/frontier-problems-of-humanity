# Rainfall profile along the Ken-Betwa canal route + wider beneficiary districts

Extends `results.md` (basin-level Ken vs Betwa trend check) with a route-level and
wider-beneficiary-district view. Data: Open-Meteo historical archive API (ERA5-based),
1981-2025, `precipitation_sum` daily, aggregated to annual totals.

## Method

- **Canal route**: approximated as a straight line through 4 documented anchor towns —
  Daudhan Dam/Panna (24.72, 80.18) -> Chhatarpur (24.92, 79.59) -> Tikamgarh (24.74, 78.83)
  -> Lalitpur terminus (24.68, 78.41) — with 2 interpolated midpoints per segment (10 points total).
  **This is NOT the true engineered canal alignment** (which follows terrain contours, not
  straight lines) — treat as a coarse proxy only.
- **Wider beneficiary districts**: single centroid point per district for Sagar, Damoh, Datia,
  Shivpuri, Vidisha, Raisen, Banda, Mahoba, Jhansi — none of these are on the direct canal
  physical path; official material bundles them in as "beneficiaries" via separate Phase-II
  dams/barrages on Betwa's own tributaries (Lower Orr, Kotha, Barari, Neemkheda, Kesari), not
  via direct Ken water transfer. That bundling is itself part of what critics (SANDRP, IndiaSpend)
  contest — it is not a settled fact, so the on-canal / off-canal distinction is kept explicit
  throughout.
- Threshold used: <800mm/yr = water-stressed, 800-900mm = borderline, >900mm = not water-stressed
  (consistent with the earlier "Vidisha/Raisen already get 900mm+" claim from this conversation).

Data: `canal_route_rainfall.csv`, `wider_district_rainfall.csv`. Script: `fetch_route_rainfall.py`.

## Headline finding

**Every single point sampled — all 10 canal-route points and all 9 wider-district points —
classifies as "not water-stressed" (>900mm) in the 2016-2025 recent-decade mean.** Recent-decade
annual totals range from ~935mm (Shivpuri) to ~1386mm (Raisen), i.e. the entire route and the
entire wider beneficiary list now sit above the 900mm threshold. On this simple annual-total
metric, the canal's direct physical path (Panna -> Chhatarpur -> Tikamgarh -> Lalitpur) is
**not** passing through areas that read as rainfall-deficient today — it tracks almost identically
to the off-canal Phase-II districts, including Vidisha/Raisen.

**The 1981-1990 baseline tells a different, more useful story.** Baseline-era means show real
differentiation that recent-decade totals wash out:
- Wetter historically: Vidisha/Raisen (~1009mm), Sagar (~976mm), Damoh (~939mm)
- Driest historically, closer to genuinely semi-arid: **Shivpuri (~659mm), Jhansi (~725mm),
  Datia (~724mm)** — all off-canal, Phase-II/wider-beneficiary districts, not on the direct
  canal path.
- On-canal points (Panna through Lalitpur) sat in an intermediate 825-990mm band at baseline —
  never as dry as Shivpuri/Jhansi/Datia, never as wet as Vidisha/Raisen.

So even in the historically drier baseline period, the direct canal route was not the driest
part of the beneficiary map — Shivpuri, Jhansi, and Datia (all off-canal / Phase-II) were drier
than anywhere the canal itself physically passes through.

## What this means for the "en-route benefit" question

Combined with the NWDA's own water-accounting split (1010.51 MCM en-route vs 50.93 MCM actually
reaching Betwa river at Lalitpur, from the parent conversation): the canal's own physical route
sits in a rainfall band that was never the most water-stressed part of the region, even at 1980s
baseline, and by the current decade the entire route reads as rainfall-adequate on this metric.
The genuinely driest points in the whole beneficiary picture (Shivpuri, Jhansi, Datia) are
**off the direct canal path** — their claimed benefit depends on separate Phase-II infrastructure,
not the Ken-Betwa canal itself. This is consistent with, not a refutation of, the earlier finding
that "en-route" water is being used in areas that are not the most water-stressed ones on the map.

## Caveats (read before citing any of this)

- **Straight-line route approximation**: the real canal follows engineered contours; actual
  alignment may pass through different micro-terrain than these 10 points suggest. Treat this as
  directional, not a survey-grade route profile.
- **Point samples, not watershed-averaged**: same limitation as the basin-level analysis in
  `results.md`.
- **Rainfall totals ≠ water availability**: annual total rainfall doesn't capture intra-year
  distribution, evapotranspiration, soil retention, or groundwater — a district can have "enough"
  annual rainfall and still be agriculturally water-stressed if it falls in a short intense burst
  with poor retention (a known Bundelkhand hydrogeology issue: hard-rock terrain, low natural
  storage). This analysis cannot distinguish that from genuine surplus.
- **ERA5/Open-Meteo bias**: known accuracy limits vs ground stations in India, worse pre-2000 —
  treat baseline-era (1981-90) numbers as more uncertain than recent-decade numbers.
- **Phase-II district bundling is contested, not confirmed**: this analysis assumes Vidisha,
  Raisen, Sagar, Damoh, Datia, Shivpuri, Banda, Mahoba, Jhansi are off the direct canal path based
  on secondary sources (IndiaSpend/SANDRP framing) — this has not been verified against an actual
  engineering DPR map. If any of these districts are in fact served by direct canal offtakes
  rather than separate Phase-II works, the on-canal/off-canal split here would need correction.
