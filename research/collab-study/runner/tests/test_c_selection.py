"""Protocol-owner amendment: C participation, writer selection and fallback."""
import json

import pytest

from test_arm_runtime import final, run_arm
from test_emitted_sets import execute
from test_study_runner import ScriptedModel, response, runner


def result(output):
    return json.loads((output / 'job-one/findings.json').read_text())


def test_early_writer_final_waits_for_peers_and_a_new_writer_final(tmp_path):
    emitted, job, model, output = execute(tmp_path, 'C', [
        response('FINAL\n'), response(final('peer two')), response(final('peer three')),
        response(final('still working').replace('FINAL', 'FINDINGS', 1)),
        response('peer two again'), response('peer three again'),
        response(final('first eligible') + '\n' + final('last eligible') + '\nFINDINGS\n'),
    ])
    assert len(model.calls) == 7  # An old FINAL must not stop a later non-FINAL turn.
    assert [row['agent'] for row in emitted] == [1, 2, 3, 1, 1, 1, 1]
    assert [row['elapsed_s'] for row in emitted] == [2, 4, 6, 8, 14, 14, 14]
    assert [row['selected_final'] for row in emitted] == [False, False, False, False, False, True, False]
    assert result(output)['findings'][0]['evidence'] == 'last eligible'
    assert job['selection'] == {'rule': 'last_writer_final_after_peer_turns',
                                'agent': 1, 'set_index': 3, 'kind': 'FINAL'}
    assert job['failed'] is False
    assert job['c_turns'] == {'1': 'response', '2': 'response', '3': 'response'}
    assert job['agents']['1']['stop_reason'] == 'final'
    assert job['agents']['2']['stop_reason'] == job['agents']['3']['stop_reason'] == 'writer_final'


def test_c_first_requests_append_each_prompt_directly_to_packet(tmp_path):
    model = ScriptedModel(response('one'), response('two'), response('three'), response(final('writer')))
    run_arm(tmp_path, 'C', model)
    for number, call in enumerate(model.calls[:3], 1):
        messages = call['messages']
        assert messages[1]['content'].startswith(f'five packet files\n\nsealed instruction for agent {number}')
        assert messages[1]['content'].count(f'sealed instruction for agent {number}') == 1
        assert [message['role'] for message in messages] == ['system', 'user']
        for peer in range(1, number):
            assert f'Agent {peer}:\n' in messages[1]['content']


@pytest.mark.parametrize('ending', ['cap', 'deadline'])
@pytest.mark.parametrize('last_agent', [1, 2, 3])
def test_c_falls_back_to_last_set_from_any_agent(tmp_path, ending, last_agent):
    texts = ['reviewing'] * 3
    texts[0] = final('early writer')
    if last_agent != 1:
        texts[last_agent - 1] = final('last peer').replace('FINAL', 'FINDINGS', 1)
    if ending == 'cap':
        replies = [response(text, prompt=39800, completion=100) for text in texts]
        ticks = 2
    else:
        # Exactly the deadline: retain the late FINAL but never select it.
        replies = [*(response(text) for text in texts), response(final('late writer'))]
        ticks = 225
    emitted, job, model, output = execute(tmp_path, 'C', replies, ticks=ticks)
    assert len(model.calls) == (3 if ending == 'cap' else 4)
    assert job['selection'] == {'rule': 'last_emitted_set', 'agent': last_agent,
                                'set_index': 0, 'kind': 'FINAL' if last_agent == 1 else 'FINDINGS'}
    assert result(output)['findings'][0]['evidence'] == ('early writer' if last_agent == 1 else 'last peer')
    assert job['failed'] is False
    assert emitted[0]['elapsed_s'] == ticks
    assert emitted[0]['selected_final'] is False
    if ending == 'deadline':
        assert emitted[-1]['elapsed_s'] == 900
        assert emitted[-1]['selected_final'] is False
        assert job['history_complete'] is False


@pytest.mark.parametrize('ending', ['cap', 'deadline', 'failure'])
def test_c_no_emitted_set_is_a_failed_run(tmp_path, ending):
    replies = ([runner.CallFailure('transport_unknown') for _ in range(3)] if ending == 'failure'
               else [response('reviewing', prompt=39800 if ending == 'cap' else 100, completion=100)
                     for _ in range(3)])
    emitted, job, _, output = execute(tmp_path, 'C', replies, ticks=300 if ending == 'deadline' else 2)
    assert emitted == []
    assert job['failed'] is True
    assert job['selection'] == {'rule': 'failed_run', 'agent': None, 'set_index': None, 'kind': None}
    assert result(output) == {'findings': [], 'malformed': [], 'discarded': 0}


@pytest.mark.parametrize('stopped_peer', [2, 3])
@pytest.mark.parametrize('stop', ['token_cap', 'transport_unknown'])
def test_c_capped_or_failed_peer_counts_as_having_a_turn(tmp_path, stopped_peer, stop):
    replies = [response('writer analysis')]
    bounds = {1: 100, 2: 100, 3: 100}
    for peer in (2, 3):
        if peer == stopped_peer and stop == 'token_cap':
            bounds[peer] = 40000  # No request is admitted for this peer.
        else:
            replies.append(runner.CallFailure(stop) if peer == stopped_peer else response('peer analysis'))
    replies.append(response(final('writer after peers')))
    model = ScriptedModel(*replies)
    job, findings, accounting = run_arm(tmp_path, 'C', model, bounds=bounds)
    assert job['selection']['rule'] == 'last_writer_final_after_peer_turns'
    assert job['c_turns'][str(stopped_peer)] == stop
    assert job['agents'][str(stopped_peer)]['stop_reason'] == stop
    assert findings['findings'][0]['evidence'] == 'writer after peers'
    assert job['failed'] is False
    assert [row['agent'] for row in accounting['attempts']] == (
        [1, 5 - stopped_peer, 1] if stop == 'token_cap' else [1, 2, 3, 1])


def test_c_explicit_empty_set_can_supply_fallback(tmp_path):
    _, job, _, output = execute(tmp_path, 'C', [
        response('FINAL\n', prompt=39800, completion=100),
        response('reviewing', prompt=39800, completion=100),
        response('reviewing', prompt=39800, completion=100),
    ])
    assert job['selection']['rule'] == 'last_emitted_set'
    assert job['failed'] is False
    assert result(output) == {'findings': [], 'malformed': [], 'discarded': 0}
