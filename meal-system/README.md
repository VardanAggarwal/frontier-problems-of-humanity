# Balanced Meal Planner

A pantry-driven, protein-gated meal planner. Pick a meal, build a plate, and watch
the nutrient gaps fill in real time. Tracks per-plate, per-day, and 7-day totals,
and suggests dishes your plate can already make.

Data lives in **SQLite** (`meals.db`), served by a stdlib-only Python API
(`app.py`, ~12 MB RSS, zero dependencies). Saved plates and recipes are
server-side, so your phone and laptop see the same history.

## Files

| File | Role |
|------|------|
| `index.html` | The planner UI — build one plate, watch the gaps fill. |
| `menu.html` | The menu generator — proposes the horizon's meals, scores them, lets you edit. |
| `shop.html` | The shopping list — shelf-life-aware, driven by the menu. |
| `app.py` | API + static server + SQLite. Stdlib only. |
| `ingredients.csv` | Nutrient table per unit, **+ shelf life, pack size, topper flag.** Hand-edit path. |
| `targets.csv` | Per-meal / daily / weekly nutrient targets. Order = gap priority. |
| `recipes.csv` | Seed dishes (67): `core` defines the dish, `opt` is the garnish layer, **`effort` is minutes**. |
| `deploy/` | systemd unit + deploy script for the slate host. |

## The three pages are one loop

```
menu.html   plan the week   ─┐
                             ├─ shop.html   buy for the plan   ─┐
index.html  cook & log      ─┘                                  │
     ▲                                                          │
     └──────────────  stock  ◀─────────────────────────────────┘
```

A **menu slot is a plate with `planned=1`** — same table, same nutrition math. Cook it
("cook" a slot) and it flips to a real plate *and consumes stock*. A plan moves nothing;
eating does.

## Menu generator

Answers the question the shopping list can't: *what am I actually going to eat?* Naively
optimising nutrients over raw ingredients does not work — a solver told to hit every target
per calorie returns **398 cloves of garlic**, because garlic is 4 kcal and carries vitamin C,
so its "efficiency" is unbeatable and nothing forces the basket to be edible. The unit of
nutrition is the **plate**, not the nutrient. So the generator plans dishes:

1. **Pick a dish per slot**, weighted by *your own history* — dishes whose ingredients appear
   in your logged plates score higher, so the week looks like your cooking. Variety is a hard
   rule (no dish twice in 3 days), not a soft penalty: a penalty just loses to a high affinity
   score, which is how every lunch became dal khichdi.
2. **Enforce the daily contract** (§8) — ≥3 eggs, a legume, a green at lunch *and* dinner, a
   probiotic, flax + a second seed, a sour on every iron-heavy plate.
3. **Repair nutrient gaps — toppers only** (`topper=1` in `ingredients.csv`), one serving per
   day. That bound is what keeps a repair edible: it can reach for a spoon of pumpkin seeds,
   never for four kilos of soya.
4. **Close the protein gap** with a 4th egg or whey — protein is structurally unfixable by
   toppers (seeds carry none), so it gets its own pass.
5. **Hold the calorie ceiling.** Everything above only *adds*; without a trim pass a "balanced"
   week lands 500 kcal/day over and the deficit — the whole point — is gone.

**The micro layer is not optional.** `opt` in `recipes.csv` holds flax, lemon, moringa, seeds.
Treating it as "nice to have" is correct for *recognising* a dish and catastrophic for
*planning* one, because that layer carries omega-3, calcium, zinc, magnesium and the
iron-absorption partner. The generator places `core` **and** `opt` as real items — capped at 3
per slot, ranked sour → green → seed. (Uncapped, a curd bowl picks up flax *and* pumpkin *and*
til *and* guava *and* papaya: ~300 kcal of toppers that blow the ceiling and crowd out carbs.)

## Effort — the axis that decides whether a plan survives a Tuesday

`effort` = active minutes, assuming the §6 prep blocks are done. This is the real variable, and
it was missing from the data model entirely. Indian home cooking is structurally expensive — a
tadka, a bhuna, a gravy, then rice, then a sabzi. The global one-pan and assembly formats hit
the same nutrition in a third of the time, which is what §8 "Beyond Indian" already said.

| Tier | Dishes | Protein/dish | **Protein per 100 kcal** | Fat/dish |
|---|---|---|---|---|
| Assembly ≤6 min | 16 | 14.9 g | **5.4 g** | 8.8 g |
| One-pan 8–15 min | 36 | 13.3 g | **5.1 g** | 7.2 g |
| Multi-step 20 min+ | 15 | 16.7 g | **5.8 g** | 5.5 g |

