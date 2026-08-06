# Ken-Betwa Link Project (KBLP): Consolidated Analysis

Investigation into India's National River Linking Project (NRLP) and its pilot,
the Ken-Betwa Link Project — costs, claimed benefits, who actually benefits, and
an independent public-data check on the core hydrological assumptions.

Every quantitative claim below was re-verified against original sources during
this pass, not just re-stated from earlier conversation. See Section 10 for a
per-claim confidence rating. Where sources conflicted, both are shown — no
number was silently picked for convenience.

**Update (this revision): three official NWDA primary-source PDFs were obtained
directly** — `kblp_about_Index_Map.pdf`, `Salient Features of KBLP.pdf`, and
`kblp_Project_at_Glance.pdf` (all saved in `source-pdfs/` alongside this
document; NWDA's live site returns a TLS certificate error on normal fetch, so
these were retrieved via direct download bypassing certificate verification).
These are now the **primary spine** for Sections 4 and 7 — several things
previously marked single-source or unresolved are now Verified, and one earlier
finding in this conversation (a "~62% of the headline is unaccounted for" claim)
is **corrected down to ~14.5%** now that the full official command-area table is
available. This is flagged prominently, not buried, because it was stated
confidently to the user before this data existed.

---

## 1. Executive Summary

- KBLP (₹44,605 crore, Cabinet-approved Dec 2021, foundation stone Dec 2024,
  targeted completion 2030) is the pilot for India's ₹5+ lakh crore, 30-link
  National River Linking Project — the only link to reach implementation in 45 years.
- Its founding premise — Ken is a "surplus" basin, Betwa a "deficit" basin — comes
  from 1980s-era hydrological classification. Our own rainfall re-check (public
  data, 1981-2025) shows both basins have gotten wetter, but **Betwa's rainfall has
  risen faster than Ken's**, narrowing (not confirming) the basin's claimed water gap.
- **The single biggest finding, now confirmed straight from NWDA's own text:
  most of this project's water never leaves the Ken basin.** Ken's own basin
  utilization (MP + UP combined) is **4,050 MCM/year**, against just **1,377 MCM**
  actually diverted through the link canal to Betwa — and of that 1,377 MCM,
  only **50.93 MCM** (≈4%) ever crosses into the Betwa river itself. Ken's own
  basin gets roughly **3x more water** than the entire interbasin transfer
  (Section 4a).
- NWDA's own water accounting for the transfer itself shows a ~20:1 en-route
  skew — ~1,010 MCM consumed en-route (Chhatarpur/Tikamgarh) vs. only ~51 MCM
  actually reaching the Betwa river at Lalitpur.
- The driest districts in the whole beneficiary list historically (Shivpuri, Jhansi,
  Datia, 1981-90 baseline) are **not on the canal's physical path** — their claimed
  benefit comes from separate Phase-II dams on Betwa's own tributaries (Orr, Keotan),
  independent of any transferred Ken water (Section 7).
- **Two districts we'd flagged as "no verified mechanism" (Damoh, Banda) are now
  confirmed via NWDA's own documents** — both get water from Ken's own
  infrastructure (Saleha Lift Irrigation Scheme, Bariarpur pick-up weir), not
  the Betwa transfer. A third (Mahoba) has a real, if partial, en-route
  mechanism we'd previously and wrongly said didn't exist (Section 7a).
- The official, current, most-authoritative total command area (NWDA's own
  "Comprehensive Project Report" figure) is **9,08,428 ha** — not the 10.62 lakh
  ha (10,62,000 ha) figure repeated in every press release. That's a real but
  modest ~14.5% gap, not the ~62% gap this document previously (and wrongly)
  stated based on incomplete component data (Section 4b).
- SANDRP's 2017 figure (6,35,661 ha) is confirmed as an **authentic original DPR
  number**, not a misattribution — but it was already ~23% ahead of that DPR's
  own technical command-area estimate (515,210 ha) at the time. Their core
  objection holds up well against the government's own numbers (Section 4c).
- Cost-comparison claims to local watershed alternatives are directionally real but
  commonly overstated: normalizing by hectare rather than total cost, local watershed
  works look ~2x cheaper per hectare, not 50x — the "95-98% cheaper" headline
  compares totals at very different scales (Section 8).
- Displacement and forest-loss figures vary substantially by source and year; we
  present ranges rather than pick one number (Section 5).

---

## 2. National River Linking Project (NRLP) — Background

- Origin: National Perspective Plan (NPP), August 1980. NWDA identified 30 links —
  16 Peninsular, 14 Himalayan — for feasibility studies.
- Whole-programme cost estimate: over ₹5 lakh crore (~US$168 billion) — an
  aggregate estimate across all 30 links, not a sanctioned single budget.
- KBLP is the only link that has reached implementation as of 2026; all others
  remain at feasibility/DPR/consensus stage, gated on inter-state agreement since
  water is a state subject under India's constitution.

**Confidence: Verified** — multiple independent government and press sources agree.

---

## 3. KBLP Overview: Timeline, Cost, Physical Scope

