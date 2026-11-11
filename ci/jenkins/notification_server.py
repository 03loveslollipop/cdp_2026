"""Local-only completion sink; keeps receipts without contacting third parties."""
import hmac
import html
import json
import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

LOG = Path('/receipts/notifications.jsonl')
TOKEN = Path('/run/secrets/notify_token').read_text().strip()
LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != '/notify':
            self.send_error(404)
            return
        if not hmac.compare_digest(self.headers.get('Authorization', ''), f'Bearer {TOKEN}'):
            self.send_error(403)
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 65536:
                raise ValueError('Invalid payload length')
            item = json.loads(self.rfile.read(size))
            if not isinstance(item, dict) or not {'job', 'build', 'status', 'url'} <= item.keys():
                raise ValueError('Missing completion fields')
        except (ValueError, TypeError):
            self.send_error(400)
            return
        item['received_at'] = datetime.now(timezone.utc).isoformat()
        with LOCK, LOG.open('a') as handle:
            handle.write(json.dumps(item) + '\n')
        self.send_response(202)
        self.end_headers()
        self.wfile.write(b'{"accepted":true}\n')

    def do_GET(self):
        if self.path != '/':
            self.send_error(404)
            return
        entries = LOG.read_text() if LOG.exists() else 'No completions received yet.'
        body = ('<!doctype html><title>Jenkins completion receipts</title>'
                '<body style="font:18px system-ui;margin:48px"><h1>Jenkins completion receipts</h1>'
                '<p>Private local receiver. Times are UTC. No external message service is used.</p>'
                '<pre style="white-space:pre-wrap;padding:24px;background:#f0f4f8">'
                + html.escape(entries) + '</pre></body>').encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(body)


if __name__ == '__main__':
    LOG.parent.mkdir(parents=True, exist_ok=True)
    ThreadingHTTPServer(('0.0.0.0', int(os.getenv('PORT', '8081'))), Handler).serve_forever()
