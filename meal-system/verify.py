#!/usr/bin/env python3
"""Data integrity checks across every CSV + the DB. Run: python3 verify.py

Not a test of the planner's logic — a test of whether the DATA it reads is coherent.
Exists because most of what has gone wrong here was a data-shape problem (ragged columns,
long-vs-short nutrient keys, ids pointing at nothing), not a code problem.
"""
import csv, os, sys, sqlite3, io

DIR = os.path.dirname(os.path.abspath(__file__))
ERR, WARN = [], []
def err(f, m):  ERR.append(f'{f}: {m}')
def warn(f, m): WARN.append(f'{f}: {m}')

def rows(fn):
    """Read a CSV the way app.py does: '#' lines are comments, not data."""
    p = os.path.join(DIR, fn)
    if not os.path.exists(p): return None, []
    raw = [l for l in open(p, encoding='utf-8').read().split('\n')
           if l.strip() and not l.lstrip().startswith('#')]
    if not raw: return None, []
    r = list(csv.reader(io.StringIO('\n'.join(raw))))
    return r[0], r[1:]


# ---------- ingredients ----------
ihdr, irows = rows('ingredients.csv')
ING = {}
for n, r in enumerate(irows, 1):
    if len(r) != len(ihdr):
        err('ingredients.csv', f'row {n} ({r[0] if r else "?"}) has {len(r)} cols, header has {len(ihdr)}')
        continue
    d = dict(zip(ihdr, r))
    if d['id'] in ING: err('ingredients.csv', f'duplicate id {d["id"]}')
    ING[d['id']] = d

NUM = ['kcal','protein','carbs','fibre','iron','calcium','vitc','folate',
       'omega3','omega3_dha','zinc','vita','magnesium','potassium','shelf','pack','lead','default']
for i, d in ING.items():
    for k in NUM:
        v = d.get(k, '')
        if v == '': continue
        try:
            x = float(v)
            if x < 0: err('ingredients.csv', f'{i}.{k} is negative ({v})')
        except ValueError:
            err('ingredients.csv', f'{i}.{k} is not a number: {v!r}')
    for k in ['pantry','base','green','probiotic','topper','keep']:
        if d.get(k, '0') not in ('0','1',''):   # '' is a legal 0 — app.py's _num() coerces it
            err('ingredients.csv', f'{i}.{k} must be 0/1, got {d.get(k)!r}')
    if not d.get('unit'):   err('ingredients.csv', f'{i} has no unit')
    if not d.get('role'):   warn('ingredients.csv', f'{i} has no role')

# kcal must agree with the macros: 4/4/9. The single strongest automatic sanity check —
# it catches a unit-scaling slip that no amount of eyeballing would.
for i, d in ING.items():
    try:
        kcal, p, c = float(d['kcal']), float(d['protein']), float(d['carbs'])
    except (ValueError, KeyError):
        continue
    if kcal <= 0: continue
    frommacros = 4*p + 4*c                       # fat is not a tracked column
    # absolute floor as well as a ratio: on a 4 kcal clove of garlic, 1 kcal of rounding is 25%
    if frommacros > kcal * 1.12 and frommacros - kcal > 3:
        err('ingredients.csv', f'{i}: protein+carbs imply {frommacros:.0f} kcal but kcal={kcal:.0f} '
                               f'— impossible, a value is mis-scaled')
    elif kcal > 60 and frommacros < kcal * 0.25 and d.get('role') not in ('seed','condiment'):
        warn('ingredients.csv', f'{i}: kcal={kcal:.0f} but protein+carbs only explain '
                                f'{frommacros:.0f} — unexplained unless it is mostly fat')

# makes / prep-output integrity
for i, d in ING.items():
    for src in (d.get('makes') or '').split():
        if src not in ING: err('ingredients.csv', f'{i}.makes points at unknown id {src!r}')
    if d.get('keep') == '1' and not d.get('makes'):
        warn('ingredients.csv', f'{i} has keep=1 but no makes — keep is for prep outputs')

