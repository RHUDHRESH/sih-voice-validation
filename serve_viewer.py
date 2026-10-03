#!/usr/bin/env python3
"""Serve a local-only side-by-side replay of saved, synthetic validation results."""
from argparse import ArgumentParser
import csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent


def bundle(results):
    summary = json.loads((results/'summary.json').read_text())
    config = json.loads((results/'config_used.json').read_text())
    cases = []
    for case in config['scenarios']:
        outputs = {}
        for policy in ('naive', 'buffered'):
            metrics = next(r for r in summary['runs'] if r['scenario_id']==case['scenario_id'] and r['policy']==policy)
            directory = results/'runs'/f'{case["scenario_id"]}__{policy}'
            def rows(name):
                with (directory/name).open() as handle:
                    return list(csv.DictReader(handle))
            outputs[policy] = {'metrics': metrics, 'events': rows('events.csv'),
                               'telemetry': rows('telemetry.csv'), 'packets': rows('packets.csv')}
        cases.append({'config': case, 'outputs': outputs})
    return {'evidence_label': 'replay_of_computed_synthetic_simulation',
            'summary_status': summary['status'], 'cases': cases,
            'warning': 'Oracle trigger and endpoint; no trained KWS, ASR or hardware measurement.'}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--results', type=Path, default=ROOT/'results/latest')
    args = parser.parse_args()
    if not (args.results/'summary.json').exists():
        parser.error('Results missing. Run python3 run_validation.py first.')
    data = json.dumps(bundle(args.results.resolve()), separators=(',', ':')).encode()
    assets = {'/': ('text/html; charset=utf-8', ROOT/'viewer/index.html'),
              '/index.html': ('text/html; charset=utf-8', ROOT/'viewer/index.html'),
              '/app.js': ('text/javascript; charset=utf-8', ROOT/'viewer/app.js'),
              '/style.css': ('text/css; charset=utf-8', ROOT/'viewer/style.css')}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path).path
            if path == '/api/data':
                body, content_type = data, 'application/json'
            elif path in assets:
                content_type, file = assets[path]
                body = file.read_bytes()
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Local replay: http://127.0.0.1:{args.port} (Ctrl-C to stop)', flush=True)
    print('Computed synthetic results only; no microphone, network ASR or hardware connection.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