### Timeline (cross-checked, consistent across sources)

| Year | Event |
|---|---|
| Aug 1980 | National Perspective Plan formulated |
| Aug 2005 | MP + UP + Centre sign MoU to prepare DPR |
| Apr 2010 | NWDA completes DPR Phase-I |
| Jan 2014 | NWDA completes DPR Phase-II |
| Sep 2014 | Special Committee on Interlinking of Rivers constituted |
| Mar 2021 | MP + UP sign implementation MoU with Jal Shakti Ministry |
| Dec 2021 | Union Cabinet approves project, ~₹44,000 cr |
| Dec 25, 2024 | PM lays foundation stone |
| Target: Mar 2030 | Completion |

**Confidence: Verified** (consistent across govt and independent sources).

### Cost

- Total cost: **₹44,605 crore at 2020-21 price levels** (Cabinet-approved figure).
- Central support: **₹39,317 crore** (₹36,290 cr grant + ₹3,027 cr loan).
- **Confidence: Verified** — consistent across PIB, PMO, and press coverage.

### Budget vs. actual expenditure — UNRESOLVED DISCREPANCY

Two different expenditure figures exist in public reporting, and we could not
reconcile them within this pass:

- One figure (previously reported in this conversation): ₹4,469.41 crore budgeted,
  ₹3,969.79 crore spent "over the last three financial years." We could not
  re-locate the original PIB/Parliament answer carrying this exact figure in this
  pass — treat as **single-source, unverified** until the original Lok Sabha
  reply is found.
- A separate, larger figure: as of **December 31, 2022**, total expenditure was
  reported at **₹7,665 crore** (₹5,038.28 cr central grant + ₹2,626.70 cr state
  budget) — this is a Lok Sabha-sourced figure per press reporting.
- A Swarajya news-brief headline separately cites "₹3,969 crore spent on Ken-Betwa
  so far" (undated in the snippet retrieved), which is suspiciously close to the
  "3,969.79" figure above but doesn't obviously reconcile with the ₹7,665 crore
  Dec-2022 figure — these may cover different time windows, different central-only
  vs. total (central+state) accounting, or different report dates.

**Confidence: Unresolved discrepancy.** Do not cite a single expenditure figure
from this document without first checking the original PIB/Parliament source and
its as-of date. The gap between ₹3,969 cr and ₹7,665 cr is too large to be rounding.

### Physical scope

- Daudhan Dam (Ken river, Panna district) + 221 km canal (incl. ~2 km tunnel
  section — some sources describe two tunnels, 1.9 km and 1.1 km) to Betwa river.
- Phase-II: Lower Orr Dam + four barrages (Neemkheda, Barari, Kotha, Kesari) —
  see Section 7 for verified locations.
- 103 MW hydropower + 27 MW solar power.

**Confidence: Verified** for dam/canal/power figures (consistent across sources);
**single-source** for the exact tunnel count/length breakdown (sources disagree
on one vs. two tunnels).

---

## 4. Who Benefits: Irrigation, Drinking Water, and Where the Water Actually Goes

### Headline figures (verified, consistent across PIB/NWDA/press)

- Total irrigation: **10.62 lakh ha/year** — 8.11 lakh ha in MP, 2.5-2.51 lakh ha
  in UP (~76% MP / ~24% UP split).
- Drinking water: **~62 lakh people** — 41 lakh MP, 21 lakh UP.
- Official beneficiary districts, per NWDA's own "About" page — MP: Chhatarpur,
  Tikamgarh, Panna, Damoh, Vidisha, Sagar, Shivpuri, Datia, Raisen. UP: Mahoba,
  Banda, Jhansi, Lalitpur.
- 103 MW hydropower + 27 MW solar.

**Confidence: Verified** — now directly from NWDA's own "About" and
"Project at a Glance" PDFs (`source-pdfs/kblp_Project_at_Glance.pdf`), not
search-engine summaries.

### 4a. The core finding: most of the project's water never leaves the Ken basin

NWDA's own "About – Ken Betwa Link Project" text (`source-pdfs/kblp_Project_at_Glance.pdf`,
page 1) gives the full water-balance accounting:

- **Ken basin's annual gross yield up to Daudhan Dam: 6,590 MCM** (at 75%
  dependability).
- **MP utilizes 2,350 MCM + UP utilizes 1,700 MCM = 4,050 MCM directly from the
  Ken system** — feeding Ken's own left-bank canal, the Bariarpur pick-up weir
  system, and lift-irrigation schemes (Section 7a). This water **never crosses
  into the Betwa basin.**
- **Total use of water from Daudhan reservoir: 4,543.52 MCM** (includes the
  4,050 MCM above plus environmental releases) — cross-checked and confirmed
  exactly against the master reconciliation table in
  `source-pdfs/Salient Features of KBLP.pdf` (§2.3.4, "Total under Daudhan dam"
  row: 4,049.92 MCM utilization + 493.6 MCM environmental flow = 4,543.52 MCM).
