# Command Area Geo-boundaries (for rainfall lookup)

Source: `source-pdfs/kblp_index_map.pdf` (scanned raster) + a user-generated
vector trace (`~/Downloads/Jul 24 Screenshot from Vectorizer.svg`, auto-traced,
no semantic labels) + a full-page screenshot showing map + legend + both CCA
tables together. Method: read the **actual printed color swatches** in the
legend and in each table's "Colour of Command" column (ground truth, not
inferred from hue), then locate each color's polygon on the map body against
the printed grid (77–81°E / 23–26°N ticks on the frame).

Pixel calibration (for anyone re-deriving from the SVG): the map's neatline
border traces as one path with bbox `x:[14.3, 1588.0], y:[0.03, 1254.05]` in
the 1588x1254 canvas — that rectangle **is** 77–81°E x 26–23°N.
`lon = 77 + (x-14.3)/1573.7*4`, `lat = 26 - (y-0.03)/1254.02*3`.

## Definitive color key (read from the table swatches, not guessed)

| Command | CCA (ha) | Swatch color (as printed) |
|---|---|---|
| MP-A Enroute command | 96,751 | pink |
| MP-B High-level, Daudhan pump | 43,678 | orange |
| MP-C High-level, K-B Link pump | 42,096 | yellow |
| MP-D Panna & Hatta LIS | 90,101 | olive / dark yellow-green |
| MP-E Command of Ken L.B.C. | 174,742 | brown / tan |
| UP-A(i) Enroute, Jhansi & Mahoba | 17,488 | orange — **same color as MP-B** |
| UP-A(ii) New command, Mahoba | 37,564 | pale cream |
| UP-B Bariarpur R.B.C., Banda | 192,479 | salmon **cross-hatch** pattern |
| UP-C Lalitpur, by substitution | 3,533 | **no swatch printed** — likely not drawn as its own polygon |
| B-A Lower Orr Dam enroute | 90,000 | light pink / lilac |
| B-B Kotha Barrage | 20,000 | darker pink / salmon (distinct shade from B-A) |
| B-C Bina Complex | 96,000 | yellow — same family as MP-C, different location |

**Named-only in the legend, no CCA given in either table** (small, tightly
clustered around Chhatarpur/Khajuraho, ~24.75–25.3°N, 79.85–80.0°E):
Singhpur Command (red), Rangwan Command (bright green), Benisagar Command
(turquoise), Command of ongoing Bansujra Project (blue dotted/stippled — this
is what fragmented into ~280 tiny disconnected shapes when auto-vectorized;
that fragmentation is itself the tell that it's a stipple pattern, not a
solid fill or a river network).

**Important disambiguation the legend itself creates:** the *legend box*
lists "Bariarpur LBC and RBC Command (M.P.)" as **purple** — a different
polygon from *Table 1*'s "Command of Bariarpur R.B.C Ken Canal in Banda"
(**salmon cross-hatch**, 192,479 ha). Same name fragment, two different
colors/shapes on the map. Don't merge them.

## Table 1 — K-B Link Main Project commands

