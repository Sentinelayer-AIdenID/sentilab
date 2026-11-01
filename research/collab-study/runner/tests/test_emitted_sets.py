"""Amendment 2: complete emitted histories with runner-owned timing."""
import json
import threading

import pytest

from test_arm_runtime import final
from test_study_runner import FakeClock, ScriptedModel, job_metadata, response, runner


def execute(tmp_path, arm, results, *, ticks=2):
    clock = FakeClock()

    class Model(ScriptedModel):
        def complete(self, *args, **kwargs):
            clock.now += ticks
            return super().complete(*args, **kwargs)

    model = Model(*results)
    ledger = runner.Ledger('10', {'input': '1', 'cached_input': '0.5', 'output': '2'})
    engine = runner.RequestEngine(model, ledger, max_tokens_per_reply=100, clock=clock, sleep=clock.sleep)
    output = tmp_path / 'output'
    runner.claim_output(output)
    writer = runner.JobOutputs(output, job_metadata(arm), clock=clock)
    clock.now = 10  # Receipt creation is not the first request's origin.
    runner.run_arm(job_metadata(arm), output=output, writer=writer, engine=engine,
                   system_prompt='sealed system', packet_message='fake packet', continue_prompt='sealed continue',
                   initial_prompt_bounds={1: 100, 2: 100, 3: 100},
                   c_turn_prompts={n: f'sealed c{n}' for n in (1, 2, 3)})
    runner.finish_run(output, ledger)
    emitted = [json.loads(line) for line in (output / 'job-one/emitted_sets.jsonl').read_text().splitlines()]
    job = json.loads((output / 'job-one/job.json').read_text())
    return emitted, job, model, output


def test_interim_sets_have_strictly_increasing_runner_times_and_final_is_last(tmp_path):
    emitted, job, model, output = execute(tmp_path, 'A', [
        response('model timestamp: -9000\n' + final('first').replace('FINAL', 'FINDINGS', 1)),
        response(final('second').replace('FINAL', 'FINDINGS', 1)),
        response(final('last')),
    ])
    assert [item['kind'] for item in emitted] == ['FINDINGS', 'FINDINGS', 'FINAL']
    assert [item['set_index'] for item in emitted] == [0, 1, 2]
    assert [item['elapsed_s'] for item in emitted] == [2, 4, 6]
    assert all(item['job_id'] == 'job-one' and item['arm'] == 'A' and item['agent'] == 1 for item in emitted)
    assert [item['findings'][0]['evidence'] for item in emitted] == ['first', 'second', 'last']
    assert len(model.calls) == 3
    assert job['history_complete'] is True
    manifest = json.loads((output / 'RUN-MANIFEST.json').read_text())
    assert manifest['files']['job-one/emitted_sets.jsonl'] == runner.sha256((output / 'job-one/emitted_sets.jsonl').read_bytes())


def test_mid_arm_failure_marks_history_incomplete_without_losing_interim_set(tmp_path):
    emitted, job, model, _ = execute(tmp_path, 'A', [
        response(final('interim').replace('FINAL', 'FINDINGS', 1)),
        runner.CallFailure('transport_unknown'),
    ])
    assert len(emitted) == 1
    assert emitted[0]['kind'] == 'FINDINGS'
    assert emitted[0]['findings'][0]['evidence'] == 'interim'
    assert job['history_complete'] is False
    assert job['unknown_usage'] is True
    assert len(model.calls) == 2


def test_c_keeps_nonwriter_sets_and_malformed_lines_under_their_own_agents(tmp_path):
    emitted, job, model, _ = execute(tmp_path, 'C', [
        response(final('one').replace('FINAL', 'FINDINGS', 1)),
        response(final('two').replace('FINAL', 'FINDINGS', 1)),
        response(final('three').replace('FINAL', 'FINDINGS', 1) + '\n{"broken":'),
        response(final('writer')),
    ])
    assert [item['agent'] for item in emitted] == [1, 2, 3, 1]
    assert [item['set_index'] for item in emitted] == [0, 0, 0, 1]
    assert emitted[2]['malformed'] == [{'line': 2, 'text': '{"broken":', 'malformed': True}]
    assert emitted[-1]['kind'] == 'FINAL'
    assert job['history_complete'] is True
    assert len(model.calls) == 4


