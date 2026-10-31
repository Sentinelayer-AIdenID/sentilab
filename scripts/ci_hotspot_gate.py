#!/usr/bin/env python3
"""Host broker; only loopback, fixed policy, append-only ledger outside build context."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

from scripts.ci_allocation import EXPIRY
import time


def serve(ledger, port=47631):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 16384:
                    raise ValueError('invalid message size')
                self.connection.settimeout(2)
                data = json.loads(self.rfile.read(size))
                if self.path == '/reserve':
                    if time.time() >= EXPIRY:
                        raise RuntimeError('allocation expired')
                    binary = data['binary']
                    if not isinstance(binary, str) or len(binary) != 64:
                        raise ValueError('invalid binary digest')
                    result = {'slot': ledger.reserve(binary)}
                elif self.path == '/settle':
                    ledger.settle(data['slot'], data['state'], data['returncode'])
                    result = {'settled': True}
                else:
                    raise ValueError('unknown allocation operation')
                status = 200
            except (ValueError, KeyError, RuntimeError, OSError) as exc:
                status, result = 409, {'error': str(exc)}
            body = json.dumps(result).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
