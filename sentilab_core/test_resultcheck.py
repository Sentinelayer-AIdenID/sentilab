"""Conformance tests exercise the reference and the shipped CLI/MCP processes."""
import asyncio
import hashlib
import json
import os
import time
from unittest.mock import patch
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


def mcp_exchange(calls, *, env=None):
    """Keep stdin open until replies arrive; EOF cancels in-flight MCP work."""
    async def exchange():
        process = await asyncio.create_subprocess_exec(
            sys.executable, '-m', 'sentilab_mcp', cwd=ROOT, env=env,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)
        replies = []
        try:
            for call in calls:
                process.stdin.write((json.dumps(call) + '\n').encode())
                await process.stdin.drain()
                if 'id' in call:
                    replies.append(await asyncio.wait_for(process.stdout.readline(), 10))
            process.stdin.close()
            tail, stderr = await asyncio.wait_for(process.communicate(), 10)
            return subprocess.CompletedProcess('sentilab_mcp', process.returncode,
                                               b''.join(replies) + tail, stderr)
        finally:
            if process.returncode is None:
                process.kill()
            await process.wait()
    result = asyncio.run(exchange())
    result.check_returncode()
    return result


class ResultCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vectors = []
        for vector in json.loads((CONTRACT / 'vectors-resultcheck.json').read_text())['vectors']:
            request = None
            if 'raw' in vector:
                raw = vector['raw']
            elif 'raw_generate' in vector:
                spec = vector['raw_generate']
                if spec['kind'] == 'deep':
                    raw = '[' * spec['depth'] + ']' * spec['depth']
                elif spec['kind'] == 'multibyte_notes':
                    raw = json.dumps(dict(schema_version='resultcheck.request.v2', request_id='x',
                        metric=dict(name='t', unit='ms', direction='lower_is_better'),
                        pairs=[], notes='é' * spec['chars']), ensure_ascii=False, separators=(',', ':'))
                else:
                    raise AssertionError('unknown vector generator')
            else:
                request = dict(schema_version='resultcheck.request.v2', request_id='vector', **vector['request'])
                if 'generate_pairs' in vector:
                    spec = vector['generate_pairs']
                    request['pairs'] = [dict(id=f'w{i}', baseline=2, candidate=1) for i in range(spec['wins'])]
                    request['pairs'] += [dict(id=f'l{i}', baseline=1, candidate=2) for i in range(spec['losses'])]
                raw = json.dumps(request, ensure_ascii=False, separators=(',', ':'))
            cls.vectors.append(dict(name=vector['name'], raw=raw, expected=vector['expect'],
                                    banned=vector.get('receipt_must_not_contain', []), request=request))

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
            mcp = mcp_exchange(calls, env={**os.environ, 'SENTILAB_RESULTCHECK_DIR': directory})
            self.assertEqual(mcp.stderr, b'')
            replies = [json.loads(line) for line in mcp.stdout.splitlines()]
            self.assertEqual(len(replies), len(self.vectors) + 2)
            replies_by_id = {reply['id']: reply for reply in replies}
            self.assertEqual(set(replies_by_id), {0, 'list', *range(1, len(self.vectors) + 1)})
            self.assertEqual(replies_by_id[0]['result']['protocolVersion'], '2024-11-05')
            self.assertIn('sentilab_resultcheck', [tool['name'] for tool in replies_by_id['list']['result']['tools']])
            for i, (vector, file) in enumerate(zip(self.vectors, files), 1):
                with self.subTest(vector=vector['name']):
                    reply = replies_by_id[i]
                    receipt = resultcheck.check_raw(file.read_bytes())
                    expected = vector.get('receipt', resultcheck.canonical(receipt))
                    if vector.get('request') is not None:
                        self.assertEqual(resultcheck.canonical(resultcheck.check(vector['request'])), expected)
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
                    self.assertEqual(reply['result']['isError'], receipt['status'] == 'rejected')
                    self.assertEqual(reply['result']['content'], [{'type': 'text', 'text': expected}])
                    for banned in vector['banned']:
                        self.assertNotIn(banned, expected)


    def test_size_limit_before_parse_and_full_file_hash(self):
        raw = b'{' + b'x' * (10 * 1024 * 1024 - 1)
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'oversize.json'
            file.write_bytes(raw)
            started = time.monotonic()
            # Parser is a dependency, not the unit under test: entering it is a defect.
            with patch.object(resultcheck.json, 'loads', side_effect=AssertionError('parsed oversized input')):
                receipt = resultcheck.check_file(file)
                self.assertEqual(resultcheck.check_raw(raw), receipt)
            self.assertLess(time.monotonic() - started, 5)
            self.assertEqual(receipt['errors'], ['request_too_large'])
            self.assertEqual(receipt['request_hash'], hashlib.sha256(raw).hexdigest())
            self.assertIsNone(receipt['statistics'])
            boundary = b'[]' + b' ' * (resultcheck.MAX_BYTES - 2)
            self.assertEqual(resultcheck.check_raw(boundary)['errors'], ['not_an_object'])
            self.assertEqual(resultcheck.check_raw(boundary + b' ')['errors'], ['request_too_large'])

    def test_deep_json_syntax_and_structure_bounds(self):
        for raw, error in [('[' * 100000 + ']' * 100000, 'request_too_deep'),
                           ('[' * 100000 + ']' * 99999, 'not_json'),
                           ('[' * 1000 + '1,]' + ']' * 999, 'not_json'),
                           ('{"x":' * 1000 + '[]' + '}' * 1000, 'request_too_deep')]:
            with self.subTest(error=error, length=len(raw)):
                receipt = resultcheck.check_raw(raw)
                self.assertEqual(receipt['errors'], [error])
                if error == 'request_too_deep':
                    self.assertIsNone(receipt['request_hash'])
        self.assertEqual(resultcheck.check_raw('[' * 8 + ']' * 8)['errors'], ['not_an_object'])
        self.assertEqual(resultcheck.check_raw('[' * 9 + ']' * 9)['errors'], ['request_too_deep'])
        self.assertEqual(resultcheck.check([None] * 200000)['errors'], ['request_too_large'])

    def test_schema_codes_and_invalid_encoding(self):
        request = dict(schema_version='resultcheck.request.v2', request_id='schema',
                       metric=dict(name='latency', unit='ms', direction='lower_is_better'), pairs=[])
        cases = [('schema_version', 'v1', 'bad_schema_version'),
                 ('request_id', 'not an id', 'bad_request_id'), ('metric', None, 'bad_metric'),
                 ('pairs', None, 'bad_pairs'), ('pairs', [None], 'bad_pairs'),
                 ('pairs', [dict(id='a', baseline=True, candidate=1)], 'bad_pair_value'),
                 ('pairs', [dict(id='a', baseline=1, candidate=2, group=False)], 'bad_pair_group'),
                 ('claim', dict(estimand='unknown', value=1), 'bad_claim'),
                 ('notes', '😀' * 2049, 'bad_notes')]
        for key, value, code in cases:
            with self.subTest(code=code):
                self.assertEqual(resultcheck.check({**request, key: value})['errors'], [code])
        for raw in (b'\xff', b'NaN', b'Infinity', b'1 2', b''):
            self.assertEqual(resultcheck.check_raw(raw)['errors'], ['not_json'])

    def test_notes_hashes_and_byte_determinism(self):
        request = json.loads(self.vectors[1]['raw'])
        before = resultcheck.check(request)
        after = resultcheck.check({**request, 'notes': 'opaque untrusted text'})
        self.assertNotEqual(before['request_hash'], after['request_hash'])
        self.assertEqual(before['statistics'], after['statistics'])
        self.assertNotIn('opaque untrusted text', resultcheck.canonical(after))
        self.assertEqual(before, resultcheck.check_raw(json.dumps(request, indent=2)))
        self.assertEqual(before, resultcheck.check(dict(reversed(list(request.items())))))
        unsealed = {key: value for key, value in before.items() if key != 'receipt_hash'}
        self.assertEqual(before['receipt_hash'], hashlib.sha256(resultcheck.canonical(unsealed).encode()).hexdigest())

    def test_transports_without_node_or_live_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, 'PATH': directory, 'SENTILAB_SIGNER_FACTORY': 'missing:factory',
                   'SENTILAB_VIEW_PUBLIC_KEYS': 'invalid', 'SENTILAB_RESULTCHECK_DIR': directory}
            file = Path(directory) / 'input.json'
            file.write_text(self.vectors[1]['raw'])
            cli = subprocess.run([sys.executable, str(ROOT / 'sentilab_cli' / 'sentilab'), 'resultcheck', str(file)],
                                 env=env, capture_output=True, timeout=10, check=True)
            request = dict(jsonrpc='2.0', id=1, method='tools/call', params={
                'name': 'sentilab_resultcheck', 'arguments': {'file': str(file)}})
            mcp = mcp_exchange([request], env=env)
            self.assertEqual(cli.stdout.rstrip(b'\n').decode(), json.loads(mcp.stdout)['result']['content'][0]['text'])
            self.assertEqual(cli.stderr + mcp.stderr, b'')
            file.unlink()
            missing = subprocess.run([sys.executable, '-m', 'sentilab_cli', 'resultcheck', str(file)],
                                     cwd=ROOT, env=env, capture_output=True, timeout=10)
            self.assertEqual(missing.returncode, 2)
            self.assertEqual(json.loads(missing.stdout), {'error': {'code': 'file_unreadable'}})
            bad_calls = [request, {**request, 'id': 2, 'params': {'name': 'sentilab_resultcheck', 'arguments': {}}},
                         {**request, 'id': 3, 'params': {'name': 'sentilab_resultcheck', 'arguments': {'file': 42}}}]
            mcp = mcp_exchange(bad_calls, env=env)
            responses = [json.loads(line) for line in mcp.stdout.splitlines()]
            self.assertEqual(len(responses), 3)
            responses_by_id = {response['id']: response for response in responses}
            self.assertEqual(set(responses_by_id), {1, 2, 3})
            self.assertTrue(responses_by_id[1]['result']['isError'])
            self.assertEqual(responses_by_id[1]['result']['content'][0]['text'], missing.stdout.decode().strip())
            self.assertEqual([responses_by_id[i]['error']['code'] for i in (2, 3)], [-32602, -32602])

    def test_rounding_and_overflow_match_reference_examples(self):
        request = dict(schema_version='resultcheck.request.v2', request_id='rounding',
                       metric=dict(name='t', unit='ms', direction='lower_is_better', scale='ratio'))
        for wins, losses, expected in [(6, 2, 0.289063), (8, 0, 0.007813), (6, 3, 0.507812)]:
            pairs = [dict(id=f'w{i}', baseline=2, candidate=1) for i in range(wins)]
            pairs += [dict(id=f'l{i}', baseline=1, candidate=2) for i in range(losses)]
            with self.subTest(wins=wins, losses=losses):
                self.assertEqual(resultcheck.check({**request, 'pairs': pairs})['statistics']['sign_test_p_two_sided'], expected)
        request.update(pairs=[dict(id='a', baseline=1e308, candidate=-1e308),
                              dict(id='b', baseline=1e308, candidate=0)],
                       claim=dict(estimand='percent_change_of_means', value=1))
        receipt = json.loads(resultcheck.canonical(resultcheck.check(request)))
        self.assertIsNone(receipt['claim_result']['tolerance'])
        self.assertEqual(receipt['claim_result']['outcome'], 'discrepancy')

    def test_evidence_manifest_matches_reviewed_contract(self):
        manifest = json.loads((ROOT / 'docs/sentilab/evidence/SLAB-022/MANIFEST.json').read_text())
        self.assertEqual(manifest['verdict_schema_version'], resultcheck.SCHEMA_VERSION)
        self.assertEqual(manifest['checker_version'], resultcheck.CHECKER_VERSION)
        self.assertEqual(manifest['vector_count'], len(self.vectors))
        reviewed = dict(line.split()[::-1] for line in (ROOT / 'contracts/HASHES.txt').read_text().splitlines() if line.strip())
        for path, digest in manifest['contract_files'].items():
            self.assertEqual(digest, reviewed[path.removeprefix('contracts/')])
            self.assertEqual(digest, hashlib.sha256((ROOT / path).read_bytes()).hexdigest())