**Effort is nearly free.** A no-cook bowl delivers 5.4 g protein per 100 kcal against 5.8 g for a
25-minute gravy. Cooking 21 min/day instead of 80 costs ~7% of protein density — nothing. Pick
the effort mode on `menu.html`; the generator caps dish effort and breaks ties toward cheaper
dishes.

**The one real cost is fat.** Assembly nutrition rides on nuts, seeds, peanut butter and curd, so
a no-cook week drifts fat-heavy and carb-light. Fat is **derived, not a column** — Atwater gives
`fat = (kcal − 4·protein − 4·carbs) / 9` from data already present — and the trim pass now cuts
the biggest *fat* contributor, not the biggest *calorie* contributor. Going by calories picked
rice (zero fat, all the carbs) and made the carb shortfall worse while the peanut butter sat
there untouched.

### Cuisine

Tagged per dish (`global · greek · med · levant · italian · mexican · asian · north · south ·
west · chaat`). Without the tag the set silently drifted **6 → 14 South Indian dishes**, because
the natural dish for coccinia, beetroot, amaranth and vermicelli is a poriyal or an upma — an
"every ingredient needs a home" rule quietly imports a cuisine.

Calories and protein look like a deadlock (120 g inside 1,775 kcal) but they're a **trade**:
half a cup of rice is ~100 kcal for 2 g of protein, a whey scoop is 120 kcal for 24 g. The
generator is allowed to shave filler to buy room for protein — the move any human would make.

When it can't close a gap, it **says so** rather than flashing green.

## Shopping list

The point is **availability**: every dish you planned should be cookable when you go to cook
it. It isn't three hand-kept lists — it's one demand model, bucketed by shelf life.

```
need(ingredient) = the planned menu                    # what you will actually eat, dish by dish
                   ↳ falls back to max(eating rate, pinned dishes) if no menu exists
                  × min(horizon, shelf life)           # the cap that matters
                  − stock
```

`min(horizon, shelf)` is the whole trick. Pick a **month** and the dals and rice
scale to 30 days, but spinach still comes back as one bunch — you cannot stock a
month of spinach. That cap is also what sorts every item into its run:

| Shelf | Run |
|---|---|
| ≤ 3 days | **Fresh** — greens, coriander, sprouts |
| 4–14 days | **Weekly** — eggs, curd, tofu, batter, veg, fruit |
| > 14 days | **Monthly staples** — dals, rice, millets, seeds, whey, oil |

**Stock is a real number, not the `pantry` flag.** Saving a plate on the planner
consumes its items; ticking a line on the shopping list adds the pack back. That
closes the loop, so *"✓ makeable right now"* and *"one buy away"* — which run the
same recipe matcher the planner uses, against stock instead of the plate — are
trustworthy. Stock drifts when you cook off-app; correct it inline any time.

First run: hit **Seed from pantry list** once (assumes a full pack of everything
flagged `pantry=1`), then fix whatever's wrong.

Shelf life and pack size are estimates in `ingredients.csv` (`shelf`, `pack`,
`packname`). Tune them and re-run `import-csv` — they only affect the shopping
math, never the nutrition.

## Data model

`meals.db` is the source of truth. The CSVs are the **seed and the hand-edit
path** — they're still how you curate the food data:

```bash
vim ingredients.csv          # edit as before
python3 app.py import-csv    # upsert into the DB
```

`import-csv` is an upsert, so it's safe to re-run. It never touches your saved
plates, and it won't clobber recipes you created in the app (those are
`is_user=1`; seed recipes are replaced). `export-csv` round-trips recipes back
out to `recipes.csv` if you want to commit ones you made in the UI.

## Run locally

```bash
python3 app.py serve     # http://127.0.0.1:8200
```

