#!/usr/bin/env python3
"""Host broker; only loopback, fixed policy, append-only ledger outside build context."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from scripts.ci_allocation import EXPIRY


def serve(ledger, port=47631, *, now=time.time):
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
                    if now() >= EXPIRY:
                        raise RuntimeError('allocation expired')
                    binary = data['binary']
                    if not isinstance(binary, str) or len(binary) != 64:
                        raise ValueError('invalid binary digest')
                    result = {'slot': ledger.reserve(binary)}
                elif self.path == '/violation':
                    ledger.violation()
                    result = {'refused': True}
                elif self.path == '/started':
                    ledger.started(data['slot'], data['pid'])
                    result = {'started': True}
                elif self.path == '/settle':
                    ledger.settle(data['slot'], data['state'], data['returncode'])
                    result = {'settled': True}
                else:
                    raise ValueError('unknown allocation operation')
                status = 200
            except (ValueError, KeyError, RuntimeError, OSError) as exc:
                status, result = 409, {'error': str(exc)}
            body = json.dumps(result).encode()
            try:
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                # A killed client cannot undo the fsynced reservation/violation.
                pass

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
