"""Narrow GitHub HTTPS ingress; Cloud Run supplies TLS, Jenkins stays private."""
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
import re
import socket
import threading
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

REPOSITORY = '03loveslollipop/cdp_2026'
REPOSITORY_ID = 1311514433
MAX_BODY = 2 * 1024 * 1024


class Relay:
    def __init__(self, secret, upstream, expires_at, branches):
        parsed = urlsplit(upstream)
        if (parsed.scheme != 'http' or parsed.port != 8080 or parsed.path not in {'', '/'}
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or ipaddress.ip_address(parsed.hostname) not in ipaddress.ip_network('10.81.0.0/28')):
            raise ValueError('Upstream must be this lab private Jenkins address on port 8080')
        if len(secret) < 32:
            raise ValueError('A high-entropy shared secret is required')
        self.secret, self.upstream = secret.encode(), upstream.rstrip('/') + '/github-webhook/'
        self.expires = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
        self.branches = {'refs/heads/' + branch for branch in branches}
        self.seen, self.lock = {}, threading.Lock()

    def handle(self, headers, body, *, forward=None, now=None):
        now = now or datetime.now(timezone.utc)
        if now >= self.expires:
            return 410, {'error': 'lab expired'}
        if not 0 < len(body) <= MAX_BODY:
            return 413, {'error': 'invalid payload length'}
        expected = 'sha256=' + hmac.new(self.secret, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(headers.get('X-Hub-Signature-256', ''), expected):
            return 403, {'error': 'invalid signature'}
        delivery = headers.get('X-GitHub-Delivery', '')
        if not re.fullmatch(r'[0-9a-fA-F-]{36}', delivery):
            return 400, {'error': 'invalid delivery id'}
        try:
            payload = json.loads(body)
            repository = payload.get('repository', {})
            if repository.get('id') != REPOSITORY_ID or repository.get('full_name') != REPOSITORY:
                return 403, {'error': 'repository not allowed'}
        except (ValueError, AttributeError):
            return 400, {'error': 'invalid JSON object'}
        event = headers.get('X-GitHub-Event', '')
        if event == 'ping':
            return 200, {'accepted': 'ping'}
        if event != 'push' or payload.get('deleted') or payload.get('ref') not in self.branches:
            return 202, {'ignored': 'event or ref outside configured branches'}
        if not re.fullmatch(r'[0-9a-f]{40}', str(payload.get('after', ''))):
            return 400, {'error': 'invalid revision'}
        fingerprint = hashlib.sha256(body).hexdigest()
        # Only successful forwards are remembered. Jenkins SCM polling provides
        # commit-based deduplication across instance restarts as well.
        with self.lock:
            prior = self.seen.get(delivery)
            if prior:
                return (200, {'duplicate': True}) if prior == fingerprint else (409, {'error': 'delivery id reused'})
            try:
                status = (forward or self.forward)(headers, body)
            except (HTTPError, URLError, TimeoutError, OSError):
                return 502, {'error': 'Jenkins unavailable; redeliver after recovery'}
            if not 200 <= status < 300:
                return 502, {'error': 'Jenkins rejected delivery'}
            self.seen[delivery] = fingerprint
            while len(self.seen) > 256:
                del self.seen[next(iter(self.seen))]
        print(json.dumps({'event': event, 'delivery': delivery, 'ref': payload['ref'],
                          'sha': payload['after'], 'upstream_status': status,
                          'received_at_utc': now.isoformat()}), flush=True)
        return 200, {'accepted': True, 'delivery': delivery}

    def forward(self, headers, body):
        forwarded = {key: headers[key] for key in ['X-Hub-Signature-256', 'X-GitHub-Event', 'X-GitHub-Delivery']}
        forwarded['Content-Type'] = 'application/json'
        with urlopen(Request(self.upstream, data=body, headers=forwarded), timeout=8) as response:
            return response.status


class Handler(BaseHTTPRequestHandler):
    relay = None

    def log_message(self, *args):
        pass

    def respond(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path != '/healthz':
            return self.respond(404, {'error': 'not found'})
        parsed = urlsplit(self.relay.upstream)
        try:
            with socket.create_connection((parsed.hostname, parsed.port), timeout=2):
                return self.respond(200, {'ready': True})
        except OSError:
            return self.respond(503, {'ready': False})

    def do_POST(self):
        if self.path != '/github-webhook/':
            return self.respond(404, {'error': 'not found'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY or self.headers.get('Transfer-Encoding'):
                return self.respond(413, {'error': 'invalid payload length'})
            if self.headers.get_content_type() != 'application/json':
                return self.respond(415, {'error': 'JSON required'})
            self.connection.settimeout(5)
            body = self.rfile.read(length)
            if len(body) != length:
                return self.respond(400, {'error': 'incomplete body'})
            status, result = self.relay.handle(self.headers, body)
            return self.respond(status, result)
        except (ValueError, TimeoutError, OSError):
            return self.respond(400, {'error': 'invalid request'})


if __name__ == '__main__':
    Handler.relay = Relay(os.environ['WEBHOOK_SECRET'], os.environ['JENKINS_URL'],
                          os.environ['EXPIRES_AT'], os.environ['BRANCHES'].split(','))
    ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PORT', '8080'))), Handler).serve_forever()
