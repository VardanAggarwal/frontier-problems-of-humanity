# Nutrition Data Sources

Candidate external datasets for mapping dietary habits → nutrition profiles, and for
the bioavailability layer (`(ingredient, nutrient, form) → absorbed`).

Compiled 2026-07-17.

---

## Composition + recipes (Indian)

### Indian Nutrient Databank (INDB)
- Code/data: https://github.com/lindsayjaacks/Indian-Nutrient-Databank-INDB-
- Paper: https://pmc.ncbi.nlm.nih.gov/articles/PMC11277795/
- Also: https://www.sciencedirect.com/science/article/pii/S2475299124017244
- Org page: https://www.anuvaad.org.in/indian-nutrient-databank/

Closest match to the dish→ingredient→nutrient chain. Built in two stages:
- Stage 1: food-item composition, n=1,095 (derived from ICMR-NIN IFCT 2017, gaps
  filled from IFCT 2004 + UK/US tables)
- Stage 2: n=1,014 Indian recipes with per-ingredient quantities, total recipe
  weight, servings, serving size — each ingredient matched to a stage-1 item

Open access. Nutrient values per 100g and per serving.

### Indian Food Composition Tables (IFCT) 2017 — ICMR-NIN
- Online: https://ifct2017.github.io/
- npm package + Zenodo (v2.0.10): https://zenodo.org/records/7088653
- FAO listing: https://www.fao.org/food-composition/tables-and-databases/detail/(country--date)-title-9/en
- Table/column review: https://www.academia.edu/69556938/Indian_Food_Composition_Table_1939_2017_Review
- PDF mirrors: https://www.researchgate.net/publication/313226719_Indian_food_Composition_Tables

528 foods × 151 components. Authoritative Indian base layer; INDB stage 1 is built
on it. npm package `ifct2017` exposes compositions, nutrient columns, recommended
intakes, food pictures, hierarchical nutrient data.

**12 tables**, including the ones that matter for bioavailability:
- Table 10 — Polyphenols
- Table 11 — Oligosaccharides, Phytosterols, Saponins, **Phytates**
- Phosphorus broken out as total P / phytin-P / phytin-P as % of total
- Also: proximates + fibre, water-soluble vitamins, fat-soluble vitamins,
  carotenoids, minerals + trace elements, starch + individual sugars, full fatty
  acid profile, amino acid profile, organic acids, edible oils/fats fatty acids

> The antinutrient layer is **not** missing — phytate and polyphenols sit in the
> same tables as the minerals.

### Recipe corpora (lower quality, larger n)
- Kaggle, 725 dishes w/ recipes + ingredients + nutrients + cooking instructions:
  https://www.kaggle.com/datasets/kashyap077/indian-recipes-ingredients-nutrition-and-cooking
- Mendeley, 6000+ Indian recipes (scraped from archanaskitchen.com):
  https://data.mendeley.com/datasets/xsphgmmh7b/1
  Generator code: https://github.com/kanishk307/IndianFoodDatasetGeneration
  Fields: RecipeName, Ingredients, Prep/Cook/Total time, Servings, Cuisine,
  Course, Diet, Instructions

---

## Composition (global / branded)

### USDA FoodData Central
- Home: https://fdc.nal.usda.gov/
- Bulk download (CSV + JSON): https://fdc.nal.usda.gov/download-datasets/
- API guide: https://fdc.nal.usda.gov/api-guide/
- OpenAPI spec: https://fdc.nal.usda.gov/api-spec/fdc_api.html
- API key signup: https://fdc.nal.usda.gov/api-key-signup/
- data.gov: https://catalog.data.gov/dataset/fooddata-central
- Community REST wrapper: https://github.com/littlebunch/fdc-api

Data types: Foundation Foods, SR Legacy, FNDDS 2021-2023, Global Branded Food
Products Database. Full Download bundles all types. Two API endpoints (Food Search,
Food Details). `DEMO_KEY` works for exploration at low rate limits.

**Branded database** is the relevant one for the demand-gen angle — resolving a
specific purchased product (which tofu, which eggs) to a nutrient profile.

---

## Cooking methods

### USDA Table of Nutrient Retention Factors, Release 6 (2007)
- PDF: https://www.ars.usda.gov/ARSUserFiles/80400525/Data/retn/retn06.pdf
- Dataset: https://agdatacommons.nal.usda.gov/articles/dataset/USDA_Table_of_Nutrient_Retention_Factors_Release_6_2007_/24660888
- ARS landing: https://www.ars.usda.gov/northeast-area/beltsville-md-bhnrc/beltsville-human-nutrition-research-center/methods-and-application-of-food-composition-laboratory/mafcl-site-pages/nutrient-retention-factors/
- Marketplace mirror: https://www.johnsnowlabs.com/marketplace/usda-nutrient-retention-factors/
- Worked example (recipe w/ yield + retention applied):
  https://www.ars.usda.gov/ARSUserFiles/80400525/Articles/ndbc26_recipe.pdf
- Yields/retention for bacon, liver, sausages:
  https://www.ars.usda.gov/ARSUserFiles/80400525/Articles/IFDC5_YldRetn.pdf

Keyed `(food, nutrient, method) → retention %`. 16 vitamins, 8 minerals, alcohol,
~290 foods. Methods: baked, boiled, reheated, broiled, pared, drained, pan-fried, etc.

**Right shape, wrong quantity, wrong forms.** Retention ≠ bioavailability (how much
survives cooking, not how much is absorbed). No soaked / sprouted / ground /
fermented / pressure-cooked. Mostly Western foods.

### FAO — weight yield + retention factors
- https://www.fao.org/uploads/media/bognar_bfe-r-02-03.pdf