- **The surplus actually diverted through the link canal to Betwa: 1,377 MCM/year.**
  Of this: 220.77 MCM used at a pumping station at RD 18km, 1,010.51 MCM
  irrigates the en-route command area, 94.79 MCM for en-route drinking water,
  and **50.93 MCM** is released into the Betwa river itself (upstream of
  Parichha Weir, for use in Lalitpur). These four figures sum exactly to 1,377 MCM.
  A further 222 MCM in extreme monsoon years is unutilized spill, staying in
  the river.

**So: Ken's own basin gets ~4,050 MCM/year, roughly 3x the entire 1,377 MCM
diverted to Betwa — and of that 1,377 MCM, only ~4% (50.93 MCM) actually reaches
the Betwa river.** The project's own name overstates how much of its water is
genuinely interbasin. This is the sharpest, best-sourced finding in this
document — confirmed by NWDA's own published text, not inferred.

**Confidence: Verified** — cross-checked and internally consistent across two
independent official documents (About page + master table), arithmetic checks
out exactly (4,049.92 + 493.6 = 4,543.52; 220.77 + 1,010.51 + 94.79 + 50.93 =
1,377.0).

### 4b. Does the 10.62 lakh ha headline add up? — corrected

An earlier pass through this analysis found only ~4.05 lakh ha traceable to
named structures out of the 10.62 lakh ha headline (a ~62% gap) and stated this
prominently to the user. **That was based on incomplete component data and is
now corrected**, having obtained NWDA's full official command-area table
(`Salient Features of KBLP.pdf`, §2.3.4):

| Level | CCA (ha) | Source |
|---|---|---|
| CCA as per original DPR | 5,15,210 | §2.3.4 table, "Total under Daudhan dam" + Bina/Kotha/Lower Orr rows |
| Annual irrigation as per original DPR | 6,35,661 | Same table — **this is the exact figure SANDRP cited in 2017** (see 4c) |
| **CCA as per Comprehensive Project Report (current, most authoritative)** | **9,08,428** | Same table, grand total row |
| Headline figure used in all press/PIB materials | 10,62,000 | PIB/PMO/press, consistent |

**Gap between the current official technical total (9,08,428 ha) and the
press headline (10,62,000 ha): ~1,53,600 ha, ~14.5%** — real, but a fraction of
the ~62% previously claimed. The remaining gap is unexplained in the documents
obtained so far (possibly rounding, a later revision, or additional
micro-irrigation/drinking-water-linked area not captured in this CCA table) —
flagged as a smaller, genuine open question rather than a large unverified claim.

