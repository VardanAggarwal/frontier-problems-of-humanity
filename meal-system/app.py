#!/usr/bin/env python3
"""Balanced Meal Planner — SQLite-backed API + static server.

Stdlib only (sqlite3 + http.server). No dependencies, ~20MB RSS.

Source of truth is meals.db. The CSVs are the *seed* and stay the hand-edit
path: edit a CSV, run `import-csv`, and the rows are upserted into the DB.
User-created recipes and saved plates live only in the DB.

Usage:
  python3 app.py serve                 # API + static files (default)
  python3 app.py import-csv            # upsert ingredients/targets/seed recipes from the CSVs
  python3 app.py export-csv            # write ingredients/targets/recipes back out to CSV

Env:
  MEALS_DB    path to the SQLite file   (default: ./data/meals.db)
  PORT        listen port               (default: 8200)
  HOST        bind address              (default: 127.0.0.1)

API:
  GET  /api/data            -> {ingredients, targets, recipes}
  GET  /api/plates          -> [{id, date, meal, items:[{id, qty}]}]
  POST /api/plates          -> save a plate     {date, meal, items}   (decrements stock)
  POST /api/plates/delete   -> {id}                                   (restores stock)
  POST /api/recipes         -> save a recipe    {name, meals[], core[], opt[], method}
  POST /api/recipes/delete  -> {id}   (user recipes only)
  POST /api/import          -> one-time localStorage migration {plates[], recipes[]}
  GET  /api/stock           -> {ing_id: {qty, bought}}  kitchen contents + freshness clock
  POST /api/stock           -> {id, qty}              set absolute
  POST /api/stock/add       -> {id, delta}            tick a shopping line (delta = packs bought)
  POST /api/stock/seed      -> assume one full pack of every pantry=1 ingredient
  GET  /api/pins            -> {recipe_id: perweek}   dishes you want to stay able to make
  POST /api/pins            -> {id, perweek}          perweek = 0 unpins
  GET  /api/menu            -> the planned menu (plates with planned=1 — intended, not eaten)
  POST /api/menu            -> {slots:[...]}          replace the menu over the range they span
  POST /api/menu/slot       -> save/edit one slot
  POST /api/menu/cook       -> {id}   slot -> real plate; NOW it consumes stock
  POST /api/menu/clear      -> {from, to}
"""
import csv
import http.server
import json
import os
import socketserver
import sqlite3
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('MEALS_DB', os.path.join(DIR, 'data', 'meals.db'))
PORT = int(os.environ.get('PORT', 8200))
HOST = os.environ.get('HOST', '127.0.0.1')

# ingredient nutrient columns, in CSV order. Adding one here + in both CSVs is all it takes:
# it flows into the planner's gap engine, the shop list and the menu scorer automatically.
# omega3 = plant ALA (barely converts to EPA/DHA); omega3_dha = pre-formed DHA/EPA
# (egg/fortified/algae) that needs no conversion. They are DIFFERENT molecules — tracked
# as separate nutrients so the planner never sums flax-ALA and egg-DHA into one number.
NUTRIENTS = ['kcal', 'protein', 'carbs', 'fibre', 'iron', 'calcium',
             'vitc', 'folate', 'omega3', 'omega3_dha', 'zinc', 'vita', 'magnesium', 'potassium']