def parity_suite():
    """Explicit Node-only gate, separate from the Python-only container suite."""
    class ContractParityTests(ResultCheckTests):
        @classmethod
        def setUpClass(cls):
            reference = subprocess.run(['node', '--input-type=module', '-e', REFERENCE],
                                       cwd=ROOT, check=True, capture_output=True, text=True, timeout=30)
            cls.vectors = [json.loads(line) for line in reference.stdout.splitlines()]

        def test_reference_numeric_and_schema_edges(self):
            base = dict(schema_version='resultcheck.request.v2', request_id='numeric',
                        metric=dict(name='t', unit='ms', direction='lower_is_better', scale='ratio'))
            cases = []
            for n in range(6, 41):
                for wins in range((n + 1) // 2, n + 1):
                    pairs = [dict(id=f'w{i}', baseline=2, candidate=1) for i in range(wins)]
                    pairs += [dict(id=f'l{i}', baseline=1, candidate=2) for i in range(n - wins)]
                    cases.append({**base, 'pairs': pairs})
            for value in (1e308, -1e308, 1e-308, 5e-324, 1e21, 1e20, 9007199254740993, 0.0000005):
                for estimand in ('mean_difference', 'percent_change_of_means', 'mean_of_percent_changes'):
                    cases.append({**base, 'pairs': [dict(id='a', baseline=value, candidate=-value),
                                                   dict(id='b', baseline=value, candidate=0)],
                                  'claim': dict(estimand=estimand, value=1)})
            cases += [{**base, 'pairs': [], 'notes': value} for value in ('é', '😀', '\ud800', '\udfff', '\ufeff')]
            cases += [None, [], {}, {**base, 'pairs': [], 'metric': {'name': '😀' * 65}},
                      {**base, 'pairs': [], 'claim': {'estimand': [], 'value': 1}}]
            nested = []
            for _ in range(9):
                nested = [nested]
            cases.append({'a': [0] * 200000, '0': nested})
            raw = [json.dumps(case, ensure_ascii=True) for case in cases]
            raw += ['NaN', 'Infinity', '{"x":1e400}', '\ufeff{}', '\ud800', '"\ud800"', '[' * 1000 + ']' * 999]
            script = """import {canonical,checkRaw} from './contracts/contract-0.2/resultcheck.mjs';
let s=''; for await (const chunk of process.stdin) s+=chunk;
console.log(JSON.stringify(JSON.parse(s).map(raw=>canonical(checkRaw(raw)))));"""
            reference = subprocess.run(['node', '--input-type=module', '-e', script], cwd=ROOT,
                                       input=json.dumps(raw), text=True, capture_output=True, check=True, timeout=30)
            for i, (text, expected) in enumerate(zip(raw, json.loads(reference.stdout))):
                with self.subTest(case=i):
                    self.assertEqual(resultcheck.canonical(resultcheck.check_raw(text)), expected)

    return unittest.defaultTestLoader.loadTestsFromTestCase(ContractParityTests)


if __name__ == '__main__':
    if sys.argv[1:] == ['--parity']:
        raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(parity_suite()).wasSuccessful())
    unittest.main()
