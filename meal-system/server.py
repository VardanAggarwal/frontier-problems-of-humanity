#!/usr/bin/env python3
"""Static file server for the meal planner + tiny write API so saved recipes
persist to recipes.csv (browsers can't write local files themselves).

Run:  python3 server.py   →  http://127.0.0.1:8777/planner.html
Endpoints:
  POST /api/recipe         body {id,name,meals,core,opt,method}  → append a row to recipes.csv
  POST /api/recipe/delete  body {id}                              → remove that row (user recipes only, id starts 'u')
"""
import json, os, http.server, socketserver

DIR = os.path.dirname(os.path.abspath(__file__))
RECIPES = os.path.join(DIR, 'recipes.csv')
PORT = 8777


def _clean(s):      # keep CSV single-line, comma-free
    return str(s).replace(',', ' ').replace('\n', ' ').replace('\r', ' ').strip()

def _ids(x):
    return ' '.join(_clean(i).replace(' ', '') for i in (x or []) if str(i).strip())


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=DIR, **k)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')  # always see fresh recipes.csv
        super().end_headers()

    def _body(self):
        n = int(self.headers.get('Content-Length', 0) or 0)
        return json.loads(self.rfile.read(n) or b'{}')

    def _json(self, code, obj):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode())

    def do_POST(self):
        try:
            if self.path == '/api/recipe':
                d = self._body()
                row = ','.join([_clean(d.get('id', '')), _clean(d.get('name', 'Recipe')),
                                _ids(d.get('meals')), _ids(d.get('core')), _ids(d.get('opt')),
                                _clean(d.get('method', ''))])
                with open(RECIPES, 'r+', encoding='utf-8') as f:
                    c = f.read()
                    if c and not c.endswith('\n'):
                        f.write('\n')
                    f.write(row + '\n')
                return self._json(200, {'ok': True})
            if self.path == '/api/recipe/delete':
                rid = _clean(self._body().get('id', ''))
                if rid.startswith('u'):
                    with open(RECIPES, encoding='utf-8') as f:
                        lines = f.readlines()
                    kept = [ln for ln in lines if ln.split(',', 1)[0].strip() != rid]
                    with open(RECIPES, 'w', encoding='utf-8') as f:
                        f.writelines(kept)
                return self._json(200, {'ok': True})
            self._json(404, {'error': 'not found'})
        except Exception as e:
            self._json(500, {'error': str(e)})


if __name__ == '__main__':
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(('127.0.0.1', PORT), Handler) as httpd:
        print(f'serving {DIR} at http://127.0.0.1:{PORT}')
        httpd.serve_forever()
