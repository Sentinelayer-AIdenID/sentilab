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


@pytest.mark.parametrize('peer_completions', [0, 1, 300])
def test_first_request_uses_sealed_bound_but_keeps_byte_floor_for_dollars(peer_completions):
    clock = FakeClock()
    ledger = runner.Ledger('10', {'input': '1', 'cached_input': '0.5', 'output': '2'})
    agent = runner.AgentState(1, 200, 100)
    agent.prompt_bound += peer_completions
    model = ScriptedModel(response())
    engine = runner.RequestEngine(model, ledger, max_tokens_per_reply=100,
                                  clock=clock, sleep=clock.sleep)
    messages = [{'role': 'user', 'content': 'packet ' * 200}]
    records = []
    reply = engine.request('job-one', agent, messages, deadline=900,
                           scope='study', record=records.append)
    if peer_completions:
        assert reply is None
        assert agent.stop_reason == 'token_cap'
        assert agent.charged_tokens == 0
        assert model.calls == records == ledger.report()['attempts'] == []
        return
    assert reply is not None
    assert agent.charged_tokens == 120
    attempt = ledger.report()['attempts'][0]
    assert attempt['prompt_bound'] == len(runner.canonical(messages))
    assert attempt['usage'] == reply.usage
    assert attempt['charged_tokens'] == 120


@pytest.mark.parametrize('packet_tokens', [24000, 30000])
def test_c_first_requests_include_full_length_peer_replies_in_token_stop(tmp_path, packet_tokens):
    class FourByteProvider:
        def complete(self, messages, *, max_tokens, timeout):
            prompt = 3 + sum(8 + (len(m['content'].encode('utf-8')) + 3) // 4
                             for m in messages)
            return response('r' * (4 * max_tokens), prompt=prompt, completion=max_tokens)

    clock = FakeClock()
    ledger = runner.Ledger('10', {'input': '1', 'cached_input': '0.5', 'output': '2'})
    reply_limit = 8192
    engine = runner.RequestEngine(FourByteProvider(), ledger, max_tokens_per_reply=reply_limit,
                                  clock=clock, sleep=clock.sleep)
    output = tmp_path / 'output'
    runner.claim_output(output)
    runner.run_arm(job_metadata('C'), output=output, engine=engine,
                   system_prompt='sealed system', packet_message='p' * (4 * packet_tokens),
                   continue_prompt='sealed continue',
                   # Covers system, packet and turn prompt, but no peer replies.
                   initial_prompt_bounds={n: packet_tokens + 100 for n in (1, 2, 3)},
                   c_turn_prompts={n: f'sealed turn {n}' for n in (1, 2, 3)})
    job = json.loads((output / 'job-one/job.json').read_text())
    attempts = ledger.report()['attempts']
    for number, agent in job['agents'].items():
        rows = [row for row in attempts if row['agent'] == int(number)]
        assert agent['charged_tokens'] <= agent['cap'] + reply_limit
        assert agent['charged_tokens'] == sum(row['usage']['prompt_tokens'] +
                                              row['usage']['completion_tokens'] for row in rows)
        assert agent['stop_reason'] == 'token_cap'
    assert not job['overspend_limit_exceeded']
    assert [row['agent'] for row in attempts] == [1]
    assert attempts[0]['usage']['completion_tokens'] == reply_limit


@pytest.mark.parametrize('replying_agent', [1, 2, 3])
def test_c_token_stop_includes_replying_agents_own_label(tmp_path, replying_agent):
    # The next request fits exactly if the assistant's "Agent N:\n" label
    # is omitted from its reservation; with the label, the agent must stop.
    model = ScriptedModel(response('r' * 100, prompt=19812, completion=100),
                          response('extra request', prompt=20000, completion=100))
    clock = FakeClock()
    ledger = runner.Ledger('10', {'input': '1', 'cached_input': '0.5', 'output': '2'})
    engine = runner.RequestEngine(model, ledger, max_tokens_per_reply=100,
                                  clock=clock, sleep=clock.sleep)
    output = tmp_path / 'output'
    runner.claim_output(output)
    runner.run_arm(job_metadata('C'), output=output, engine=engine,
                   system_prompt='sealed system', packet_message='packet',
                   continue_prompt='sealed continue',
                   initial_prompt_bounds={n: 19812 if n == replying_agent else 40000
                                          for n in (1, 2, 3)},
                   c_turn_prompts={n: f'sealed turn {n}' for n in (1, 2, 3)})
    job = json.loads((output / 'job-one/job.json').read_text())
    assert len(model.calls) == 1
    assert [row['agent'] for row in ledger.report()['attempts']] == [replying_agent]
    assert job['agents'][str(replying_agent)]['charged_tokens'] == 19912
    assert all(agent['stop_reason'] == 'token_cap' for agent in job['agents'].values())
