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
| `index.html` | The whole UI. Talks to the API; holds no durable state. |
| `app.py` | API + static server + SQLite. Stdlib only. |
| `ingredients.csv` | Nutrient table, per unit. **Seed + hand-edit path.** |
| `targets.csv` | Per-meal / daily / weekly nutrient targets. Order = gap priority. |
| `recipes.csv` | Seed dishes matched against the plate. |
| `deploy/` | systemd unit + deploy script for the slate host. |

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
| `POST /api/plates` | save a plate |
| `POST /api/plates/delete` | `{id}` |
| `POST /api/recipes` | save a user recipe |
| `POST /api/recipes/delete` | `{id}` — user recipes only; seeds are protected |
| `POST /api/import` | one-time localStorage migration |

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
