"""CI launch wrapper. Copied HotSpot trees retain this module and entry guard.

Only non-CI callers use subprocess.run directly. The CI broker owns all counters;
workers have no ledger path to reset. A failed reservation never starts a child.
"""
import hashlib
import http.client
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys

BROKER_PORT = 47631


def request(event, **fields):
    connection = http.client.HTTPConnection('127.0.0.1', BROKER_PORT, timeout=5)
    try:
        connection.request('POST', '/' + event, json.dumps(fields),
                           {'Content-Type': 'application/json'})
        response = connection.getresponse()
        data = json.loads(response.read(16384))
        if response.status != 200:
            raise RuntimeError('CI allocation refused: ' + data.get('error', 'broker failure'))
        return data
    finally:
        connection.close()


def run_reserved(command, *, reserve, settle, started, timeout=None, **kwargs):
    """The fake-test seam is the broker transport, never the launched code.

    The fd handshake authorizes exactly one compiled entry. It is an inherited
    socket, not an environment bearer value or a file containing a secret.
    """
    binary = Path(command[0])
    slot = reserve(hashlib.sha256(binary.read_bytes()).hexdigest())
    state, code, process = 'launch_error', None, None
    parent, child = socket.socketpair()
    try:
        environment = dict(kwargs.pop('env', os.environ))
        environment['CI_HOTSPOT_ENTRY_FD'] = str(child.fileno())
        process = subprocess.Popen(command, pass_fds=(child.fileno(),), env=environment, **kwargs)
        child.close()
        started(slot, process.pid)
        parent.sendall(b'G')
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            state = 'timeout'
            process.kill()
            stdout, stderr = process.communicate()
            code = process.returncode
            raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr)
        code = process.returncode
        state = 'success' if code == 0 else ('killed' if code < 0 else 'failure')
        return subprocess.CompletedProcess(command, code, stdout, stderr)
    finally:
        child.close()
        parent.close()
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
            state, code = 'killed', process.returncode
        settle(slot, state, code)


def run_hotspot(command, *, capture_output=False, check=False, **kwargs):
    if os.environ.get('CI_ALLOCATION') != '1':
        return subprocess.run(command, capture_output=capture_output, check=check, **kwargs)
    if capture_output:
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    result = run_reserved(command, reserve=lambda binary: request('reserve', binary=binary)['slot'],
                          started=lambda slot, pid: request('started', slot=slot, pid=pid),
                          settle=lambda slot, state, code: request('settle', slot=slot, state=state,
                                                                  returncode=code), **kwargs)
    if check:
        result.check_returncode()
    return result
