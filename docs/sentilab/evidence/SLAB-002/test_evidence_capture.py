"""Exercise the actual embedded recorder without spending any thermal solves.

Load definitions verbatim from the shipping shell script; subprocesses and file
copies are real. These checks do not invoke the full regression driver.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / 'scripts/sentilab_regress.sh'


def recorder():
    source = SCRIPT.read_text().split("<<'EVIDENCE_PY'\n", 1)[1].split('\nEVIDENCE_PY\n', 1)[0]
    namespace = {'__name__': 'evidence_recorder'}
    exec(compile(source, str(SCRIPT), 'exec'), namespace)
    return namespace


class EvidenceCaptureTests(unittest.TestCase):
    def setUp(self):
        self.api = recorder()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name) / 'run'
        self.run.mkdir()
        self.scratch = Path(self.temp.name) / 'scratch'
        self.scratch.mkdir()
        self.api['initialize'](ROOT, self.run)

    def assert_refs(self, step):
        for ref in [step['stdout'], step['stderr'], *step['artifacts']]:
            path = self.run / ref['path']
            self.assertTrue(path.is_file())
            self.assertEqual(ref['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_failed_demo_keeps_streams_artifacts_and_failure_after_cleanup(self):
        command = [sys.executable, '-c',
                   "from pathlib import Path; import sys; "
                   "Path('demo_results.json').write_text('partial report'); "
                   "Path('demo_flight_record.json').write_text('partial record'); "
                   "print('partial stdout'); print('failure stderr', file=sys.stderr); sys.exit(17)"]
        status = self.api['record_step'](self.run, 'demo', self.scratch, command)
        self.assertEqual(status, 17)
        shutil.rmtree(self.scratch)
        self.api['finalize'](ROOT, self.run, status, 0, 1)
        run = json.loads((self.run / 'run.json').read_text())
        self.assertEqual((run['status'], run['exit_code']), ('failed', 17))
        step = run['steps'][0]
        self.assertEqual(step['command'], command)
        self.assertEqual(step['exit_code'], 17)
        self.assertLessEqual(step['started_at'], step['ended_at'])
        self.assertGreater(step['wall_time_s'], 0)
        self.assertEqual(len(step['artifacts']), 2)
        self.assertEqual((self.run / step['stdout']['path']).read_text(), 'partial stdout\n')
        self.assertEqual((self.run / step['stderr']['path']).read_text(), 'failure stderr\n')
        self.assert_refs(step)
        self.assertEqual(run['script_sha256'], hashlib.sha256(SCRIPT.read_bytes()).hexdigest())
        self.assertEqual(run['head_sha'], subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip())
        self.assertEqual(run['git_tree_sha'], subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], cwd=ROOT, text=True).strip())
        self.assertEqual(step['metadata']['sha256'], hashlib.sha256((self.run / step['metadata']['path']).read_bytes()).hexdigest())
        self.assertEqual(run['toolchain']['python']['exit_code'], 0)

    def test_successful_probe_keeps_report_and_distinct_run(self):
        command = [sys.executable, '-c',
                   "from pathlib import Path; Path('probe_results').mkdir(); "
                   "Path('probe_results/report.json').write_text('{\"runs\": []}'); print('probe output')"]
        self.assertEqual(self.api['record_step'](self.run, 'probe', self.scratch, command), 0)
        shutil.rmtree(self.scratch)
        self.api['finalize'](ROOT, self.run, 0, 1, 0)
        before = (self.run / 'run.json').read_bytes()
        other = self.run.parent / 'another-run'
        other.mkdir()
        self.api['initialize'](ROOT, other)
        self.assertEqual((self.run / 'run.json').read_bytes(), before)
        run = json.loads(before)
        self.assertEqual(run['status'], 'passed')
        self.assertEqual(len(run['steps'][0]['artifacts']), 1)
        self.assert_refs(run['steps'][0])

    def test_missing_executable_retains_error_and_nonzero_status(self):
        status = self.api['record_step'](self.run, 'missing', self.scratch, [str(self.scratch / 'absent')])
        self.assertEqual(status, 127)
        step = json.loads((self.run / 'missing/step.json').read_text())
        self.assertEqual(step['exit_code'], 127)
        self.assertIn('No such file', (self.run / step['stderr']['path']).read_text())
        self.assert_refs(step)

    def test_duplicate_step_cannot_overwrite_evidence(self):
        self.api['record_step'](self.run, 'sample', self.scratch, [sys.executable, '-c', "print('original')"])
        before = (self.run / 'sample/step.json').read_bytes()
        with self.assertRaises(FileExistsError):
            self.api['record_step'](self.run, 'sample', self.scratch, [sys.executable, '-c', "print('replacement')"])
        self.assertEqual((self.run / 'sample/step.json').read_bytes(), before)
        self.assertEqual((self.run / 'sample/stdout.txt').read_text(), 'original\n')


if __name__ == '__main__':
    unittest.main()
