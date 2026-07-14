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
  POST /api/plates          -> save a plate     {date, meal, items}
  POST /api/plates/delete   -> {id}
  POST /api/recipes         -> save a recipe    {name, meals[], core[], opt[], method}
  POST /api/recipes/delete  -> {id}   (user recipes only)
  POST /api/import          -> one-time localStorage migration {plates[], recipes[]}
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

# ingredient nutrient columns, in CSV order
NUTRIENTS = ['kcal', 'protein', 'carbs', 'fibre', 'iron', 'calcium',
             'vitc', 'folate', 'omega3', 'zinc', 'vita']
FLAGS = ['pantry', 'base', 'green', 'probiotic']

SCHEMA = """
CREATE TABLE IF NOT EXISTS ingredients(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, unit TEXT, default_qty REAL DEFAULT 1,
  role TEXT, pantry INT DEFAULT 0, base INT DEFAULT 0, green INT DEFAULT 0,
  probiotic INT DEFAULT 0, note TEXT DEFAULT '',
  kcal REAL DEFAULT 0, protein REAL DEFAULT 0, carbs REAL DEFAULT 0, fibre REAL DEFAULT 0,
  iron REAL DEFAULT 0, calcium REAL DEFAULT 0, vitc REAL DEFAULT 0, folate REAL DEFAULT 0,
  omega3 REAL DEFAULT 0, zinc REAL DEFAULT 0, vita REAL DEFAULT 0,
  sort INT DEFAULT 0
);
CREATE TABLE IF NOT EXISTS targets(
  fname TEXT PRIMARY KEY, nkey TEXT NOT NULL, name TEXT, unit TEXT, cadence TEXT,
  daily REAL DEFAULT 0, meal REAL DEFAULT 0, permeal INT DEFAULT 1, sort INT DEFAULT 0
);
CREATE TABLE IF NOT EXISTS recipes(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, meals TEXT DEFAULT '', core TEXT DEFAULT '',
  opt TEXT DEFAULT '', method TEXT DEFAULT '', is_user INT DEFAULT 0
);
CREATE TABLE IF NOT EXISTS plates(
  id TEXT PRIMARY KEY, date TEXT NOT NULL, meal TEXT NOT NULL, created_at TEXT
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


def init_db():
    with db() as c:
        c.executescript(SCHEMA)


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
        cols = ['id', 'name', 'unit', 'default_qty', 'role'] + FLAGS + ['note'] + NUTRIENTS + ['sort']
        ph = ','.join('?' * len(cols))
        upd = ', '.join(f'{k}=excluded.{k}' for k in cols if k != 'id')
        sql = (f'INSERT INTO ingredients ({",".join(cols)}) VALUES ({ph}) '
               f'ON CONFLICT(id) DO UPDATE SET {upd}')
        for i, r in enumerate(ing):
            c.execute(sql, [
                r['id'], r['name'], r.get('unit', ''), _num(r.get('default'), 1), r.get('role', ''),
                *[int(_num(r.get(k))) for k in FLAGS], r.get('note', '') or '',
                *[_num(r.get(k)) for k in NUTRIENTS], i])

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
                'INSERT INTO recipes (id,name,meals,core,opt,method,is_user) VALUES (?,?,?,?,?,?,0) '
                'ON CONFLICT(id) DO UPDATE SET name=excluded.name, meals=excluded.meals, '
                'core=excluded.core, opt=excluded.opt, method=excluded.method '
                'WHERE recipes.is_user = 0',
                [r['id'], r['name'], r.get('meals', ''), r.get('core', ''),
                 r.get('opt', ''), r.get('method', '')])
    if verbose:
        print(f'imported: {len(ing)} ingredients, {len(tgt)} targets, {len(rec)} seed recipes -> {DB_PATH}')


def export_csv():
    """Write the DB back out to the CSVs (round-trips user recipes into recipes.csv)."""
    init_db()
    with db() as c:
        rec = c.execute('SELECT id,name,meals,core,opt,method FROM recipes ORDER BY is_user, id').fetchall()
    path = os.path.join(DIR, 'recipes.csv')
    with open(path, encoding='utf-8') as f:
        header = [ln for ln in f if ln.lstrip().startswith('#')]
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.writelines(header)
        w = csv.writer(f)
        w.writerow(['id', 'name', 'meals', 'core', 'opt', 'method'])
        for r in rec:
            w.writerow([r['id'], r['name'], r['meals'], r['core'], r['opt'], r['method']])
    print(f'exported {len(rec)} recipes -> {path}')


# ---------- reads ----------

def get_data():
    with db() as c:
        ing = [{
            'id': r['id'], 'name': r['name'], 'unit': r['unit'], 'default': r['default_qty'],
            'role': r['role'], 'note': r['note'] or '',
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
            'user': bool(r['is_user']),
        } for r in c.execute('SELECT * FROM recipes ORDER BY is_user, id')]
    return {'ingredients': ing, 'targets': tgt, 'recipes': rec}


def get_plates():
    with db() as c:
        items = {}
        for r in c.execute('SELECT * FROM plate_items'):
            items.setdefault(r['plate_id'], []).append({'id': r['ing_id'], 'qty': r['qty']})
        return [{'id': r['id'], 'date': r['date'], 'meal': r['meal'],
                 'items': items.get(r['id'], [])}
                for r in c.execute('SELECT * FROM plates ORDER BY date, created_at')]


# ---------- writes ----------

def _sid(prefix):
    return f'{prefix}{int(time.time() * 1000)}'


def save_plate(d, conn=None):
    pid = str(d.get('id') or _sid('p'))
    own = conn is None
    c = conn or db()
    try:
        c.execute('INSERT OR REPLACE INTO plates (id,date,meal,created_at) VALUES (?,?,?,?)',
                  [pid, d['date'], d['meal'], d.get('created_at') or time.strftime('%Y-%m-%dT%H:%M:%S')])
        c.execute('DELETE FROM plate_items WHERE plate_id = ?', [pid])
        for it in d.get('items', []):
            c.execute('INSERT INTO plate_items (plate_id,ing_id,qty) VALUES (?,?,?)',
                      [pid, it['id'], _num(it.get('qty'), 1)])
        if own:
            c.commit()
    finally:
        if own:
            c.close()
    return pid


def del_plate(pid):
    with db() as c:
        c.execute('DELETE FROM plate_items WHERE plate_id = ?', [pid])
        c.execute('DELETE FROM plates WHERE id = ?', [pid])


def save_recipe(d, conn=None):
    rid = str(d.get('id') or _sid('u'))
    j = lambda v: ' '.join(str(x).strip() for x in (v or []) if str(x).strip())
    own = conn is None
    c = conn or db()
    try:
        c.execute('INSERT OR REPLACE INTO recipes (id,name,meals,core,opt,method,is_user) '
                  'VALUES (?,?,?,?,?,?,1)',
                  [rid, d.get('name') or 'Recipe', j(d.get('meals')), j(d.get('core')),
                   j(d.get('opt')), d.get('method') or 'Your saved recipe'])
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
                save_plate(p, conn=c)
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
                return self._json(200, get_plates())
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
    elif cmd == 'import-csv':
        import_csv()
    elif cmd == 'export-csv':
        export_csv()
    else:
        print(__doc__)
        sys.exit(1)