def test_multiple_exact_markers_in_one_reply_are_all_kept_and_final_ends_agent(tmp_path):
    text = 'preamble\n' + final('interim').replace('FINAL', 'FINDINGS', 1) + '\n' + final('finished')
    emitted, job, model, output = execute(tmp_path, 'A', [response(text)])
    assert [item['kind'] for item in emitted] == ['FINDINGS', 'FINAL']
    assert [item['set_index'] for item in emitted] == [0, 1]
    assert [item['elapsed_s'] for item in emitted] == [2, 2]
    assert job['agents']['1']['stop_reason'] == 'final'
    assert len(model.calls) == 1
    assert json.loads((output / 'job-one/findings.json').read_text())['findings'][0]['evidence'] == 'finished'


def test_c_nonwriter_final_keeps_taking_turns_until_writer_ends_arm(tmp_path):
    interim = final('working').replace('FINAL', 'FINDINGS', 1)
    emitted, job, model, _ = execute(tmp_path, 'C', [
        response(interim), response(final('two finished')), response(interim),
        response(interim), response(interim), response(final('three finished')), response(final('writer finished')),
    ])
    assert [item['agent'] for item in emitted] == [1, 2, 3, 1, 2, 3, 1]
    for agent in (1, 2, 3):
        rows = [item for item in emitted if item['agent'] == agent]
        assert rows[-1]['kind'] == ('FINDINGS' if agent == 2 else 'FINAL')
        assert [row['set_index'] for row in rows] == list(range(len(rows)))
    assert len(model.calls) == 7
    assert job['agents']['2']['stop_reason'] == 'writer_final'
    assert job['agents']['2']['charged_tokens'] == 240
    assert job['history_complete'] is True


def test_late_reply_is_retained_but_history_is_incomplete_and_final_set_empty(tmp_path):
    emitted, job, _, output = execute(tmp_path, 'A', [response(final('late'))], ticks=901)
    assert emitted[0]['elapsed_s'] == 901
    assert emitted[0]['kind'] == 'FINAL'
    assert job['history_complete'] is False
    assert json.loads((output / 'job-one/findings.json').read_text())['findings'] == []


def test_only_exact_marker_lines_emit_sets():
    assert runner.parse_emitted_sets('FINDINGS \n{}\nFINALsuffix\n{}') == []


def test_presend_retry_keeps_first_attempt_time_and_marks_history_incomplete(tmp_path):
    emitted, job, model, _ = execute(tmp_path, 'A', [
        runner.CallFailure('presend_failure', safe_to_retry=True), response(final('after retry')),
    ])
    assert emitted[0]['elapsed_s'] == 14
    assert job['history_complete'] is False
    assert len(model.calls) == 2


def test_blank_malformed_lines_are_preserved_between_markers():
    sets = runner.parse_emitted_sets('FINDINGS\n\nFINAL\n')
    assert sets[0]['malformed'] == [{'line': 1, 'text': ''}]
    assert sets[1]['malformed'] == []


def test_unicode_line_separators_stay_inside_one_finding_line(tmp_path):
    finding = {'file': 'model.py', 'location': '1', 'defect': 'alpha\u2028beta', 'evidence': 'left\u2029right'}
    text = 'FINAL\r\n' + json.dumps(finding, ensure_ascii=False) + '\r\n'
    parsed = runner.parse_final(text)
    assert parsed['findings'] == [finding]
    assert parsed['malformed'] == []
    emitted, _, _, output = execute(tmp_path, 'A', [response(text)])
    assert emitted[0]['findings'] == [finding]
    assert emitted[0]['malformed'] == []
    assert len((output / 'job-one/emitted_sets.jsonl').read_text().splitlines()) == 1


