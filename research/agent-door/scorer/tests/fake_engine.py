"""Synthetic HotSpot file writer. No fake result is a thermal reference."""
import json
import os
from pathlib import Path
import resource
import socket
import sys
import time

CONTROL = Path('__CONTROL__')
mode = CONTROL.read_text()
report = CONTROL.with_name('observed-' + str(os.getpid()) + '.json')
network_denied = False
try:
    socket.socket()
except PermissionError:
    network_denied = True
report.write_text(json.dumps({'pid': os.getpid(), 'executable': sys.executable,
                              'limits': resource.getrlimit(resource.RLIMIT_CPU),
                              'network_denied': network_denied, 'environment': sorted(os.environ)}))
if mode == 'escape':
    child = os.fork()
    if child == 0:
        os.setsid()
        CONTROL.with_name('escaped.pid').write_text(str(os.getpid()))
        while True:
            time.sleep(1)
if mode in ('timeout', 'escape'):
    time.sleep(60)
if mode == 'cpu':
    while True:
        pass
if mode == 'error':
    raise SystemExit(9)
if mode == 'sleep-normal':
    time.sleep(1)
if mode == 'truncated':
    Path('sample.grid.steady').write_text('Layer 0:\n0\t388.08\n')
    raise SystemExit(0)

# Complete block evidence, read through the production gate-zero reader.
lines = [line.strip() for line in Path('samplelayers.lcf').read_text().splitlines()
         if line.strip() and not line.startswith('#')]
steady = []
for offset in range(0, len(lines), 7):
    layer, flp = int(lines[offset]), Path(lines[offset + 6])
    for line in flp.read_text().splitlines():
        if line.strip() and not line.startswith('#'):
            steady.append(f'layer_{layer}_{line.split()[0]}\t389.08\n')
Path('sample.steady').write_text(''.join(steady))
with Path('sample.grid.steady').open('w') as stream:
    for layer in range(8):
        stream.write(f'Layer {layer}:\n')
        for index in range(4096):
            value = 388.09 if mode == 'mismatch' else 388.08
            if layer == 4 and index == 0:
                value = 392.21 if mode == 'lower' else 392.22
            stream.write(f'{index}\t{value:.2f}\n')