# ---------- targets ----------
thdr, trows = rows('targets.csv')
TGT = {r[thdr.index('fname')]: dict(zip(thdr, r)) for r in trows if len(r) == len(thdr)}
NKEY = {'kcal':'kcal','protein':'p','carbs':'c','fibre':'fib','iron':'fe','calcium':'ca','vitc':'vc',
        'folate':'fo','omega3':'o3','omega3_dha':'o3d','zinc':'zn','vita':'va','magnesium':'mg',
        'potassium':'k'}
for fn, d in TGT.items():
    if fn not in NKEY and fn != 'omega3dha':
        warn('targets.csv', f'fname {fn!r} has no column in ingredients.csv')
    if d['cadence'] not in ('meal','day','week'):
        err('targets.csv', f'{fn} cadence {d["cadence"]!r} not meal/day/week')

# ---------- the gate layer ----------
fhdr, frows_ = rows('forms.csv')
FORMS = {r[0]: dict(zip(fhdr, r)) for r in frows_ if len(r) == len(fhdr)}
for r in frows_:
    if len(r) != len(fhdr):
        err('forms.csv', f'row {r[0] if r else "?"} has {len(r)} cols, header has {len(fhdr)}')
VALID_NUTS = set(NKEY) | set(NKEY.values())
for i, d in ING.items():
    nf, g = d.get('needform',''), (d.get('gated','') or '').split()
    if nf and nf not in FORMS: err('ingredients.csv', f'{i}.needform {nf!r} is not a forms.csv id')
    if g and not nf:           err('ingredients.csv', f'{i} lists gated={g} but no needform')
    if nf and not g:           warn('ingredients.csv', f'{i} has needform={nf} but gates nothing')
    for k in g:
        if k not in VALID_NUTS: err('ingredients.csv', f'{i}.gated has unknown nutrient {k!r}')
    # a gate with no ungated alternative makes the nutrient unreachable
    for k in g:
        alt = [j for j, e in ING.items()
               if j != i and float(e.get(k) or 0) > 0 and k not in (e.get('gated','') or '').split()]
        if not alt: err('ingredients.csv', f'{i} gates {k} and NOTHING else supplies it — unreachable')
for fid, d in FORMS.items():
    if d.get('mechanism') not in ('phytate','heat','matrix','fat'):
        err('forms.csv', f'{fid} mechanism {d.get("mechanism")!r} unknown')
    pr = d.get('phyt_red','')
    if pr and d['mechanism'] != 'phytate':
        err('forms.csv', f'{fid} has phyt_red but mechanism={d["mechanism"]} — only phytate scales')
    if pr:
        try:
            if not 0 <= float(pr) <= 100: err('forms.csv', f'{fid} phyt_red {pr} out of 0-100')
        except ValueError: err('forms.csv', f'{fid} phyt_red not numeric: {pr!r}')
    for k in (d.get('gates','') or '').split():
        if k not in VALID_NUTS: err('forms.csv', f'{fid}.gates unknown nutrient {k!r}')

# ---------- phytate ----------
phdr, prows = rows('phytate.csv')
for r in prows:
    if len(r) != len(phdr): err('phytate.csv', f'row {r[0] if r else "?"} ragged'); continue
    d = dict(zip(phdr, r))
    if d['id'] not in ING: err('phytate.csv', f'id {d["id"]!r} is not an ingredient')
    for k in ['phytate','iron','zinc','phy_fe','phy_zn']:
        if d.get(k):
            try: float(d[k])
            except ValueError: err('phytate.csv', f'{d["id"]}.{k} not numeric: {d[k]!r}')
    # the ratios must reproduce from the raw numbers
    try:
        p, fe, zn = float(d['phytate']), float(d['iron']), float(d['zinc'])
        for mineral, aw, col in (('iron',55.85,'phy_fe'), ('zinc',65.38,'phy_zn')):
            m = fe if mineral=='iron' else zn
            if m > 0 and d.get(col):
                calc = (p/660.04)/(m/aw)
                if abs(calc - float(d[col])) > 0.05:
                    err('phytate.csv', f'{d["id"]}.{col}={d[col]} but recomputes to {calc:.2f}')
    except (ValueError, KeyError, ZeroDivisionError): pass
    # phytate.csv iron/zinc should match ingredients.csv for the same row
    g = ING.get(d['id'])
    if g:
        for col in ('iron','zinc'):
            try:
                a, b = float(d[col]), float(g[col])
                if a > 0 and b > 0 and abs(a-b)/max(a,b) > 0.35:
                    warn('phytate.csv', f'{d["id"]}.{col}={a} vs ingredients.csv {b} — different source rows?')
            except (ValueError, KeyError): pass

