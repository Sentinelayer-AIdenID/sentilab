"""MCP file authority is configured by the host, never by its caller."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from sentilab_core import resultcheck
from sentilab_core.test_resultcheck import ROOT, mcp_exchange


ERROR = {'content': [{'type': 'text', 'text': '{"error":{"code":"file_unreadable"}}'}],
         'isError': True}


class FileBoundaryTests(unittest.TestCase):
    def exchange(self, files, env):
        calls = [dict(id=i, method='tools/call', params={
            'name': 'sentilab_resultcheck', 'arguments': {'file': str(file)}})
            for i, file in enumerate(files)]
        calls.append(dict(id='ping', method='ping'))
        process = mcp_exchange(calls, env=env)
        self.assertEqual(process.stderr, b'')
        replies = {r['id']: r for r in map(json.loads, process.stdout.splitlines())}
        self.assertEqual(replies.pop('ping')['result'], {})
        self.assertEqual(set(replies), set(range(len(files))))
        return [replies[i]['result'] for i in range(len(files))]

    def test_unconfigured_or_invalid_root_never_discloses_a_file_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'input.json'
            file.write_bytes(b'not JSON')
            for root in (None, '', str(file), str(file.parent / 'missing')):
                with self.subTest(root=root):
                    env = dict(os.environ)
                    env.pop('SENTILAB_RESULTCHECK_DIR', None)
                    if root is not None:
                        env['SENTILAB_RESULTCHECK_DIR'] = root
                    self.assertEqual(self.exchange([file], env), [ERROR])

    def test_resolved_boundary_allows_inside_and_hides_every_outside_path(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / 'allowed'
            root.mkdir()
            file = root / 'input.json'
            raw = b'not JSON'
            file.write_bytes(raw)
            sibling = parent / 'allowed-sibling'
            sibling.mkdir()
            outside = sibling / 'input.json'
            outside.write_bytes(raw)
            (root / 'inside-link').symlink_to(file)
            (root / 'outside-link').symlink_to(outside)
            (root / 'outside-dir').symlink_to(sibling, target_is_directory=True)
            (root / 'loop').symlink_to(root / 'loop')
            env = {**os.environ, 'SENTILAB_RESULTCHECK_DIR': str(root)}
            allowed = [file, 'input.json', 'inside-link']
            denied = [outside, '../allowed-sibling/input.json', 'outside-link',
                      'outside-dir/input.json', sibling / 'missing', '../missing', 'loop']
            replies = self.exchange(allowed + denied, env)
            receipt = resultcheck.canonical(resultcheck.check_raw(raw))
            self.assertEqual(replies[:len(allowed)], [
                {'content': [{'type': 'text', 'text': receipt}], 'isError': True}] * len(allowed))
            self.assertEqual(replies[len(allowed):], [ERROR] * len(denied))
            # An ordinary local CLI retains its existing authority and exits.
            cli = subprocess.run([sys.executable, '-m', 'sentilab_cli', 'resultcheck', str(outside)],
                                 cwd=ROOT, env=env, capture_output=True, timeout=5)
            self.assertEqual(cli.returncode, 2)
            self.assertEqual(cli.stdout.decode(), receipt + '\n')
            self.assertEqual(cli.stderr, b'')

    def test_directory_swap_after_resolution_is_rejected_before_descriptor_read(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / 'allowed'
            slot = root / 'slot'
            slot.mkdir(parents=True)
            file = slot / 'input.json'
            file.write_bytes(b'[]')
            outside = parent / 'outside'
            outside.mkdir()
            (outside / file.name).write_bytes(b'private fixture bytes')
            hooks = parent / 'hooks'
            hooks.mkdir()
            swapped, read = parent / 'swapped', parent / 'read'
            # Inject only the filesystem race: the real worker, open, fstat,
            # descriptor resolution and read still execute in a stdio process.
            (hooks / 'sitecustomize.py').write_text(r'''
import os
from pathlib import Path
original_open, original_read = os.open, os.read
target = Path(os.environ['RC_SWAP_FILE'])
outside = Path(os.environ['RC_SWAP_OUTSIDE'])
def opened(file, *args, **kwargs):
    if os.fspath(file) == str(target):
        target.parent.rename(target.parent.with_name('old'))
        target.parent.symlink_to(outside, target_is_directory=True)
        Path(os.environ['RC_SWAPPED']).touch()
    return original_open(file, *args, **kwargs)
def read(fd, count):
    if Path('/proc/self/fd/' + str(fd)).resolve().is_relative_to(outside):
        Path(os.environ['RC_READ']).touch()
    return original_read(fd, count)
os.open, os.read = opened, read
''')
            env = {**os.environ, 'SENTILAB_RESULTCHECK_DIR': str(root), 'PYTHONPATH': str(hooks),
                   'RC_SWAP_FILE': str(file), 'RC_SWAP_OUTSIDE': str(outside),
                   'RC_SWAPPED': str(swapped), 'RC_READ': str(read)}
            replies = self.exchange([file], env)
            self.assertTrue(swapped.exists(), 'the race must actually run')
            self.assertFalse(read.exists(), 'outside descriptor bytes must never be read')
            self.assertEqual(replies, [ERROR])


if __name__ == '__main__':
    unittest.main()
