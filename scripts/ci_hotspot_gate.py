#!/usr/bin/env python3
"""Host broker; only loopback, fixed policy, append-only ledger outside build context."""
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from scripts.ci_allocation import EXPIRY


class Broker(ThreadingHTTPServer):
    """Bounded drain of accepted handlers and the listener backlog before export."""
    daemon_threads = True  # a stuck handler cannot hang the runner indefinitely
    drain_timeout = 5
    max_handlers = 128

    def __init__(self, *args, **kwargs):
        self.active = set()
        self.condition = threading.Condition()
        self.quiescent = False
        self.incomplete = False
        self.closed = False
        self.serving = False
        super().__init__(*args, **kwargs)

    def get_request(self):
        request, address = super().get_request()
        request.settimeout(2)  # includes header parsing, not just the request body
        return request, address

    def process_request(self, request, address):
        with self.condition:
            if len(self.active) >= self.max_handlers:
                self.incomplete = True
                self.shutdown_request(request)
                return
            # Register BEFORE starting the thread: close cannot miss queued work.
            self.active.add(request)
        try:
            super().process_request(request, address)
        except Exception:
            with self.condition:
                self.incomplete = True
                self.active.remove(request)
                self.condition.notify_all()
            self.shutdown_request(request)
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            with self.condition:
                self.active.remove(request)
                self.condition.notify_all()

    def server_close(self):
        if self.closed:
            return
        if not self.serving:  # bind failure: there is no accept thread to stop
            super().server_close()
            self.closed = True
            return
        deadline = time.monotonic() + self.drain_timeout
        self.shutdown()
        # All workload senders are stopped by the meter first. Consume buffered
        # requests even if serve_forever stopped before accepting them.
        self.socket.setblocking(False)
        for _ in range(self.max_handlers):
            if time.monotonic() >= deadline:
                self.incomplete = True
                break
            try:
                request, address = self.get_request()
            except BlockingIOError:
                break
            self.process_request(request, address)
        else:
            self.incomplete = True
        super().server_close()
        self.closed = True
        with self.condition:
            while self.active:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.incomplete = True
                    for request in self.active:
                        try:
                            request.shutdown(socket.SHUT_RDWR)
                        except OSError:
                            pass
                    break
                self.condition.wait(remaining)
            self.quiescent = not self.incomplete and not self.active and time.monotonic() < deadline


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

    server = Broker(('127.0.0.1', port), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
    server.serving = True
    thread.start()
    return server
