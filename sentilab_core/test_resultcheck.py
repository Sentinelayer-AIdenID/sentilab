"""Conformance tests exercise the reference and the shipped CLI/MCP processes."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from sentilab_core import resultcheck

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / 'contracts' / 'contract-0.2'
REFERENCE = r'''
import {readFileSync} from 'node:fs';
import {canonical, check, checkRaw} from './contracts/contract-0.2/resultcheck.mjs';
const vectors = JSON.parse(readFileSync('contracts/contract-0.2/vectors-resultcheck.json')).vectors;
for (const v of vectors) {
  let raw;
  if ('raw' in v) raw = v.raw;
  else if (v.raw_generate?.kind === 'deep') raw = '['.repeat(v.raw_generate.depth) + ']'.repeat(v.raw_generate.depth);
  else if (v.raw_generate?.kind === 'multibyte_notes') raw = JSON.stringify({schema_version:'resultcheck.request.v2', request_id:'x', metric:{name:'t',unit:'ms',direction:'lower_is_better'},pairs:[],notes:'é'.repeat(v.raw_generate.chars)});
  else {
    const r = {schema_version:'resultcheck.request.v2', request_id:'vector', ...v.request};
    if (v.generate_pairs) r.pairs = [
      ...Array.from({length:v.generate_pairs.wins}, (_,i)=>({id:`w${i}`,baseline:2,candidate:1})),
      ...Array.from({length:v.generate_pairs.losses}, (_,i)=>({id:`l${i}`,baseline:1,candidate:2}))];
    raw = JSON.stringify(r);
    if (canonical(check(r)) !== canonical(checkRaw(raw))) throw Error(v.name);
  }
  console.log(JSON.stringify({name:v.name,raw,expected:v.expect,banned:v.receipt_must_not_contain??[],receipt:canonical(checkRaw(raw))}));
}
'''


class ResultCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Missing Node is a failing gate, never a skipped conformance check.
        reference = subprocess.run(['node', '--input-type=module', '-e', REFERENCE],
                                   cwd=ROOT, check=True, capture_output=True, text=True)
        cls.vectors = [json.loads(line) for line in reference.stdout.splitlines()]

    def subset(self, actual, expected):
        if isinstance(expected, dict):
            self.assertIsInstance(actual, dict)
            if not expected:
                self.assertEqual(actual, {})
            for key, value in expected.items():
                self.assertIn(key, actual)
                self.subset(actual[key], value)
        elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
            self.assertIsInstance(actual, (int, float))
            self.assertAlmostEqual(actual, expected, delta=1e-6)
        else:
            self.assertEqual(actual, expected)

    def test_all_contract_vectors_core_cli_mcp(self):
        with tempfile.TemporaryDirectory() as directory:
            files = []
            calls = [dict(jsonrpc='2.0', id=0, method='initialize', params={
                'protocolVersion': '2024-11-05', 'capabilities': {},
                'clientInfo': {'name': 'conformance', 'version': '1'}}),
                dict(jsonrpc='2.0', method='notifications/initialized'),
                dict(jsonrpc='2.0', id='list', method='tools/list')]
            for i, vector in enumerate(self.vectors, 1):
                file = Path(directory) / f'{i}.json'
                file.write_bytes(vector['raw'].encode('utf-8'))
                files.append(file)
                calls.append(dict(jsonrpc='2.0', id=i, method='tools/call', params={
                    'name': 'sentilab_resultcheck', 'arguments': {'file': str(file)}}))
            mcp = subprocess.run([sys.executable, '-m', 'sentilab_mcp'], cwd=ROOT,
                                 input=''.join(json.dumps(x) + '\n' for x in calls),
                                 capture_output=True, text=True, timeout=30, check=True)
            self.assertEqual(mcp.stderr, '')
            replies = [json.loads(line) for line in mcp.stdout.splitlines()]
            self.assertEqual(len(replies), len(self.vectors) + 2)
            self.assertEqual(replies[0]['result']['protocolVersion'], '2024-11-05')
            self.assertIn('sentilab_resultcheck', [tool['name'] for tool in replies[1]['result']['tools']])
            for i, (vector, file, reply) in enumerate(zip(self.vectors, files, replies[2:]), 1):
                with self.subTest(vector=vector['name']):
                    expected = vector['receipt']
                    receipt = resultcheck.check_raw(file.read_bytes())
                    self.subset(receipt, vector['expected'])
                    self.subset(json.loads(expected), vector['expected'])
                    self.assertEqual(resultcheck.canonical(receipt), expected)
                    self.assertEqual(resultcheck.canonical(resultcheck.check_raw(file.read_bytes())), expected)
                    cli = subprocess.run([sys.executable, '-m', 'sentilab_cli', 'resultcheck', str(file)],
                                         cwd=ROOT, capture_output=True, timeout=10)
                    code = {'checked': 0, 'checked_with_flags': 1, 'insufficient_data': 1, 'rejected': 2}[receipt['status']]
                    self.assertEqual(cli.returncode, code)
                    self.assertEqual(cli.stderr, b'')
                    self.assertEqual(cli.stdout, (expected + '\n').encode())
                    self.assertEqual(reply['id'], i)
                    self.assertEqual(reply['result']['content'], [{'type': 'text', 'text': expected}])
                    for banned in vector['banned']:
                        self.assertNotIn(banned, expected)


if __name__ == '__main__':
    unittest.main()
