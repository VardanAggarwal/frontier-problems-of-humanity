#!/usr/bin/env python3
"""Build a day of plates and check the numbers against targets.

Reproduces the planner's own arithmetic (delivered() incl. gates, qty x grams, per-slot budgets)
outside the browser, so a bad number shows up as a failing assertion rather than as a plate that
looks slightly off. Run: python3 test_day.py
"""
import sqlite3, sys, os

DIR = os.path.dirname(os.path.abspath(__file__))
c = sqlite3.connect(os.path.join(DIR, 'data', 'meals.db')); c.row_factory = sqlite3.Row

NKEY = {'kcal':'kcal','protein':'p','carbs':'c','fibre':'fib','iron':'fe','calcium':'ca',
        'vitc':'vc','folate':'fo','omega3':'o3','omega3_dha':'o3d','zinc':'zn','vita':'va',
        'magnesium':'mg','potassium':'k'}
ING = {r['id']: r for r in c.execute('SELECT * FROM ingredients')}
TGT = {r['nkey']: r for r in c.execute('SELECT * FROM targets')}
KCAL_SLOT = {'breakfast':475, 'lunch':625, 'snack':100, 'dinner':575}
MEAL_P    = {'breakfast':30, 'lunch':32, 'snack':8, 'dinner':30}

def delivered(i, col):
    """Same seam as index.html: a gated nutrient reads 0 until its form is applied."""
    gated = (i['gated'] or '').split()
    if i['needform'] and (col in gated or NKEY.get(col) in gated):
        return 0.0
    return i[col] or 0.0

def total(items, col):
    return sum(delivered(ING[iid], col) * q for iid, q in items)

# A day built the way you'd actually eat it. qty is in SERVINGS (unit=serving, 0.5 steps).
DAY = {
 'breakfast': [('egg',3),('poha',0.5),('onion',1),('curd',0.5),('lemon',0.5),('gchilli',1)],
 'lunch':     [('rice',0.5),('dal',1),('soya',1),('spinach',1),('tomato',1),('onion',1),
               ('lemon',0.5),('ghee',0.5)],
 'snack':     [('curd',0.5),('flax',0.5)],
 'dinner':    [('atta',0.5),('rajma',1),('paneer',0.5),('methi',1),('tomato',1),('onion',1),
               ('lemon',0.5),('pumpkin',1)],
}

fails, warns = [], []
print('=' * 74)
for slot, items in DAY.items():
    kc, p = total(items,'kcal'), total(items,'protein')
    bud, pt = KCAL_SLOT[slot], MEAL_P[slot]
    flag = '' if kc <= bud*1.15 else '   OVER BUDGET'
    if kc > bud*1.15: fails.append(f'{slot}: {kc:.0f} kcal vs {bud} budget')
    print(f'{slot.upper():10s} {kc:5.0f}/{bud} kcal   {p:5.1f}/{pt} g protein{flag}')
    for iid, q in items:
        i = ING[iid]
        g = (i['grams'] or 0) * q
        gate = f"  [{i['gated']} needs {i['needform']}]" if i['needform'] else ''
        print(f'    {q:>4g} x {i["name"][:26]:28s} {g:5.0f} g  {delivered(i,"kcal")*q:5.0f} kcal '
              f'{delivered(i,"protein")*q:5.1f} P{gate}')
    if p < pt * 0.80: warns.append(f'{slot}: protein {p:.1f} vs {pt} target')

allitems = [x for v in DAY.values() for x in v]
print('=' * 74)
print(f'{"DAY TOTAL vs TARGET":32s} {"got":>9s} {"target":>8s}   %')
for col, key in NKEY.items():
    t = TGT.get(key)
    if not t or not t['daily']: continue
    got, want = total(allitems, col), t['daily']
    pct = got/want*100
    mark = '  LOW' if pct < 70 else ('  over' if pct > 200 else '')
    if col == 'kcal': mark = '' if got <= 1775*1.05 else '  OVER'
    print(f'  {t["name"][:30]:32s} {got:9.1f} {want:8g}  {pct:4.0f}%{mark}')
    if pct < 50 and t['permeal']: fails.append(f'{t["name"]}: {pct:.0f}% of target')

kc = total(allitems,'kcal')
print(f'\n  {"ENERGY":32s} {kc:9.0f} {1775:8g}  {kc/1775*100:4.0f}%')
print(f'  {"slot budgets sum":32s} {sum(KCAL_SLOT.values()):9d} {1775:8g}')
print(f'  {"per-slot protein sum":32s} {sum(MEAL_P.values()):9d} {100:8g}')

print()
if warns:
    print('WARNINGS'); [print('  ! ' + w) for w in warns]
if fails:
    print('FAILURES'); [print('  X ' + f) for f in fails]; sys.exit(1)
print('OK — no slot over budget, no per-meal target under half.')