def test_every_final_in_one_reply_is_recorded_and_last_is_explicitly_selected(tmp_path):
    text = final('first candidate') + '\n' + final('last candidate')
    emitted, job, model, output = execute(tmp_path, 'A', [response(text)])
    assert [row['findings'][0]['evidence'] for row in emitted] == ['first candidate', 'last candidate']
    assert [row['selected_final'] for row in emitted] == [False, True]
    assert job['agents']['1']['final_set_index'] == 1
    assert json.loads((output / 'job-one/findings.json').read_text())['findings'][0]['evidence'] == 'last candidate'
    assert len(model.calls) == 1


@pytest.mark.parametrize('arm', ['A', 'B', 'C'])
def test_setup_delay_uses_one_arm_clock_and_records_summed_request_times(tmp_path, arm):
    clock = FakeClock()
    output = tmp_path / 'output'
    runner.claim_output(output)
    writer = runner.JobOutputs(output, job_metadata(arm), clock=clock)
    clock.now = 100  # Output allocation/setup must not shift only wall_seconds.
    barrier = threading.Barrier(3) if arm == 'B' else None

    class Model:
        calls = 0

        def complete(self, messages, *, max_tokens, timeout):
            self.calls += 1
            assert timeout == 900 - (7 * (self.calls - 1) if arm == 'C' else 0)
            if barrier:
                # All three requests overlap for seven seconds in arm B.
                barrier.wait(timeout=5)
                clock.now = 107
                barrier.wait(timeout=5)
            else:
                clock.now += 7
            return response(final('finished') if arm != 'C' or self.calls == 4
                            else final('interim').replace('FINAL', 'FINDINGS', 1))

    ledger = runner.Ledger('10', {'input': '1', 'cached_input': '0.5', 'output': '2'})
    engine = runner.RequestEngine(Model(), ledger, max_tokens_per_reply=100, clock=clock)
    runner.run_arm(job_metadata(arm), output=output, writer=writer, engine=engine,
                   system_prompt='system', packet_message='packet', continue_prompt='continue',
                   initial_prompt_bounds={n: 100 for n in (1, 2, 3)},
                   c_turn_prompts={n: f'turn {n}' for n in (1, 2, 3)})
    job = json.loads((output / 'job-one/job.json').read_text())
    emitted = [json.loads(line) for line in (output / 'job-one/emitted_sets.jsonl').read_text().splitlines()]
    expected_agent_s = {'A': [7], 'B': [7, 7, 7], 'C': [14, 7, 7]}[arm]
    assert job['wall_seconds'] == max(row['elapsed_s'] for row in emitted) == (28 if arm == 'C' else 7)
    assert [agent['agent_s'] for agent in job['agents'].values()] == expected_agent_s
    assert job['agent_s'] == sum(expected_agent_s)
    assert all(row['request_s'] == 7 for row in ledger.report()['attempts'])


@pytest.mark.parametrize('retry', [False, True])
def test_request_time_sums_failed_attempts_but_excludes_retry_sleep(tmp_path, retry):
    emitted, job, _, output = execute(tmp_path, 'A', [
        runner.CallFailure('presend_failure' if retry else 'timeout_unknown', safe_to_retry=retry),
        response(final('after retry')),
    ], ticks=7)
    assert job['agents']['1']['agent_s'] == job['agent_s'] == (14 if retry else 7)
    assert job['wall_seconds'] == (24 if retry else 7)
    if retry:
        assert emitted[0]['elapsed_s'] == 24
    else:
        assert emitted == []
    attempts = json.loads((output / 'ACCOUNTING.json').read_text())['attempts']
    assert [row['request_s'] for row in attempts] == ([7, 7] if retry else [7])