FLAGS = ['pantry', 'base', 'green', 'probiotic', 'topper']
# shopping columns — shelf life (days) decides the run, pack converts need -> what you buy
SHOP = ['shelf', 'pack', 'packname']
# lead-time columns — hours of ahead-work (soak/sprout) before an ingredient is cookable
PREP = ['lead', 'prep']
# prep-output columns — a row you MAKE (soaked rajma, bhuna base) rather than buy.
#   makes = space-sep raw input ids it's produced from ('' = a normal ingredient, not a prep output)
#   keep  = 1 = a standing prep you always want a batch of ready on hand
MADE = ['makes', 'keep']
# gating columns — the FLAG escape hatch for absorption effects that are real but unquantified.
#   needform = the forms.csv id that must be applied before this row's `gated` nutrients count
#   gated    = space-sep nutrient keys NOT to credit until then (whole til's calcium, whole flax's ALA)
# A flag, not a multiplier: we know the direction, we do not have the number, and inventing one
# would be worse than showing nothing. The planner zeroes a gated nutrient and says why.
GATE = ['needform', 'gated']
# provenance — where this row's numbers CAME FROM. The whole ifct table lives in the DB
# (542 foods x 421 components); a row that names an ifct_code and a grams basis can have its
# nutrients REGENERATED from the source at any time (`python3 app.py ifct-derive`). A row with
# no ifct_code is, by definition, still an estimate — and now visibly so rather than silently.
SRC = ['ifct_code', 'grams', 'grams_src']
# columns added after a release — ALTERed onto the existing tables by _migrate()
MIGRATIONS = {
    'ingredients': {'shelf': 'INT DEFAULT 30', 'pack': 'REAL DEFAULT 1', 'packname': "TEXT DEFAULT ''",
                    'topper': 'INT DEFAULT 0',
                    'magnesium': 'REAL DEFAULT 0', 'potassium': 'REAL DEFAULT 0',
                    'omega3_dha': 'REAL DEFAULT 0',
                    'needform': "TEXT DEFAULT ''", 'gated': "TEXT DEFAULT ''",
                    'ifct_code': "TEXT DEFAULT ''", 'grams': 'REAL DEFAULT 0',
                    'grams_src': "TEXT DEFAULT ''",
                    'lead': 'REAL DEFAULT 0', 'prep': "TEXT DEFAULT ''",
                    'makes': "TEXT DEFAULT ''", 'keep': 'INT DEFAULT 0'},
    'plates': {'planned': 'INT DEFAULT 0', 'recipe_id': "TEXT DEFAULT ''"},
    'recipes': {'cuisine': "TEXT DEFAULT 'neutral'", 'effort': 'INT DEFAULT 15',
                # amounts = 'id:grams ...' per serving (INDB). src = where the dish came from.
                'amounts': "TEXT DEFAULT ''", 'src': "TEXT DEFAULT ''"},
    # bought_at, NOT updated_at: freshness is measured from the last PURCHASE. updated_at moves
    # every time you cook, so using it would silently reset the clock each time you ate some.
    'stock': {'bought_at': "TEXT DEFAULT ''"},
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS ingredients(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, unit TEXT, default_qty REAL DEFAULT 1,
  role TEXT, pantry INT DEFAULT 0, base INT DEFAULT 0, green INT DEFAULT 0,
  probiotic INT DEFAULT 0, topper INT DEFAULT 0, note TEXT DEFAULT '',
  kcal REAL DEFAULT 0, protein REAL DEFAULT 0, carbs REAL DEFAULT 0, fibre REAL DEFAULT 0,
  iron REAL DEFAULT 0, calcium REAL DEFAULT 0, vitc REAL DEFAULT 0, folate REAL DEFAULT 0,
  omega3 REAL DEFAULT 0,         -- plant ALA (does not convert well to EPA/DHA)
  omega3_dha REAL DEFAULT 0,     -- pre-formed DHA/EPA: egg/fortified/algae, directly usable
  zinc REAL DEFAULT 0, vita REAL DEFAULT 0,
  magnesium REAL DEFAULT 0, potassium REAL DEFAULT 0,
  shelf INT DEFAULT 30, pack REAL DEFAULT 1, packname TEXT DEFAULT '',
  lead REAL DEFAULT 0,           -- hours of ahead-work (soak/sprout) before it can be cooked
  prep TEXT DEFAULT '',
  makes TEXT DEFAULT '',         -- prep OUTPUT: space-sep raw input ids it's made from ('' = normal ingredient)
  keep INT DEFAULT 0,            -- 1 = standing prep, always want a batch ready
  sort INT DEFAULT 0
);
CREATE TABLE IF NOT EXISTS stock(
  ing_id TEXT PRIMARY KEY, qty REAL DEFAULT 0, updated_at TEXT,
  bought_at TEXT DEFAULT ''      -- last time this was BOUGHT. Freshness clock; cooking never resets it.
);
CREATE TABLE IF NOT EXISTS pins(
  recipe_id TEXT PRIMARY KEY, perweek REAL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS targets(
  fname TEXT PRIMARY KEY, nkey TEXT NOT NULL, name TEXT, unit TEXT, cadence TEXT,
  daily REAL DEFAULT 0, meal REAL DEFAULT 0, permeal INT DEFAULT 1, sort INT DEFAULT 0
);
CREATE TABLE IF NOT EXISTS recipes(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, meals TEXT DEFAULT '', core TEXT DEFAULT '',
  opt TEXT DEFAULT '', method TEXT DEFAULT '', is_user INT DEFAULT 0,
  cuisine TEXT DEFAULT 'neutral',
  effort INT DEFAULT 15          -- ACTIVE minutes. The axis the generator optimises against.
);
CREATE TABLE IF NOT EXISTS plates(
  id TEXT PRIMARY KEY, date TEXT NOT NULL, meal TEXT NOT NULL, created_at TEXT,
  planned INT DEFAULT 0,      -- 1 = a menu slot (intended), 0 = a plate (eaten)
  recipe_id TEXT DEFAULT ''   -- the dish this slot was generated from, for display
);
CREATE TABLE IF NOT EXISTS plate_items(
  plate_id TEXT NOT NULL REFERENCES plates(id) ON DELETE CASCADE,
  ing_id TEXT NOT NULL, qty REAL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_plates_date ON plates(date);
CREATE INDEX IF NOT EXISTS idx_items_plate ON plate_items(plate_id);
"""


def db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys = ON')
    c.execute('PRAGMA journal_mode = WAL')   # concurrent reads while writing
    return c


def _migrate(c):
    """Add columns introduced after a table was first created (CREATE IF NOT EXISTS won't)."""
    for tbl, cols in MIGRATIONS.items():
        have = {r['name'] for r in c.execute(f'PRAGMA table_info({tbl})')}
        for k, decl in cols.items():
            if k not in have:
                c.execute(f'ALTER TABLE {tbl} ADD COLUMN {k} {decl}')


def init_db():
    with db() as c:
        c.executescript(SCHEMA)
        _migrate(c)


# ---------- CSV seed / import ----------

def _rows(path):
    """Read a CSV, skipping the leading `#` comment lines."""
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        lines = [ln for ln in f if ln.strip() and not ln.lstrip().startswith('#')]
    return list(csv.DictReader(lines))


def _num(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def import_csv(verbose=True):
    """Upsert ingredients + targets + seed recipes from the CSVs.

    User-created recipes (is_user=1) and saved plates are never touched.
    Seed-recipe rows are replaced, so editing recipes.csv still works.
    """
    init_db()
    ing = _rows(os.path.join(DIR, 'ingredients.csv'))
    tgt = _rows(os.path.join(DIR, 'targets.csv'))
    rec = _rows(os.path.join(DIR, 'recipes.csv'))
    with db() as c:
        cols = (['id', 'name', 'unit', 'default_qty', 'role'] + FLAGS + ['note']
                + NUTRIENTS + SHOP + PREP + MADE + GATE + SRC + ['sort'])
        ph = ','.join('?' * len(cols))
        upd = ', '.join(f'{k}=excluded.{k}' for k in cols if k != 'id')
        sql = (f'INSERT INTO ingredients ({",".join(cols)}) VALUES ({ph}) '
               f'ON CONFLICT(id) DO UPDATE SET {upd}')
        for i, r in enumerate(ing):
            c.execute(sql, [
                r['id'], r['name'], r.get('unit', ''), _num(r.get('default'), 1), r.get('role', ''),
                *[int(_num(r.get(k))) for k in FLAGS], r.get('note', '') or '',
                *[_num(r.get(k)) for k in NUTRIENTS],
                int(_num(r.get('shelf'), 30)), _num(r.get('pack'), 1), r.get('packname', '') or '',
                _num(r.get('lead'), 0), r.get('prep', '') or '',
                r.get('makes', '') or '', int(_num(r.get('keep'))),
                r.get('needform', '') or '', r.get('gated', '') or '',
                r.get('ifct_code', '') or '', _num(r.get('grams')),
                r.get('grams_src', '') or '', i])

        tcols = ['fname', 'nkey', 'name', 'unit', 'cadence', 'daily', 'meal', 'permeal', 'sort']
        tph = ','.join('?' * len(tcols))
        tupd = ', '.join(f'{k}=excluded.{k}' for k in tcols if k != 'fname')
        tsql = (f'INSERT INTO targets ({",".join(tcols)}) VALUES ({tph}) '
                f'ON CONFLICT(fname) DO UPDATE SET {tupd}')
        for i, r in enumerate(tgt):
            c.execute(tsql, [r['fname'], r['key'], r['name'], r.get('unit', ''), r.get('cadence', 'day'),
                             _num(r.get('daily')), _num(r.get('meal')),
                             int(_num(r.get('permeal'), 1)), i])

        for r in rec:
            c.execute(
                'INSERT INTO recipes (id,name,meals,core,opt,method,cuisine,effort,amounts,src,is_user) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,0) '
                'ON CONFLICT(id) DO UPDATE SET name=excluded.name, meals=excluded.meals, '
                'core=excluded.core, opt=excluded.opt, method=excluded.method, '
                'cuisine=excluded.cuisine, effort=excluded.effort, '
                'amounts=excluded.amounts, src=excluded.src '
                'WHERE recipes.is_user = 0',
                [r['id'], r['name'], r.get('meals', ''), r.get('core', ''),
                 r.get('opt', ''), r.get('method', ''),
                 r.get('cuisine', 'neutral') or 'neutral', int(_num(r.get('effort'), 15)),
                 r.get('amounts', '') or '', r.get('src', '') or ''])
    if verbose:
        print(f'imported: {len(ing)} ingredients, {len(tgt)} targets, {len(rec)} seed recipes -> {DB_PATH}')


def export_csv():
    """Write the DB back out to the CSVs (round-trips user recipes into recipes.csv)."""
    init_db()
    with db() as c:
        rec = c.execute('SELECT id,name,meals,core,opt,method,cuisine,effort FROM recipes '
                        'ORDER BY is_user, id').fetchall()
    path = os.path.join(DIR, 'recipes.csv')
    with open(path, encoding='utf-8') as f:
        header = [ln for ln in f if ln.lstrip().startswith('#')]
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.writelines(header)
        w = csv.writer(f)
        w.writerow(['id', 'name', 'meals', 'core', 'opt', 'method', 'cuisine', 'effort'])
        for r in rec:
            w.writerow([r['id'], r['name'], r['meals'], r['core'], r['opt'], r['method'],
                        r['cuisine'], r['effort']])
    print(f'exported {len(rec)} recipes -> {path}')


# ---------- reads ----------


# ---------- IFCT: the sourced reference layer ----------
# The full ICMR-NIN Indian Food Composition Tables 2017 live in the `ifct` table: 542 foods,
# 151 components (each with its published error term). Ingredient rows link to it by code.
# IFCT units are per 100 g, in GRAMS for everything except energy (kJ). The conversions below
# are the only place that should know that.

IFCT_MAP = {                       # our nutrient column -> (ifct key, multiplier from per-100g)
    'protein': ('protcnt', 1), 'carbs': ('choavldf', 1), 'fibre': ('fibtg', 1),
    'iron': ('fe', 1000), 'calcium': ('ca', 1000), 'vitc': ('vitc', 1000),
    'folate': ('folsum', 1e6), 'omega3': ('f18d3n3', 1), 'omega3_dha': ('f22d6n3', 1),
    'zinc': ('zn', 1000), 'magnesium': ('mg', 1000), 'potassium': ('k', 1000),
}


def ifct_search(q, limit=25):
    """Find IFCT foods by name, scientific name, local name or group."""
    init_db()
    with db() as c:
        rows = c.execute(
            'SELECT code, name, grup, enerc/4.184 kcal, protcnt, fe*1000 fe, ca*1000 ca, zn*1000 zn '
            'FROM ifct WHERE name LIKE ? OR scie LIKE ? OR lang LIKE ? OR grup LIKE ? '
            'ORDER BY name LIMIT ?',
            (f'%{q}%',) * 4 + (limit,)).fetchall()
    for r in rows:
        print(f"{r['code']:6s} {r['name'][:44]:46s} {r['kcal'] or 0:6.0f}kcal "
              f"p{r['protcnt'] or 0:5.1f} fe{r['fe'] or 0:5.2f} ca{r['ca'] or 0:5.0f} zn{r['zn'] or 0:5.2f}"
              f"  [{r['grup']}]")
    if not rows:
        print(f'no IFCT food matches {q!r}')
    return rows


def ifct_derive(write=False):
    """Regenerate nutrient columns for every ingredient that declares an ifct_code + grams.

    This is what makes "sourced" mechanically true rather than a claim in a comment: the
    numbers are a function of (code, grams) and can be rebuilt from the table at any time.
    Rows without an ifct_code are listed as UNSOURCED — they are estimates and should look it.
    """
    init_db()
    out, unsourced = [], []
    with db() as c:
        ing = c.execute('SELECT * FROM ingredients ORDER BY sort, id').fetchall()
        for r in ing:
            code, g = (r['ifct_code'] or '').strip(), r['grams'] or 0
            if not code or g <= 0:
                unsourced.append(r['id']); continue
            f = c.execute('SELECT * FROM ifct WHERE code=?', (code,)).fetchone()
            if not f:
                print(f'  !! {r["id"]}: ifct_code {code} not in table'); continue
            s = g / 100.0
            vals = {'kcal': (f['enerc'] or 0) / 4.184 * s}
            if not f['enerc'] and f['fatce']:        # oils/fats carry no energy in IFCT
                vals['kcal'] = 9 * f['fatce'] * s
            for col, (k, mul) in IFCT_MAP.items():
                vals[col] = (f[k] or 0) * mul * s
            # vitamin A as ug RAE: preformed retinol + carotene equivalents / 12
            vals['vita'] = ((f['retol'] or 0) * 1e6 + (f['cartbeq'] or 0) * 1e6 / 12) * s
            diffs = [(k, r[k], v) for k, v in vals.items()
                     if abs((r[k] or 0) - v) > max(0.05, abs(r[k] or 0) * 0.02)]
            out.append((r['id'], code, g, f['name'], diffs))
            if write:
                c.execute('UPDATE ingredients SET ' + ','.join(f'{k}=?' for k in vals) +
                          ' WHERE id=?', list(vals.values()) + [r['id']])
    for iid, code, g, nm, diffs in out:
        print(f'{iid:14s} {code} {g:6.1f}g  {nm[:34]:36s} ' +
              ('  '.join(f'{k} {a or 0:.4g}->{b:.4g}' for k, a, b in diffs) if diffs else '(matches)'))
    print(f'\n{len(out)} sourced from IFCT, {len(unsourced)} UNSOURCED: {" ".join(unsourced)}')
    if write:
        print('written to DB — run `export-ingredients` to push back into ingredients.csv')
    return out


def export_ingredients():
    """Write the ingredients table back to ingredients.csv, preserving the comment header."""
    init_db()
    path = os.path.join(DIR, 'ingredients.csv')
    src = open(path, encoding='utf-8').read().split('\n')
    head = [l for l in src if l.lstrip().startswith('#')]
    hdr = next(l for l in src if l.startswith('id,')).split(',')
    # significant figures per column: the file is meant to be read and hand-edited, and
    # "69.7897 kcal" is false precision on a table whose own error bars are ~5%.
    DP = {'kcal': 0, 'calcium': 0, 'folate': 0, 'vita': 0, 'magnesium': 0, 'potassium': 0,
          'protein': 1, 'carbs': 1, 'fibre': 1, 'vitc': 1, 'grams': 0,
          'iron': 2, 'zinc': 2, 'omega3': 2, 'omega3_dha': 2}
    def fmt(v, col=None):
        if v is None: return ''
        if isinstance(v, float):
            if col in DP: v = round(v, DP[col])
            return ('%.4f' % v).rstrip('0').rstrip('.') if v % 1 else str(int(v))
        return str(v)
    with db() as c:
        rows = c.execute('SELECT * FROM ingredients ORDER BY sort, id').fetchall()
    colmap = {'default': 'default_qty'}
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(head) + '\n' + ','.join(hdr) + '\n')
        for r in rows:
            f.write(','.join(fmt(r[colmap.get(k, k)], k) for k in hdr) + '\n')
    print(f'wrote {len(rows)} ingredients -> {path}')


def get_data():
    with db() as c:
        ing = [{
            'id': r['id'], 'name': r['name'], 'unit': r['unit'], 'default': r['default_qty'],
            'role': r['role'], 'note': r['note'] or '',
            'shelf': r['shelf'] or 30, 'pack': r['pack'] or 1, 'packname': r['packname'] or '',
            'lead': r['lead'] or 0, 'prep': r['prep'] or '',
            'makes': r['makes'] or '', 'keep': bool(r['keep']),
            'needform': r['needform'] or '', 'gated': (r['gated'] or '').split(),
            'ifct_code': r['ifct_code'] or '', 'grams': r['grams'] or 0,
            'grams_src': r['grams_src'] or '',
            **{k: bool(r[k]) for k in FLAGS},
            **{k: r[k] for k in NUTRIENTS},
        } for r in c.execute('SELECT * FROM ingredients ORDER BY sort, id')]
        tgt = [{
            'fname': r['fname'], 'key': r['nkey'], 'name': r['name'], 'unit': r['unit'],
            'cadence': r['cadence'], 'daily': r['daily'], 'meal': r['meal'],
            'permeal': bool(r['permeal']),
        } for r in c.execute('SELECT * FROM targets ORDER BY sort, fname')]
        rec = [{
            'id': r['id'], 'name': r['name'],
            'meals': (r['meals'] or '').split(), 'core': (r['core'] or '').split(),
            'opt': (r['opt'] or '').split(), 'method': r['method'] or '',
            'cuisine': r['cuisine'] or '', 'effort': r['effort'] or 0,   # 0/'' = unknown, UI hides it
            # amounts = 'id:grams ...' per SERVING, from INDB. src = provenance ('INDB:ASC152').
            'amounts': dict((lambda a: (a[0], float(a[1])))(x.split(':'))
                            for x in (r['amounts'] or '').split() if ':' in x),
            'src': r['src'] or '',
            'user': bool(r['is_user']),
        } for r in c.execute('SELECT * FROM recipes ORDER BY is_user, id')]
    return {'ingredients': ing, 'targets': tgt, 'recipes': rec}


def get_plates(planned=0):
    """planned=0 -> what you ate (history). planned=1 -> the menu (what you intend to eat)."""
    with db() as c:
        items = {}
        for r in c.execute('SELECT * FROM plate_items'):
            items.setdefault(r['plate_id'], []).append({'id': r['ing_id'], 'qty': r['qty']})
        return [{'id': r['id'], 'date': r['date'], 'meal': r['meal'],
                 'recipe': r['recipe_id'] or '', 'items': items.get(r['id'], [])}
                for r in c.execute('SELECT * FROM plates WHERE planned = ? ORDER BY date, created_at',
                                   [planned])]


def get_stock():
    with db() as c:
        return {r['ing_id']: {'qty': r['qty'], 'bought': r['bought_at'] or r['updated_at'] or ''}
                for r in c.execute('SELECT * FROM stock')}


def get_pins():
    with db() as c:
        return {r['recipe_id']: r['perweek'] for r in c.execute('SELECT * FROM pins')}


# ---------- writes ----------

def _sid(prefix):
    return f'{prefix}{int(time.time() * 1000)}'


def _now():
    return time.strftime('%Y-%m-%dT%H:%M:%S')


def _bump(c, iid, delta):
    """Move one ingredient's stock by delta, floored at 0.

    Floored, not signed: cooking something the DB thought you didn't have means the
    count was wrong, not that you owe a negative cup of dal. Letting it go negative
    would silently inflate the next buy list.
    """
    now = _now()
    c.execute('INSERT INTO stock (ing_id,qty,updated_at,bought_at) VALUES (?,?,?,?) '
              'ON CONFLICT(ing_id) DO UPDATE SET qty=max(0, stock.qty + ?), updated_at=?, '
              "  bought_at=CASE WHEN ? > 0 THEN ? ELSE stock.bought_at END",
              [iid, max(0.0, delta), now, now, delta, now, delta, now])


def _bump_items(c, items, sign):
    for it in items:
        _bump(c, it['id'], sign * _num(it.get('qty'), 1))


def _plate_items(c, pid):
    return [{'id': r['ing_id'], 'qty': r['qty']}
            for r in c.execute('SELECT * FROM plate_items WHERE plate_id = ?', [pid])]


def save_plate(d, conn=None, stock=True, planned=0):
    """Save a plate (planned=0, eaten) or a menu slot (planned=1, intended).

    Only eaten plates move stock — a menu is a plan, not a consumption. Overwriting an
    existing eaten plate returns the old items to stock first, so a re-save is not a
    double-consume.
    """
    pid = str(d.get('id') or _sid('m' if planned else 'p'))
    own = conn is None
    c = conn or db()
    move = stock and not planned
    try:
        if move:
            _bump_items(c, _plate_items(c, pid), +1)     # undo the previous version, if any
        c.execute('INSERT OR REPLACE INTO plates (id,date,meal,created_at,planned,recipe_id) '
                  'VALUES (?,?,?,?,?,?)',
                  [pid, d['date'], d['meal'], d.get('created_at') or _now(),
                   planned, d.get('recipe', '')])
        c.execute('DELETE FROM plate_items WHERE plate_id = ?', [pid])
        items = d.get('items', [])
        for it in items:
            c.execute('INSERT INTO plate_items (plate_id,ing_id,qty) VALUES (?,?,?)',
                      [pid, it['id'], _num(it.get('qty'), 1)])
        if move:
            _bump_items(c, items, -1)                    # eating it takes it out of the kitchen
        if own:
            c.commit()
    finally:
        if own:
            c.close()
    return pid


def del_plate(pid):
    with db() as c:
        r = c.execute('SELECT planned FROM plates WHERE id = ?', [pid]).fetchone()
        if r and not r['planned']:
            _bump_items(c, _plate_items(c, pid), +1)     # un-eaten — put it back
        c.execute('DELETE FROM plate_items WHERE plate_id = ?', [pid])
        c.execute('DELETE FROM plates WHERE id = ?', [pid])


def cook_slot(mid):
    """Menu slot -> you actually cooked it. Flips planned 1->0 and consumes the stock."""
    with db() as c:
        r = c.execute('SELECT * FROM plates WHERE id = ? AND planned = 1', [mid]).fetchone()
        if not r:
            return {'ok': False, 'error': 'no such menu slot'}
        _bump_items(c, _plate_items(c, mid), -1)
        c.execute('UPDATE plates SET planned = 0 WHERE id = ?', [mid])
    return {'ok': True, 'id': mid}


def save_menu(slots):
    """Replace the menu over the date range the slots span. One write for a whole week."""
    if not slots:
        return {'saved': 0}
    lo = min(s['date'] for s in slots)
    hi = max(s['date'] for s in slots)
    with db() as c:
        old = [r['id'] for r in c.execute(
            'SELECT id FROM plates WHERE planned = 1 AND date BETWEEN ? AND ?', [lo, hi])]
        for pid in old:                                  # planned rows never touched stock
            c.execute('DELETE FROM plate_items WHERE plate_id = ?', [pid])
            c.execute('DELETE FROM plates WHERE id = ?', [pid])
        for i, s in enumerate(slots):
            s = {**s, 'id': s.get('id') or f'm{int(time.time() * 1000)}_{i}'}
            save_plate(s, conn=c, planned=1)
        c.commit()
    return {'saved': len(slots), 'from': lo, 'to': hi}


def clear_menu(lo, hi):
    with db() as c:
        for r in c.execute('SELECT id FROM plates WHERE planned = 1 AND date BETWEEN ? AND ?',
                           [lo, hi]).fetchall():
            c.execute('DELETE FROM plate_items WHERE plate_id = ?', [r['id']])
            c.execute('DELETE FROM plates WHERE id = ?', [r['id']])
    return {'ok': True}


def set_stock(iid, qty, bought=None):
    """Correct a count. Does NOT restart the freshness clock unless we've never had one —
    editing 'spinach: 4 -> 2 cups' is you telling us what's left, not that you just shopped."""
    now = _now()
    with db() as c:
        c.execute('INSERT INTO stock (ing_id,qty,updated_at,bought_at) VALUES (?,?,?,?) '
                  'ON CONFLICT(ing_id) DO UPDATE SET qty=excluded.qty, updated_at=excluded.updated_at, '
                  "  bought_at=COALESCE(NULLIF(?, ''), NULLIF(stock.bought_at, ''), ?)",
                  [iid, max(0.0, _num(qty)), now, bought or now, bought or '', now])
    return get_stock()


def add_stock(iid, delta):
    with db() as c:
        _bump(c, iid, _num(delta))
    return get_stock()


def seed_stock():
    """Bootstrap: assume one full pack of everything flagged pantry=1, for rows not yet counted."""
    with db() as c:
        rows = c.execute('SELECT id, pack FROM ingredients WHERE pantry = 1').fetchall()
        for r in rows:
            c.execute('INSERT INTO stock (ing_id,qty,updated_at,bought_at) VALUES (?,?,?,?) '
                      'ON CONFLICT(ing_id) DO NOTHING',
                      [r['id'], r['pack'] or 1, _now(), _now()])
    return get_stock()


def set_pin(rid, perweek):
    with db() as c:
        if _num(perweek) <= 0:
            c.execute('DELETE FROM pins WHERE recipe_id = ?', [rid])
        else:
            c.execute('INSERT INTO pins (recipe_id,perweek) VALUES (?,?) '
                      'ON CONFLICT(recipe_id) DO UPDATE SET perweek=excluded.perweek',
                      [rid, _num(perweek)])
    return get_pins()


def save_recipe(d, conn=None):
    rid = str(d.get('id') or _sid('u'))
    j = lambda v: ' '.join(str(x).strip() for x in (v or []) if str(x).strip())
    own = conn is None
    c = conn or db()
    try:
        # cuisine/effort are unknown for a recipe you built by hand — store them empty rather than
        # defaulting to a guess. The UI hides what it doesn't know instead of printing "15m · neutral".
        c.execute('INSERT OR REPLACE INTO recipes (id,name,meals,core,opt,method,cuisine,effort,is_user) '
                  'VALUES (?,?,?,?,?,?,?,?,1)',
                  [rid, d.get('name') or 'Recipe', j(d.get('meals')), j(d.get('core')),
                   j(d.get('opt')), d.get('method') or 'Your saved recipe',
                   d.get('cuisine', '') or '', int(_num(d.get('effort'), 0))])
        if own:
            c.commit()
    finally:
        if own:
            c.close()
    return rid


def del_recipe(rid):
    with db() as c:                       # seed recipes are protected
        c.execute('DELETE FROM recipes WHERE id = ? AND is_user = 1', [rid])


def import_local(d):
    """One-time migration of a browser's localStorage into the DB. Idempotent by id."""
    with db() as c:
        for p in d.get('plates', []):
            if p.get('date') and p.get('meal'):
                save_plate(p, conn=c, stock=False)   # history — already eaten, don't consume stock
        for r in d.get('recipes', []):
            save_recipe(r, conn=c)
        c.commit()
    return {'plates': len(d.get('plates', [])), 'recipes': len(d.get('recipes', []))}


# ---------- http ----------

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=DIR, **k)

    def log_message(self, fmt, *a):
        if os.environ.get('MEALS_QUIET') != '1':
            super().log_message(fmt, *a)

    def end_headers(self):
        if self.path.startswith('/api/'):
            self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def _json(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _body(self):
        n = int(self.headers.get('Content-Length', 0) or 0)
        return json.loads(self.rfile.read(n) or b'{}')

    def do_GET(self):
        try:
            if self.path.startswith('/api/data'):
                return self._json(200, get_data())
            if self.path.startswith('/api/plates'):
                return self._json(200, get_plates(0))
            if self.path.startswith('/api/menu'):
                return self._json(200, get_plates(1))
            if self.path.startswith('/api/stock'):
                return self._json(200, get_stock())
            if self.path.startswith('/api/pins'):
                return self._json(200, get_pins())
            if self.path.startswith('/api/health'):
                return self._json(200, {'status': 'ok', 'db': DB_PATH})
            if self.path.startswith('/api/'):
                return self._json(404, {'error': 'not found'})
            return super().do_GET()
        except Exception as e:                       # noqa: BLE001 — surface to the client
            return self._json(500, {'error': str(e)})

    def do_POST(self):
        try:
            p, d = self.path.rstrip('/'), self._body()
            if p == '/api/plates':
                return self._json(200, {'ok': True, 'id': save_plate(d)})
            if p == '/api/plates/delete':
                del_plate(str(d.get('id', '')))
                return self._json(200, {'ok': True})
            if p == '/api/recipes':
                return self._json(200, {'ok': True, 'id': save_recipe(d)})
            if p == '/api/recipes/delete':
                del_recipe(str(d.get('id', '')))
                return self._json(200, {'ok': True})
            if p == '/api/import':
                return self._json(200, {'ok': True, **import_local(d)})
            if p == '/api/stock':
                return self._json(200, set_stock(str(d.get('id', '')), d.get('qty'), d.get('bought')))
            if p == '/api/stock/add':
                return self._json(200, add_stock(str(d.get('id', '')), d.get('delta')))
            if p == '/api/stock/seed':
                return self._json(200, seed_stock())
            if p == '/api/pins':
                return self._json(200, set_pin(str(d.get('id', '')), d.get('perweek')))
            if p == '/api/menu':
                return self._json(200, {'ok': True, **save_menu(d.get('slots', []))})
            if p == '/api/menu/slot':
                return self._json(200, {'ok': True, 'id': save_plate(d, planned=1)})
            if p == '/api/menu/cook':
                return self._json(200, cook_slot(str(d.get('id', ''))))
            if p == '/api/menu/clear':
                return self._json(200, clear_menu(str(d.get('from', '')), str(d.get('to', ''))))
            return self._json(404, {'error': 'not found'})
        except Exception as e:                       # noqa: BLE001
            return self._json(500, {'error': str(e)})


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def serve():
    init_db()
    with db() as c:
        n = c.execute('SELECT count(*) FROM ingredients').fetchone()[0]
    if not n:
        print('empty db — seeding from CSVs')
        import_csv()
    with Server((HOST, PORT), Handler) as httpd:
        print(f'meal planner on http://{HOST}:{PORT}  (db: {DB_PATH})')
        httpd.serve_forever()


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'serve'
    if cmd == 'serve':
        serve()
    elif cmd == 'ifct':
        ifct_search(' '.join(sys.argv[2:]) or '')
    elif cmd == 'ifct-derive':
        ifct_derive(write='--write' in sys.argv)
    elif cmd == 'export-ingredients':
        export_ingredients()
    elif cmd == 'import-csv':
        import_csv()
    elif cmd == 'export-csv':
        export_csv()
    else:
        print(__doc__)
        sys.exit(1)
