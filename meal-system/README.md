# Balanced Meal Planner

A pantry-driven, protein-gated meal planner. Pick a meal, build a plate from your
pantry, and watch nutrient gaps fill in real time. Tracks per-plate, per-day, and
7-day-window totals. All state lives in the browser (`localStorage`) — no account,
no backend required.

## Files

| File | Role |
|------|------|
| `index.html` | The whole app — UI + logic. Loads the CSVs at startup. |
| `ingredients.csv` | Nutrient table, one row per ingredient (values per unit). |
| `targets.csv` | Per-meal / daily / weekly nutrient targets. |
| `recipes.csv` | Dish definitions matched against the plate. |
| `server.py` | **Optional** local helper (see below). |

Edit the CSVs — not the HTML — to change the food data. Comments at the top of
each CSV document the columns.

## Run / deploy

It's a static site. Serve the folder over any HTTP server:

```bash
cd meal-system
python3 -m http.server 8777
# open http://localhost:8777/
```

To deploy, upload the folder to any static host / web server. `index.html` is the
entry point. (Opening `index.html` directly via `file://` won't work — browsers
block local file reads; it needs to be served over HTTP.)

### Optional: `server.py`

The planner saves user-created recipes to `localStorage` by default. Run
`python3 server.py` if you instead want saved recipes written back to
`recipes.csv` on this machine (a tiny write API the app calls when present, and
silently skips when absent). Not needed for a normal deploy.

## Making it generic (later)

The food data is already externalized in the CSVs. The remaining personalization
is hardcoded in `index.html` and would need a settings/import UI to make this a
tool for anyone:

- `KCAL` — daily calorie baseline (currently a deficit midpoint).
- `MEALS` — per-meal protein targets and which meals track micros.
- `BLURBS` — the per-nutrient coaching lines.
- `NONFOOD` — supplement reminders (B12, D3, etc.).