**Confidence: Verified** (from NWDA's own master table) for the 9,08,428 ha
figure and the ~14.5% gap; the **cause** of the remaining gap is unresolved.

### 4c. SANDRP's critique — now confirmed as an authentic official figure

The original 2017 SANDRP post states:

> DPR: "a third of the surplus water will be utilized for enroute irrigation of
> 0.60 lakh ha" (i.e., 60,000 ha)
>
> EAC (Expert Appraisal Committee): "It is proposed to provide irrigation
> facility in 6,35,661 ha of area in Panna, Chhatarpur, Tikamgarh Districts of
> Madhya Pradesh and Banda, Mahoba and Jhansi Districts in Uttar Pradesh"

NWDA's own master table (§2.3.4) confirms **6,35,661 ha is a real number** — it
is exactly the "Annual irrigation as per DPR (Original)" total (MP 3,69,881 +
UP 2,65,780 = 6,35,661). This was not a misattribution or SANDRP error. But
that same original DPR's own **command area (CCA)** — a technically distinct,
narrower measure than "annual irrigation" — was only **5,15,210 ha** at the
time. So even by the project's own original technical documents, the widely
publicized irrigation figure (6,35,661 ha) already ran **~23% ahead of** the
DPR's own command-area estimate. SANDRP's 2017 objection — that the publicized
irrigation claim looked inconsistent with the technical basis — holds up well
against the government's own numbers, though the project's technical estimate
has since been revised upward (to 9,08,428 ha under the "Comprehensive Project
Report"), narrowing but not eliminating that original gap.

**Confidence: Verified** — both the 6,35,661 ha and 5,15,210 ha figures are now
confirmed directly from NWDA's own table, resolving what was previously an
"inferential leap, not proven" rating.

---

## 5. Environmental and Social Costs — Reconciled Estimates

### Forest/tree loss — estimates vary substantially by source and date; no single number is authoritative

| Estimate | Source/date (as found) | Context |
|---|---|---|
| ~10,500 ha habitat, "46 lakh trees" | 2017 Forest Advisory Committee (FAC) estimate | Cited as the official-process estimate at clearance stage |
| "18 lakh trees" | Hindustan Times, May 2017 | Contemporary press coverage of the FAC-era clearance process |
| "7 lakh trees over 90 sq km" | Deccan Herald (undated in source retrieved) | Different area/tree-count pairing than the above two |
| "3 to 4 million trees" (30-40 lakh) | More recent (2023-24 era) critical commentary | Closer to, but still not matching, the 2017 FAC figure |

These four figures span roughly a 6x range (7 lakh to 46 lakh trees) and do not
cleanly reconcile — they may reflect different project phases (Phase I only vs.
full project), different area definitions, or simply inconsistent secondary
reporting of an original FAC number we did not independently locate in this pass.
**Treat "several tens of lakh trees, order of magnitude, exact figure contested"
as the honest summary — do not cite a single tree count as authoritative.**

**Confidence: Unresolved discrepancy.**

### Displacement — similarly inconsistent

- One framing: 6,600+ Gond/Kol Adivasi households; 10 villages fully submerged;
  24 villages affected in total.
- Another framing: "21 villages" displaced by dams and canal, without the
  submerged/affected split.

These may both be roughly correct under different counting conventions (e.g.,
"fully submerged" vs. "land acquired from" vs. "any project impact"), but we
could not confirm which framing is more current/authoritative in this pass.

**Confidence: Unresolved discrepancy** — present as a range (~21-24 villages,
6,600+ households), not a single figure.

### Wildlife/ecological impact

- ~70% of Panna Tiger Reserve's core area affected (submergence), including tiger
  breeding zones and nesting sites for critically endangered white-rumped and
  long-billed vultures.
- Ken Gharial Sanctuary and golden mahseer populations flagged as threatened.
- Central Empowered Committee (Supreme Court body) has itself noted forest/wildlife
  clearance was treated as a procedural formality.

**Confidence: Verified** (consistent across multiple independent environmental
reporting sources) for the qualitative claims; the specific "70%" figure is
**single-source** and should be treated as an estimate, not an exact measurement.

---

## 6. Our Independent Rainfall Analysis

Full methodology, caveats, and raw data: `results.md`, `route_analysis.md`,
`fetch_rainfall.py`, `fetch_route_rainfall.py`, `analyze_trends.py`,
`ken_basin_rainfall.csv`, `betwa_basin_rainfall.csv`, `canal_route_rainfall.csv`,
`wider_district_rainfall.csv`.

**We independently recomputed every headline number in this section directly
from the raw CSVs during this verification pass** (not just re-read the prior
summary) — all figures below match what was previously reported:

- Ken annual rainfall: 940mm (1981-90 mean) → 1,213mm (2016-25 mean), **+29.0%**.
- Betwa annual rainfall: 931mm → 1,277mm, **+37.2%**.
- Ken/Betwa ratio: 1.010 (1981-90, near parity) → 0.950 (2016-25) — Betwa now
  wetter than Ken, a reversal from parity.
- Trend significance: both increasing, Kendall's tau p<0.01 for both basins
  (Ken p=0.0026, Betwa p=0.0008 by direct recomputation).
- Route/wider-district baseline (1981-90): driest points were Shivpuri (~659mm),
  Jhansi (~725mm), Datia (~724mm) — all off the direct canal path. On-canal
  points (Panna→Chhatarpur→Tikamgarh→Lalitpur) sat in an intermediate 825-990mm
  band, never the driest part of the map even historically.
- By 2016-25, every sampled point (canal-route and wider-district) reads above
  900mm — the differentiation is a historical-baseline signal, washed out in
  recent data.

**Confidence: Our-own-analysis.** Methodologically sound for what it is (a cheap
directional proxy), but explicitly **not** a substitute for actual streamflow
data — see caveats in `results.md` and `route_analysis.md` (rainfall ≠ runoff;
ERA5/Open-Meteo reanalysis has known India-specific biases, especially pre-2000;
point sampling, not true watershed-area-weighted averaging; straight-line canal
route is a coarse approximation of the true engineered alignment).

---

## 7. Phase-II Geography — Verification of the Upstream/Downstream Claim

**This section corrects and confirms a claim already given to the user in this
conversation — it was checked against real geographic sources, not assumed.**

### Betwa's actual course (verified via Wikipedia's Betwa River article)

Betwa rises in the Vindhya Range near Raisen (just north of Hoshangabad, MP),
flows **northeast** through Madhya Pradesh — passing Vidisha, Sanchi, Ganj Basoda,
Kurwai, Orchha — then into Uttar Pradesh, joining the **Yamuna at Hamirpur**.
Total length 590 km (232 km in MP, 358 km in UP).

**This confirms the claim already given to the user: Raisen and Vidisha sit near
the river's source — genuinely upstream — while Jhansi and Lalitpur (and the
canal's terminus near Lalitpur) sit much further downstream, closer to the
Hamirpur/Yamuna confluence.** Transferred Ken water released into the Betwa near
Lalitpur physically cannot flow upstream to reach Neemkheda (Raisen), Barari, or
Kotha (Vidisha) barrages. This part of the prior conclusion **holds** — it was a
correct inference, now confirmed against a primary geographic source rather than
just district-name association.

### Phase-II structures — re-verified against independent source (PMFIAS)

| Structure | River | District |
|---|---|---|
| Lower Orr Dam | Orr (Betwa tributary) | Ashoknagar / Shivpuri |
| Neemkheda barrage | Betwa (mainstem) | Raisen |
| Barari barrage | Betwa (mainstem) | Vidisha |
| Kotha barrage | Betwa (mainstem) | Vidisha |
| Kesari barrage | Keotan (Betwa tributary) | Vidisha |

All five structures capture Betwa-basin water (mainstem or tributary) that
existed independent of any Ken transfer — confirmed by the upstream geography
above. **Confidence: Verified** (two independent sources agree on structure
locations; geography independently confirmed via Wikipedia).

### Datia — settled with real district-boundary data, after two wrong turns

This claim went through two incorrect states in this analysis before being
settled properly, worth showing rather than hiding:

1. First pass: treated Datia's inclusion as an unconfirmed secondary-source
   claim ("weakest single fact in this document").
2. Second pass: over-corrected after re-reading the index map's text/OCR
   extraction, concluding the "Enroute Command of Lower Orr Dam" (90,000 ha)
   polygon must be drawn spanning both Shivpuri and Datia — an inference from
   the district list, not a verified spatial fact.
3. **Settled here, using real geography**: fetched actual district boundary
   polygons for Shivpuri and Datia from OpenStreetMap (via Nominatim; see
   `ken_betwa_flow_map.html`'s `districtBoundaries` data and
   `index_map_documentation.md`). Measured straight-line distance from Lower
   Orr Dam (24.90°N, 77.85°E) to each district's nearest boundary point:
   **6.2 km to Shivpuri, 92.8 km to Datia.** A 90,000 ha (~900 km², roughly
   30 km across) command area cannot physically span a 93 km gap. The dam's
   command area almost certainly sits entirely within Shivpuri/Ashoknagar.

**Conclusion: Datia is officially listed as a KBLP beneficiary district, but
the specific mechanism most often cited (Lower Orr Dam's command area) is
geographically implausible, confirmed by real district-boundary measurement,
not inference from a jumbled PDF text extraction.** If Datia genuinely
benefits, it must be through some other, unnamed mechanism — this analysis
found none. Datia's own primary drainage (Sindh/Pahuj river system, per CGWB)
remains structurally separate from the Betwa/Orr system Lower Orr Dam sits on.

**Confidence: Verified** (real boundary distance, directly measured) that the
Lower-Orr-Dam-to-Datia mechanism is implausible; **Unresolved** whether any
other mechanism explains Datia's official beneficiary status.

### 7a. Phase I's own 7 official beneficiary districts — mechanism confirmed for each

Phase I's specifically-named beneficiary list (`Salient Features of KBLP.pdf`,
Daudhan Dam § "Benefited Districts") is narrower than the whole-project
13-district list: **MP: Chhatarpur, Tikamgarh, Panna. UP: Jhansi, Mahoba, Banda,
Lalitpur** — 7 districts total. **Damoh is not on this specific list**, despite
drawing Daudhan-associated water via the Saleha LIS (§2.3.4 groups it under
"Total under Daudhan dam") — a small internal inconsistency in NWDA's own
documents (one table's scope doesn't match another's), not something we're
introducing. We include Damoh below anyway since its water-source mechanism is
directly relevant and confirms the same "Ken-basin, not transfer" pattern.
NWDA's master command-area table (§2.3.4) and index map together let us trace
an actual mechanism for each — several corrections to earlier findings in this
conversation follow:

| District | Mechanism | Water source | Status |
|---|---|---|---|
| Panna | Dam site; "Lift from Daudhan Dam – Panna district" (Saleha LIS, part 1) | Ken (Daudhan reservoir) | Verified |
| Chhatarpur | En-route K-B Link Main Canal command | **Transfer** (en-route) | Verified |
| Tikamgarh | En-route K-B Link Main Canal command | **Transfer** (en-route) | Verified |
| Lalitpur | Canal terminus, 50.93 MCM released to Betwa | **Transfer** (final release) | Verified |
| **Damoh** | "Lift from Daudhan Dam – Damoh district" (Saleha LIS, part 2) — 20,101 ha / 104.653 MCM | **Ken** (Daudhan reservoir), *not* the transfer | **Corrected**: previously "no Betwa-side mechanism found, likely Ken-basin" — now confirmed exactly. 104.653 + Panna's 331.634 = 436.29 MCM, matching the "436 MCM ... Saleha Lift Irrigation Scheme ... Panna and Damoh" line in the About page almost exactly. |
| **Banda** | "Bariarpur PUW [pick-up weir] through Dam", fed from Daudhan Dam releases; carries a large environmental-flow allocation (493.6 MCM) | **Ken** (via Bariarpur), *not* the transfer | **Corrected/confirmed**: previously inferred from Ken/Yamuna confluence geography alone (Chilla village); now named and quantified in NWDA's own table. |
| **Mahoba** | "Enroute Command (Jhansi & Mahoba)": 17,488 ha, plus a separately labeled "additional command proposed by UP in Mahoba": 37,564 ha | Partly genuine en-route **transfer** water (shared with Jhansi), plus a separate UP-proposed addition | **Corrected**: this conversation previously stated "no mechanism found anywhere" for Mahoba — that was wrong. A real, officially documented mechanism exists, though the split between the genuinely canal-fed portion and the separately-proposed addition isn't further broken down in the documents obtained. |

**Only 4 of Phase I's own 7 districts (Panna, Chhatarpur, Tikamgarh, Lalitpur)
receive genuinely transferred Ken-to-Betwa water. Damoh and Banda receive Ken's
own water via separate Ken-basin infrastructure (Saleha LIS, Bariarpur PUW) —
real, documented, but not the interbasin transfer. Mahoba's mechanism is
partially transfer-connected (shared en-route command with Jhansi) plus a
separate additional claim.** This is the same "administrative bundling" pattern
found at the whole-project level (Section 4a) recurring inside Phase I's own
narrower district list.

**Confidence: Verified** for all mechanisms above — sourced directly from
NWDA's own index map and master command-area table, not inference.

### 7b. Bina Complex hectare figure — resolved

A secondary source (encountered earlier in this investigation) claimed the Bina
Complex covers "8 lakh ha across 10 MP districts," sharply contradicting the
96,000 ha figure used throughout this document. **NWDA's own index map and
master table both confirm 96,000 ha** (CWC's project annexure independently
corroborates this too, with tehsil-level detail: Madia + Dehra dams on the Bina
river, arrested by Chakarpur Dam, serving Khurai/Malthone/Bina tehsils, Sagar
district). **The 8 lakh ha figure has no supporting primary source and should
be treated as an error in that one secondary source.**

**Confidence: Verified** — three independent sources (NWDA index map, NWDA
master table, CWC annexure) agree on 96,000 ha.

---

## 8. Cost Comparison to Local Alternatives

### Original claims (Brij Gopal analysis, via IndiaSpend/isignal.in)

- Local water management: ~44,000 ha irrigated for **₹880 crore**.
- Compared against a **₹18,000 crore** Ken-Betwa cost estimate (an earlier,
  smaller project-cost figure than the current ₹44,605 crore Cabinet-approved
  figure — likely a pre-2018 or Phase-I-only estimate; exact date/scope of the
  ₹18,000 cr figure not confirmed in this pass).
- Headline claim: ~95% cost saving.

### Recomputed against the current ₹44,605 crore figure

If we naively substitute the current total project cost:
₹880 cr / ₹44,605 cr ≈ 2%, i.e., a **~98% "saving"** — an even larger headline
number than the original claim.

**But this recomputation is itself misleading**, and we flag it as such rather
than present it uncritically: the ₹880 cr local-alternative figure covers **44,000
ha**, while ₹44,605 cr covers a claimed **10.62 lakh ha** — a ~24x difference in
scope. Comparing *total costs* across two wildly different scales is not a valid
comparison. The economically meaningful comparison is **cost per hectare**:

- Local alternative: ₹880 cr ÷ 44,000 ha ≈ **₹2.0 lakh/ha**
- KBLP: ₹44,605 cr ÷ 10,62,000 ha ≈ **₹4.2 lakh/ha**

**Normalized per hectare, KBLP is roughly 2x more expensive than the local
alternative — not 50x, and not a 95-98% saving.** The large headline percentages
in both the original claim and our naive recomputation are artifacts of comparing
totals at different scales, not a real per-unit cost difference. The ~2x per-hectare
gap is still a meaningful finding in favor of local alternatives (before even
counting KBLP's displacement, forest-loss, and ecological costs, which have no
equivalent in the local-alternative case) — but it is a much more modest, more
defensible number than the "95% cheaper" framing suggests.

**Confidence: Our-own-analysis (recomputation from single-source input figures)** —
the ₹880 cr and 44,000 ha inputs themselves are single-source (Brij Gopal via
IndiaSpend) and not independently re-verified in this pass.

### Supporting case-study evidence (not independently re-verified in this pass)

- Parasai-Sindh watershed (Jhansi district): traditional Haveli earthen-bunding
  raised groundwater by 2-5 meters, enabling double-cropping.
- Kol tribe farm ponds/check dams (2009-2011): wheat yield rose from 19,910 kg to
  190,920 kg (~9.6x) after building 61 structures.
- IWMI: repairing 146 tanks in Tikamgarh could irrigate 29,000 ha, vs. KBLP's
  planned 47,000 ha across four districts (no cost figure given for this
  comparison in the source).

**Confidence: Single-source** for all three — each traces to one secondary
source (IndiaSpend/isignal.in piece), not independently cross-checked against a
primary study in this pass. Directionally plausible (consistent with a broad,
well-documented literature on Indian watershed-management success stories) but
the specific numbers should be treated as illustrative, not load-bearing.

---

## 9. Full Source List

- PIB: [River Interlinking Projects](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2149302), [National River Linking Project](https://www.pib.gov.in/Pressreleaseshare.aspx?PRID=1777259), [Cabinet approves Ken-Betwa](https://www.pib.gov.in/PressReleasePage.aspx?PRID=1779306)
- PMO: [Cabinet approves Ken-Betwa Interlinking of Rivers Project](https://www.pmindia.gov.in/en/news_updates/cabinet-approves-ken-betwa-interlinking-of-rivers-project/)
- NWDA official PDFs (primary source, this revision) — live nwda.gov.in pages return a TLS
  certificate error on standard fetch; these were retrieved by direct download bypassing
  certificate verification, and are saved in `source-pdfs/` alongside this document:
  - [KBLP Index Map](https://nwda.gov.in/upload/uploadfiles/files/kblp_about_Index_Map.pdf) — `source-pdfs/kblp_index_map.pdf`
  - [Salient Features of KBLP](https://nwda.gov.in/upload/uploadfiles/files/Salient%20Features%20of%20KBLP.pdf) — `source-pdfs/kblp_salient_features.pdf` (26pp; §2.3.4 command-area/water-utilization master table is the primary spine for Sections 4 and 7a)
  - [KBLP Project at a Glance](https://nwda.gov.in/upload/uploadfiles/files/kblp_Project_at_Glance.pdf) — `source-pdfs/kblp_project_at_glance.pdf`
- SANDRP: [Unjustified Ken-Betwa Link Costs (2017)](https://sandrp.in/2017/01/24/drp-news-bulletin-23-jan-2017-unjustified-ken-betwa-link-costs-bundelkhand-to-gain-nothing-panna-to-lose-its-tigers/) — original quotes re-verified in this pass
- Hakai Magazine: [The Audacious Scheme to Reroute India's Water](https://hakaimagazine.com/news/the-audacious-scheme-to-reroute-indias-water/)
- Mongabay: [river interlinking could worsen drought](https://india.mongabay.com/2023/10/as-ken-betwa-project-barrels-ahead-new-research-finds-river-interlinking-could-worsen-drought/)
- Dialogue Earth: [new doubts about India's river linking plans](https://dialogue.earth/en/water/new-research-raises-fresh-doubts-about-indias-river-linking-plans/), [will not save Bundelkhand](https://dialogue.earth/en/water/linking-rivers-will-not-save-bundelkhand/)
- Geographical: [river-linking project could affect monsoon](https://geographical.co.uk/science-environment/indias-controversial-river-linking-project)
- National Herald: [the irreversible course of damage](https://www.nationalheraldindia.com/environment/ken-betwa-river-linking-project-panna-tiger-reserve-the-irreversible-course-of-damage)
- Countercurrents: [NACEJ condemns violations (Jul 2026)](https://countercurrents.org/2026/07/nacej-condemns-the-violation-of-constitutional-and-human-rights-of-the-ken-betwa-link-project-affected-communities/), [non-viability (Sep 2023)](https://countercurrents.org/2023/09/ken-betwa-river-link-project-should-be-reconsidered-due-to-non-viability-and-disruptive-impacts-on-bundelkhand-region/), [will not solve water problems (Dec 2024)](https://countercurrents.org/2024/12/ken-betwa-river-link-project-will-not-solve-the-water-problems-of-bundelkhand/)
- Counterview: [climate justice alliance backs Bundelkhand villagers](https://www.counterview.net/2026/07/climate-justice-alliance-backs.html)
- IndiaSpend (mirrored at isignal.in): [Pipe Dreams: Why Interlinking Ken-Betwa Will Not Solve Bundelkhand's Water Crisis](https://www.isignal.in/pipe-dreams-why-interlinking-ken-betwa-will-not-solve-bundelkhands-water-crisis)
- Down To Earth: [at what cost?](https://www.downtoearth.org.in/water/ken-betwa-linking-project-seeks-to-end-bundelkhands-water-woes-but-at-what-cost)
- EPW (paywalled): Sudeshna Ghosh, Feb 2026, [Ken-Betwa River Linking Project](https://www.epw.in/journal/2026/2/commentary/ken-betwa-river-linking-project.html)
- Bundelkhand Research Portal: [Agriculture in Bundelkhand](https://bundelkhand.in/info/agriculture-in-bundelkhand)
- The Print: [critics' questions and fears](https://theprint.in/environment/in-deadly-dry-bundelkhand-ken-betwa-link-finally-seems-real-but-critics-have-questions-fears/888236/)
- theanalysis.org.in: [KBLP Resources — Reports & Documents](https://theanalysis.org.in/ken-betwa-link-project-resources-reports-documents/) (primary EIA/Feasibility/R&R documents hosted here, not yet individually reviewed in full)
- Rau's IAS, PMFIAS, NextIAS, Sanskriti IAS, Testbook, Lukmaan IAS, Vajiram & Ravi, Model Diplomat, Legacy IAS, Qukut, ForumIAS, Swarajya — exam-prep/aggregator sources, used for cross-checking factual details (dates, MW figures, district lists) where primary sources were unavailable; **treated as lower-tier corroboration, not primary evidence**, per this document's confidence ratings
- Wikipedia: [Betwa River](https://en.wikipedia.org/wiki/Betwa_River) — used for geographic verification in Section 7
- CGWB: [Datia District Profile](https://cgwb.gov.in/old_website/District_Profile/MP/Datia.pdf) — used for the Datia basin-membership check in Section 7
- Our own analysis: `results.md`, `route_analysis.md`, `fetch_rainfall.py`, `fetch_route_rainfall.py`, `analyze_trends.py`, and associated CSVs, this repo

---

## 10. Confidence and Limitations Summary

| Claim | Rating |
|---|---|
| NRLP background (1980 origin, 30 links, ₹5 lakh cr aggregate) | Verified |
| KBLP timeline (1980-2030) | Verified |
| KBLP total cost ₹44,605 cr / central support ₹39,317 cr | Verified |
| KBLP budget vs. actual expenditure (any single figure) | **Unresolved discrepancy** — ₹3,969 cr vs ₹7,665 cr vs ₹4,469 cr budgeted figures do not reconcile |
| Irrigation 10.62 lakh ha (8.11 MP / 2.51 UP), drinking water 62 lakh people | Verified — direct from NWDA PDFs |
| Ken basin's own utilization (4,050 MCM) vs. actual interbasin transfer (1,377 MCM, of which 50.93 MCM reaches Betwa) | **Verified** — NWDA's own text, arithmetic cross-checked exactly across two documents |
| NWDA en-route water accounting (1010.51 / 94.79 / 50.93 MCM) | **Verified** — confirmed directly from NWDA's "About" page and master table (upgraded from single-source) |
| Official CCA 9,08,428 ha vs. 10.62 lakh ha headline (~14.5% gap) | **Verified** figure; **corrects this document's own earlier claim of a ~62% gap**, which was based on incomplete component data |
| SANDRP's DPR-vs-EAC irrigation figures (60,000 ha vs 6,35,661 ha) | **Verified** — 6,35,661 ha and the original DPR's 5,15,210 ha CCA both confirmed directly from NWDA's master table (upgraded from "inference, not proven") |
| Damoh's mechanism (Saleha LIS from Daudhan reservoir, Ken water) | **Verified** — corrects this document's earlier "no Betwa-side mechanism found" to a confirmed Ken-basin mechanism |
| Banda's mechanism (Bariarpur PUW from Daudhan Dam, Ken water) | **Verified** — corrects/confirms earlier geography-only inference with an official named structure |
| Mahoba's mechanism (en-route Jhansi&Mahoba 17,488 ha + separate 37,564 ha UP proposal) | **Verified** — corrects this document's earlier "no mechanism found anywhere," which was wrong |
| Bina Complex CCA (96,000 ha vs. a conflicting "8 lakh ha" secondary claim) | **Verified at 96,000 ha** — three independent sources agree; the 8 lakh ha figure is unsupported |
| Forest/tree-loss figures | **Unresolved discrepancy** — 7 lakh to 46 lakh trees across sources, no reconciliation found |
| Displacement figures (villages/households) | **Unresolved discrepancy** — 21 vs 24 villages, framing inconsistent |
| Panna Tiger Reserve ~70% core-area impact | Single-source estimate |
| Our rainfall trend analysis (Ken +29%, Betwa +37%, ratio 1.01→0.95) | Our-own-analysis, independently recomputed from raw CSVs — internally consistent, methodologically caveated (rainfall ≠ streamflow) |
| Canal-route vs. wider-district rainfall baseline pattern | Our-own-analysis, recomputed and confirmed from CSVs |
| Betwa flow direction / Raisen-Vidisha upstream of Lalitpur | Verified against Wikipedia's Betwa River article |
| Phase-II structure locations (Lower Orr, Neemkheda, Barari, Kotha, Kesari) | Verified — multiple independent sources agree |
| Lower Orr Dam serving Datia district specifically | **Verified implausible** — real OpenStreetMap district-boundary measurement shows the dam is 6.2 km from Shivpuri but 92.8 km from Datia; a 900 km² command area cannot bridge that gap. Datia's official beneficiary status stands, but not via this mechanism; **Unresolved** what mechanism, if any, actually applies |
| Cost comparison to local alternatives (₹880 cr / 44,000 ha) | Single-source input; our per-hectare recomputation (~2x, not 50-98x) is Our-own-analysis |
| Parasai-Sindh, Kol tribe, IWMI case-study figures | Single-source, not independently re-verified |

**Overall assessment:** obtaining NWDA's own primary PDFs materially upgraded
this document's evidentiary base — the central finding sharpened rather than
softened (most project water stays in the Ken basin; the interbasin transfer
itself is small and heavily consumed en-route), while several previously-wrong
or unverified claims got corrected using the government's own numbers: Damoh,
Banda, and Mahoba's mechanisms are now confirmed rather than guessed at, the
Bina Complex contradiction is resolved, and — importantly — an earlier claim
in this very document (~62% of the headline unaccounted for) is now corrected
to ~14.5%, a real but much smaller gap. What remains genuinely open (Datia's
basin mismatch, expenditure figures, tree/village counts) stays open rather
than forced to a false resolution.
