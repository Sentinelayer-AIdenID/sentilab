"""Token-cap utilization must follow provider usage, independently of dollars."""
import json

import pytest

from test_study_runner import FakeClock, ScriptedModel, job_metadata, response, runner


@pytest.mark.parametrize('arm', ['A', 'B', 'C'])
@pytest.mark.parametrize('packet_bytes', [12000, 24000, 52000])
def test_four_byte_provider_uses_most_of_each_agents_cap(tmp_path, arm, packet_bytes):
    class FourByteProvider:
        def complete(self, messages, *, max_tokens, timeout):
            # This synthetic provider owns both counts; the runner must not
            # replace its usage with the much larger serialized byte count.
            prompt = 3 + sum(8 + (len(m['content'].encode('utf-8')) + 3) // 4
                             for m in messages)
            return response('r' * (4 * max_tokens), prompt=prompt, completion=max_tokens)

    clock = FakeClock()
    ledger = runner.Ledger('10', {'input': '1', 'cached_input': '0.5', 'output': '2'})
    reply_limit = 500
    engine = runner.RequestEngine(FourByteProvider(), ledger, max_tokens_per_reply=reply_limit,
                                  clock=clock, sleep=clock.sleep)
    output = tmp_path / 'output'
    runner.claim_output(output)
    runner.run_arm(job_metadata(arm), output=output, engine=engine,
                   system_prompt='sealed system', packet_message='p' * packet_bytes,
                   continue_prompt='sealed continue',
                   initial_prompt_bounds={n: packet_bytes // 4 + 100 for n in (1, 2, 3)},
                   c_turn_prompts={n: f'sealed turn {n}' for n in (1, 2, 3)})
    job = json.loads((output / 'job-one/job.json').read_text())
    attempts = ledger.report()['attempts']
    assert {row['agent'] for row in attempts} == ({1} if arm == 'A' else {1, 2, 3})
    for number, agent in job['agents'].items():
        rows = [row for row in attempts if row['agent'] == int(number)]
        assert agent['stop_reason'] == 'token_cap'
        assert agent['charged_tokens'] == sum(row['usage']['prompt_tokens'] +
                                              row['usage']['completion_tokens'] for row in rows)
        assert 0.65 * agent['cap'] <= agent['charged_tokens'] <= agent['cap'] + reply_limit
    assert not job['overspend_limit_exceeded']


@pytest.mark.parametrize('peer_completions', [0, 300])
def test_first_request_uses_sealed_bound_but_keeps_byte_floor_for_dollars(peer_completions):
    clock = FakeClock()
    ledger = runner.Ledger('10', {'input': '1', 'cached_input': '0.5', 'output': '2'})
    agent = runner.AgentState(1, 200, 100)
    agent.prompt_bound += peer_completions
    engine = runner.RequestEngine(
        ScriptedModel(response()),
        ledger, max_tokens_per_reply=100, clock=clock, sleep=clock.sleep)
    messages = [{'role': 'user', 'content': 'packet ' * 200}]
    records = []
    reply = engine.request('job-one', agent, messages, deadline=900,
                           scope='study', record=records.append)
    assert reply is not None
    assert agent.charged_tokens == 120
    attempt = ledger.report()['attempts'][0]
    assert attempt['prompt_bound'] == len(runner.canonical(messages))
    assert attempt['usage'] == reply.usage
    assert attempt['charged_tokens'] == 120