# ---------- retention ----------
rhdr, rrows = rows('retention.csv')
for r in rrows:
    if len(r) != len(rhdr): err('retention.csv', f'row {r[0] if r else "?"} ragged'); continue
    for k, v in list(zip(rhdr, r))[1:]:
        if v == '': continue
        try:
            if not 0 <= float(v) <= 100: err('retention.csv', f'{r[0]}.{k}={v} out of 0-100')
        except ValueError: err('retention.csv', f'{r[0]}.{k} not numeric: {v!r}')

# ---------- recipes ----------
chdr, crows = rows('recipes.csv')
SEEN = set()
for r in crows:
    if len(r) != len(chdr): err('recipes.csv', f'row {r[0] if r else "?"} has {len(r)} cols'); continue
    d = dict(zip(chdr, r))
    if d['id'] in SEEN: err('recipes.csv', f'duplicate id {d["id"]}')
    SEEN.add(d['id'])
    ids = (d['core']+' '+d['opt']).split()
    for x in ids:
        if x not in ING: err('recipes.csv', f'{d["id"]} references unknown ingredient {x!r}')
    if not d['core'].split(): err('recipes.csv', f'{d["id"]} has no core ingredients')
    for m in d['meals'].split():
        if m not in ('breakfast','lunch','dinner','snack'):
            err('recipes.csv', f'{d["id"]} unknown meal {m!r}')
    # blank effort is legitimate: the file's own header says 0/'' = unknown and the UI hides it.
    # An INDB dish with no time match should read unknown, not be coerced to a made-up number.
    if d['effort'].strip():
        try:
            if not 0 <= int(d['effort']) <= 120: warn('recipes.csv', f'{d["id"]} effort={d["effort"]}')
        except ValueError: err('recipes.csv', f'{d["id"]} effort not an int: {d["effort"]!r}')
    dup = [x for x in set(d['core'].split()) if x in d['opt'].split()]
    if dup: warn('recipes.csv', f'{d["id"]} lists {dup} in BOTH core and opt')

# ---------- DB agreement ----------
try:
    c = sqlite3.connect(os.path.join(DIR, 'data', 'meals.db')); c.row_factory = sqlite3.Row
    dbi = {r['id']: r for r in c.execute('SELECT * FROM ingredients')}
    if len(dbi) != len(ING):
        err('db', f'{len(dbi)} ingredients in DB vs {len(ING)} in CSV — re-run import-csv')
    for i, d in ING.items():
        if i not in dbi: err('db', f'{i} in CSV but not DB'); continue
        for col, cast in (('iron',float), ('calcium',float), ('zinc',float)):
            if abs(cast(d[col] or 0) - (dbi[i][col] or 0)) > 0.001:
                err('db', f'{i}.{col} CSV={d[col]} DB={dbi[i][col]} — stale import')
        if (dbi[i]['needform'] or '') != (d.get('needform') or ''):
            err('db', f'{i}.needform CSV={d.get("needform")!r} DB={dbi[i]["needform"]!r}')
    nrec = c.execute('SELECT COUNT(*) n FROM recipes WHERE is_user=0').fetchone()['n']
    if nrec != len(SEEN): warn('db', f'{nrec} seed recipes in DB vs {len(SEEN)} in CSV')
    c.close()
except Exception as e:
    err('db', f'could not check: {e}')

# ---------- report ----------
print(f'ingredients {len(ING)} · recipes {len(SEEN)} · forms {len(FORMS)} · '
      f'phytate {len(prows)} · retention {len(rrows)} · targets {len(TGT)}')
for e in ERR:  print('  ERROR  ' + e)
for w in WARN: print('  warn   ' + w)
print(f'\n{len(ERR)} errors, {len(WARN)} warnings')
sys.exit(1 if ERR else 0)
