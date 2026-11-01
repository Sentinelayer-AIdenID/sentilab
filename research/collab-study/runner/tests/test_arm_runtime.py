"""Exercise complete arm loops against the real request engine and output writer."""
import json
import threading

import pytest

from test_study_runner import FakeClock, ScriptedModel, job_metadata, response, runner


def run_arm(tmp_path, arm, model, *, clock=None, max_usd='10', bounds=None):
    clock = clock or FakeClock()
    ledger = runner.Ledger(max_usd, {'input': '1', 'cached_input': '0.5', 'output': '2'})
    engine = runner.RequestEngine(model, ledger, max_tokens_per_reply=100,
                                  clock=clock, sleep=clock.sleep)
    output = tmp_path / 'output'
    runner.claim_output(output)
    runner.run_arm(job_metadata(arm), output=output, engine=engine,
                   system_prompt='sealed system', packet_message='five packet files',
                   continue_prompt='sealed continue',
                   initial_prompt_bounds=bounds or {1: 100, 2: 100, 3: 100},
                   c_turn_prompts={n: f'sealed instruction for agent {n}' for n in (1, 2, 3)})
    runner.finish_run(output, ledger)
    job = json.loads((output / 'job-one/job.json').read_text())
    findings = json.loads((output / 'job-one/findings.json').read_text())
    return job, findings, ledger.report()


def final(evidence):
    return 'FINAL\n' + json.dumps({'file': 'model.py', 'location': '1',
                                   'defect': 'fake defect', 'evidence': evidence})


def test_a_preserves_own_history_and_sealed_continue_until_final(tmp_path):
    model = ScriptedModel(response('private thoughts'), response(final('A result')))
    job, findings, accounting = run_arm(tmp_path, 'A', model)
    assert findings['findings'][0]['evidence'] == 'A result'
    assert job['agents']['1']['cap'] == 120000
    assert job['agents']['1']['charged_tokens'] == 240
    assert job['agents']['1']['stop_reason'] == 'final'
    assert model.calls[0]['messages'] == [
        {'role': 'system', 'content': 'sealed system'},
        {'role': 'user', 'content': 'five packet files'}]
    assert model.calls[1]['messages'] == model.calls[0]['messages'] + [
        {'role': 'assistant', 'content': 'private thoughts'},
        {'role': 'user', 'content': 'sealed continue'}]
    assert accounting['scopes']['study']['attempts'] == 2


def test_b_agents_are_concurrent_and_never_see_another_agents_text(tmp_path):
    class IsolatedModel:
        def __init__(self):
            self.barrier = threading.Barrier(3)
            self.lock = threading.Lock()
            self.conversations = {}

        def complete(self, messages, **kwargs):
            identity = threading.get_ident()
            with self.lock:
                history = self.conversations.setdefault(identity, [])
                history.append(json.loads(json.dumps(messages)))
            if len(history) == 1:
                self.barrier.wait(timeout=5)
                return response(f'private-{identity}')
            return response(final(f'result-{identity}'))

    model = IsolatedModel()
    job, findings, accounting = run_arm(tmp_path, 'B', model)
    assert set(findings) == {'1', '2', '3'}
    assert len({value['findings'][0]['evidence'] for value in findings.values()}) == 3
    assert len(model.conversations) == 3
    for identity, calls in model.conversations.items():
        assert len(calls) == 2
        assert calls[0] == [{'role': 'system', 'content': 'sealed system'},
                            {'role': 'user', 'content': 'five packet files'}]
        assert calls[1][2:] == [{'role': 'assistant', 'content': f'private-{identity}'},
                               {'role': 'user', 'content': 'sealed continue'}]
    assert [agent['cap'] for agent in job['agents'].values()] == [40000] * 3
    assert [agent['charged_tokens'] for agent in job['agents'].values()] == [240] * 3
    assert accounting['scopes']['study']['attempts'] == 6


def test_c_round_robin_shares_every_labelled_reply_and_only_writer_final_ends(tmp_path):
    replies = ['writer analysis', final('nonwriter'), 'third analysis', final('writer')]
    model = ScriptedModel(*(response(text) for text in replies))
    job, findings, accounting = run_arm(tmp_path, 'C', model)
    assert findings['findings'][0]['evidence'] == 'writer'
    assert [row['agent'] for row in accounting['attempts']] == [1, 2, 3, 1]
    assert [agent['charged_tokens'] for agent in job['agents'].values()] == [240, 120, 120]
    for turn, call in enumerate(model.calls):
        assert call['messages'][:2] == [
            {'role': 'system', 'content': 'sealed system'},
            {'role': 'user', 'content': 'five packet files'}]
        assert call['messages'][2:-1] == [
            {'role': 'assistant', 'content': f'Agent {i + 1}:\n{text}'}
            for i, text in enumerate(replies[:turn])]
        assert call['messages'][-1]['content'] == f'sealed instruction for agent {turn % 3 + 1}'


def test_c_skips_exhausted_agents_and_returns_empty_without_writer_final(tmp_path):
    model = ScriptedModel(response('one', prompt=39800, completion=100),
                          response('two'), response('three', prompt=39800, completion=100),
                          response(final('nonwriter'), prompt=39800, completion=100))
    job, findings, accounting = run_arm(tmp_path, 'C', model)
    assert [row['agent'] for row in accounting['attempts']] == [1, 2, 3, 2]
    assert findings == {'findings': [], 'malformed': [], 'discarded': 0}
    assert {agent['stop_reason'] for agent in job['agents'].values()} == {'token_cap'}


@pytest.mark.parametrize('arm', ['A', 'B', 'C'])
def test_arm_checks_global_dollar_cap_before_any_model_call(tmp_path, arm):
    model = ScriptedModel()
    job, findings, accounting = run_arm(tmp_path, arm, model, max_usd='0.00029')
    assert model.calls == []
    assert {agent['stop_reason'] for agent in job['agents'].values()} == {'dollar_cap'}
    assert accounting['stop_reason'] == 'dollar_cap'
    assert accounting['grand_total_usd'] == '0'


def test_arm_deadline_is_fixed_at_fifteen_minutes_and_late_final_is_empty(tmp_path):
    clock = FakeClock()

    class LateModel:
        def complete(self, messages, *, timeout, max_tokens):
            assert timeout == 900
            clock.now = 901
            return response(final('too late'))

    job, findings, accounting = run_arm(tmp_path, 'A', LateModel(), clock=clock)
    assert findings['findings'] == []
    assert job['agents']['1']['stop_reason'] == 'wall_time'
    assert accounting['scopes']['study']['charged_tokens'] == 120


def test_arm_does_not_invent_initial_prompt_bounds(tmp_path):
    with pytest.raises(runner.InputError, match='initial prompt'):
        run_arm(tmp_path, 'B', ScriptedModel(), bounds={1: 100})
    assert not (tmp_path / 'output/job-one').exists()