### Review: preparation/cooking impact on vegetables & legumes
- https://www.sciencedirect.com/science/article/pii/S1878450X15000207

---

## Bioavailability — the generic model

The key finding: for phytate-chelated minerals, bioavailability is **predicted from
a molar ratio**, not measured per ingredient. Compute `Phy:Zn` / `Phy:Fe` from two
composition numbers (both in IFCT) and read off published thresholds.

### Maize — fermentation ± soaking/germination (Frontiers in Nutrition, 2024)
- https://www.frontiersin.org/journals/nutrition/articles/10.3389/fnut.2024.1478155/full
- PMC: https://pmc.ncbi.nlm.nih.gov/articles/PMC11646714/

Phytate reduction: soak+germinate+ferment (Lp299) up to **85.6%**; raw flour
fermented w/ Lp299 **65.3%**, w/ yogurt **68.7%**; spontaneous fermentation **51.8%**.

Molar ratios, soak+germinate+ferment vs raw:
- Phy:Zn 40.76 → 7.77 (**81% reduction**)
- Phy:Fe 41.42 → 6.24 (**85% reduction**)

### Sorghum — soaking + germination (PLOS One)
- https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0025512
- PMC: https://pmc.ncbi.nlm.nih.gov/articles/PMC3189212/

Phytate reduced **23.6–32.4%** (soaking), **24.9–35.3%** (germination).
Covers phytase activity during the process.

### Faba bean — soaking + sprouting (PMC)
- https://pmc.ncbi.nlm.nih.gov/articles/PMC4252429/

Phytate reduced **26.9–32.5%** (soaking), **28.0–34.9%** (sprouting).

### Grains — germination + fermentation, Fe/Zn bioaccessibility
- https://www.researchgate.net/publication/6822367_Influence_of_germination_and_fermentation_on_bioaccessibility_of_zinc_and_iron_from_food_grains

### Cross-study observation
Soaking ~24–33% and germination ~25–35% phytate reduction across **three unrelated
crops** (sorghum, faba bean, maize). Suggests form transforms are roughly
food-independent — a transform table keyed on *method*, not ingredient.

Soaking at 45–65°C, pH 5.0–6.0 → 26–100% phytate enzymatically hydrolysed.

---

## The factorization

```
bioavailable Zn = f(Phy:Zn after applying form transforms)
```

Three tables that compose, instead of an `(ingredient, nutrient, form)` cross-product:

| Layer | Source | Status |
|---|---|---|
| phytate + mineral per food | IFCT 2017 Tables 10/11 | **exists**, 528 Indian foods |
| method → % phytate reduction | literature, ~5 methods | roughly food-independent |
| molar ratio → absorption | published thresholds | established model |

A formula extrapolates to foods nobody measured. A lookup table doesn't.

Collapses the cuisine/cooking-style layers into a *form* attribute: bhuna is not a
style to model, it's a transform `(til, whole) → (til, roasted)`. Dishes decompose
into ingredients-in-forms; INDB already supplies dish→ingredient quantities, so the
dish layer is derived, never stored.

---

## Caveats

- The molar-ratio model is verified here for **one mechanism family only**: phytate
  chelating Fe/Zn/Ca. Whether fat-solubility, heat lability, oxalates, or tannins
  have equally clean generic models is **unverified** — not checked.
- Form-transform percentages come from **three studies on three crops**. Consistent,
  but three.
- Everything above was fetched and read. Any mechanism list not appearing here with
  a URL (lycopene/fat, curcumin/piperine, tannins/non-heme iron, cell-wall matrix)
  was asserted from memory in conversation and is **not yet sourced**.

---

## What is now local (2026-07-19)

| Layer | File | Source actually used |
|---|---|---|
| Indian composition | `ingredients.csv` (50 new rows) | IFCT 2017 via `ifct2017` npm — read directly, not through INDB |
| Non-Indian composition | `ingredients.csv` (oats, tofu, pb, pumpkin seeds, chia) | INDB repo `UK_fct.xlsx` (144 foods) + `US_fct.xlsx` (54) |
| Phytate + molar ratios | `phytate.csv` | IFCT Table 11 + mineral table, computed |
| Form transforms | `forms.csv` | the fermentation/soaking literature above |
| Cooking retention | `retention.csv` | USDA RF6 as shipped in the INDB repo (`USDA_nrf.xlsx`) |
| Dish → ingredient chain | not yet imported | INDB `recipes.xlsx` — 1014 recipes / 10271 lines |

**INDB does not ship an Indian ingredient table.** Its README requires `NIN_fct` to be
requested from ICMR-NIN separately — so INDB's Indian composition layer *is* IFCT 2017, which
we already read directly. What INDB uniquely adds is (a) the 198 UK/US foods IFCT lacks,
(b) USDA RF6 pre-extracted, and (c) the recipe corpus. `INDB.xlsx` itself is nutrients per
*recipe*, not per ingredient — the wrong grain for this system.

**Licence:** the INDB repo carries no LICENSE file. The paper is open access and the data are
published for reuse, but "no licence" is not the same as "permissively licensed". Fine for a
private planner; check before anything public or commercial. The underlying UK COFID and USDA
data are separately open; IFCT 2017 is ICMR-NIN copyright.

### Corrections this produced
- Pumpkin seeds were carrying **zinc 2.2 mg/15 g** and the label "the zinc specialist".
  UK FCT says **0.99 mg** — the estimate was 2.2x high and the label overstated.
- Rolled oats zinc 1.5 → **0.92 mg/40 g**.
- Tofu: UK FCT's steamed tofu is 73 kcal/8.1 g protein/1.2 mg iron per 100 g vs the 130/11/2.7
  in use. Firmness genuinely varies this much, so the row was flagged, **not** overwritten.