| # | Command | CCA (ha) | BBox (lat, lon) | Centroid | Confidence |
|---|---|---|---|---|---|
| MP-A | Enroute command | 96,751 | 25.2–25.5, 78.7–79.0 | 25.35, 78.85 | medium — pink shade shared with B-A, positioned by elimination (small patch near Jhansi/Mauranipur, distinct from the larger Lower Orr pink blob further west) |
| MP-B | High-level, Daudhan pump | 43,678 | 24.6–24.9, 79.9–80.1 | 24.75, 80.0 | high — orange patch directly between Chhatarpur and Khajuraho/Daudhan, area-matched (44,600 ha vs 43,678 ha CCA, 2% error) against the vector trace |
| MP-C | High-level, K-B Link pump | 42,096 | 24.8–24.95, 79.9–80.0 | 24.87, 79.95 | medium — yellow patch just south of Chhatarpur near Rangawan Dam |
| MP-D | Panna and Hatta LIS | 90,101 | 23.9–24.6, 79.6–80.3 | 24.25, 79.95 | medium — olive band running Panna→Hatta (Damoh) |
| MP-E | Command of Ken L.B.C. | 174,742 | 24.7–25.3, 79.9–80.6 | 25.0, 80.25 | medium-high — brown corridor along Ken R, Chhatarpur→Banda border, largest single MP command, visually distinct color |
| UP-A(i) | Enroute: Jhansi & Mahoba | 17,488 | 25.0–25.2, 79.7–79.9 | 25.1, 79.8 | medium — same orange as MP-B, disambiguated by the 25°N line: UP-A(i) sits just above/on it, MP-B sits well below (24.6–24.9) |
| UP-A(ii) | New command, Mahoba | 37,564 | 25.25–25.4, 79.8–80.0 | 25.32, 79.9 | medium — cream box explicitly labeled "ADDITIONAL COMMAND PROPOSED BY UP IN MAHOBA" on the map |
| UP-B | Bariarpur R.B.C. command, Banda | 192,479 | 25.3–25.9, 80.2–80.9 | 25.6, 80.55 | high — distinctive salmon cross-hatch covering most of Banda/Chitrakoot, unambiguous pattern |
| UP-C | Lalitpur, by substitution | 3,533 | — | — | **dropped** — too small an area to be worth separating in rainfall analysis (0.5% of total CCA) |

## Table 2 — Betwa Projects commands

| # | Command | CCA (ha) | BBox (lat, lon) | Centroid | Confidence |
|---|---|---|---|---|---|
| B-A | Enroute command, Lower Orr Dam | 90,000 | 24.85–25.35, 78.05–78.55 | 25.1, 78.3 | high — large, unambiguous pink/lilac blob between Shivpuri and Jhansi, matches "LOWER ORR DAM" label box directly |
| B-B | Kotha Barrage | 20,000 | 23.75–24.05, 77.85–78.15 | 23.9, 78.0 | high — distinct salmon patch at "KOTHA BARRAGE" label, west of Bina R |
| B-C | Bina Complex | 96,000 | 23.55–23.95, 78.6–78.95 | 23.75, 78.78 | high — yellow block at "MADIA DAM"/Sagar cluster, unambiguous position |

## What changed from the first pass (district-guess version)

The original boxes were built from real-world town/district coordinates, not
the map itself. This version reads the map's own swatches and grid. Biggest
corrections: MP-B/MP-C locations moved ~0.3-0.5° east (they sit right against
Daudhan/Khajuraho, not spread across the whole Chhatarpur district); B-A/B-B/
B-C are now high-confidence instead of guessed. MP-A, UP-A(i), UP-C stay
lower confidence because of genuine color reuse or missing swatches on the
map itself — not something more image analysis can resolve without OCR'd
text-to-shape linkage.

## Notes on how water gets to each box

- **MP-A/B/C/D/E**: all fed off Daudhan Dam on the Ken (24.72, 80.18) — either
  gravity canal (Ken LBC) or lift/pump schemes onto higher ground beside it.
- **UP-A/B/C**: fed off the same Daudhan/Ken system after it crosses into UP —
  Bariarpur P.U.W. (pick-up weir) feeds Bariarpur RBC into Banda.
- **B-A/B/C**: NOT fed by the K-B transfer at all — standalone Betwa Projects
  (Phase II framing), off local Betwa/Orr/Bina tributaries, no physical link
  to the Ken side.

## Next step

If you want rainfall per box rather than per centroid, sample a small grid
(e.g. 3x3, 0.15° spacing) inside each bbox and feed into
`fetch_route_rainfall.py`'s pattern (same Open-Meteo archive endpoint, no
key). Say the word and I'll generate that point list + run the fetch.