First boot seeds the DB from the CSVs automatically. `MEALS_DB`, `HOST`, and
`PORT` are env-overridable.

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/data` | ingredients + targets + recipes |
| `GET /api/plates` | all saved plates |
| `POST /api/plates` | save a plate — **consumes stock** |
| `POST /api/plates/delete` | `{id}` — **restores stock** |
| `POST /api/recipes` | save a user recipe |
| `POST /api/recipes/delete` | `{id}` — user recipes only; seeds are protected |
| `POST /api/import` | one-time localStorage migration |
| `GET /api/stock` | `{ing_id: qty}` — what's in the kitchen, in serving units |
| `POST /api/stock` | `{id, qty}` — set absolute |
| `POST /api/stock/add` | `{id, delta}` — tick a shopping line |
| `POST /api/stock/seed` | one full pack of every `pantry=1` ingredient |
| `GET /api/pins` | `{recipe_id: perweek}` |
| `POST /api/pins` | `{id, perweek}` — `0` unpins |
| `GET /api/menu` | the planned menu (plates with `planned=1`) |
| `POST /api/menu` | `{slots:[…]}` — replace the menu over the range they span |
| `POST /api/menu/cook` | `{id}` — slot → real plate; **now** it consumes stock |
| `POST /api/menu/clear` | `{from, to}` |

## Adding a recipe

Edit `recipes.csv`, run `import-csv`. **Not** a direct `INSERT` into `meals.db` — the DB is
gitignored runtime state, so an inserted recipe would live on one machine and vanish on a fresh
clone or deploy. The CSV is the versioned source; the DB is what the app actually reads
(`/api/data` never touches a CSV).

Recipes you create *in the app* are the opposite case: they're `is_user=1`, live only in the DB,
and `import-csv` deliberately won't clobber them. `export-csv` round-trips them back out.

The menu generator is only as good as this file — its variety ceiling is the number of dishes
per slot. Two checks worth running after an edit:

```bash
# every ingredient has a recipe home (§8: "no priority ingredient goes unused")
# and no dish references an ingredient id that doesn't exist
python3 - <<'EOF'
import csv
rows=[r for r in csv.DictReader([l for l in open('recipes.csv') if l.strip() and not l.startswith('#')])]
ings={r['id'] for r in csv.DictReader([l for l in open('ingredients.csv') if l.strip() and not l.startswith('#')])}
used=set().union(*[set(r['core'].split())|set(r['opt'].split()) for r in rows])
print('orphan ingredients:', ' '.join(sorted(ings-used)) or 'none')
print('bad refs:', [(r['id'],i) for r in rows for i in r['core'].split()+r['opt'].split() if i not in ings] or 'none')
EOF
```

## Adding a nutrient

One column in `ingredients.csv`, one row in `targets.csv`, one entry in `app.py`'s
`NUTRIENTS` — it then flows into the planner's gap engine, the shop list and the menu scorer
automatically, and `_migrate()` ALTERs the existing DB on next boot. Magnesium and potassium
were added this way. **You cannot cover what you don't measure**: before magnesium was a
column, a menu could be 40% short on it and report all-green.

B12, D3, iodine and the calcium top-up stay *out* of the food math on purpose — they're
supplement-covered (§9) and live in `NONFOOD` reminders. Selenium and choline are untracked
because 3–4 eggs a day makes them permanently green; a column would be noise, not signal.

## Deploy

Target is the slate host (`ubuntu@140.245.216.42`). The planner runs entirely
beside slate — its own systemd service, port (8200), data dir
(`/home/ubuntu/meal-system-data`), and Caddy site block. Slate is never touched;
the Caddyfile is backed up and `caddy validate`d before any reload.

```bash
./deploy/deploy.sh                 # ship code + restart the service on :8200
./deploy/deploy.sh <duckdns-label> # ...and wire up https://<label>.duckdns.org
```

**The DuckDNS subdomain must exist first.** The token only updates the IP of
domains you already own, so create the label at
[duckdns.org](https://duckdns.org) (login → add domain), then pass it to the
script — it registers the IP, adds the label to the 5-minutely refresh in
`~/duckdns/duck.sh`, writes the Caddy block, and turns on basic auth reusing
slate's `AUTH_USER` / `AUTH_PASS`.

Rollback is `sudo systemctl disable --now meals` plus restoring the
`/etc/caddy/Caddyfile.bak.*` the script leaves behind.

## Migrating off localStorage

Older versions kept plates in the browser. On first load the app lifts any
`mp.saved` / `mp.recipes` into the DB once (`POST /api/import`) and sets
`mp.migrated`. Nothing is lost; open the old browser once against the new
deploy.

## Making it generic (later)

Food data is in the DB/CSVs, but the personal config is still hardcoded in
`index.html`:

- `KCAL` — daily calorie baseline (a deficit midpoint).
- `MEALS` — per-meal protein targets, and which meals track micros.
- `BLURBS` — per-nutrient coaching lines.
- `NONFOOD` — supplement reminders (B12, D3, …).

Moving these into a `settings` table + a small editor UI is what turns this from
a personal tool into one anyone can use.
