# Collaboration study runner

`study_runner.py` runs protocol v2 with Amendments 1–5, using Python 3.12 and
`requests`. Packets are UTF-8 text only: the runner never imports or executes
their `model.py`. The tests and example use synthetic packets exclusively.
The operator obtains participant packets through the separate private handoff.

## Input contract

Every input is named on the command line. `order.json` is an array of
`{"job_id":"case-one-A","arm":"A","packet":"case-one","repeat":1}` entries
in execution order. Job IDs are unique, case-insensitive, safe directory names;
the `pilot-` prefix is reserved. Every packet directory contains exactly
`README.md`, `config.json`, `model.py`, `results.json`, and `report.md`.
Live runs require ten packets, all represented in the order. Dry runs may use
fewer. Neither files nor packet directories may be symlinks.

`protocol.example.json` is a **fake fixture**, with fake prices and synthetic
prompt bounds. It is not an approved study protocol. Supply the sealed values:

| Field | Meaning |
| --- | --- |
| `deployment` | Operator's Azure deployment name; the endpoint is also bound by hash in the freeze. |
| `max_tokens_per_reply` | Positive output-token limit on each request. |
| `max_usd` | Global dollar cap, including pilot, study, retries, and unknown charges. |
| `prices_per_million` | Sealed `input`, `cached_input`, and `output` dollar prices. Decimal strings are accepted. |
| `prompt_files` | File basenames for `system`, `continue`, `c1`, `c2`, and `c3`. Each file is separately passed with `--prompt NAME=PATH`. |
| `initial_prompt_tokens` | Explicit initial prompt reservation for each job and agent, e.g. `{"case-one-A":{"1":100}}`. No live default or tokenizer estimate exists. |
| `pilot_arms` | Explicit ordered subset of `A`, `B`, `C`; required when a pilot is requested. No arms are selected implicitly. |

The remaining example fields declare fixed protocol rules. Changing the model,
caps, wall limit, turn order, writer, or finding format is refused. All prompts
are read once before running. The same system prompt is used in every arm.
`prompt.example.txt` is a placeholder only; the operator supplies the approved
prompt files. The runner does not add instructions for emitting interim findings.
The packet message uses headers `### README.md`, `### config.json`, etc., in the
order above. A/B subsequently receive their own reply and the sealed continue
prompt. C receives every prior reply as `Agent N:\n<verbatim reply>`. Each agent's
own replies have the assistant role; peer replies are folded into one user
message with that turn's sealed `c1`, `c2`, or `c3` prompt. Each C agent's first
user message starts with the packet, a blank line, and its sealed turn prompt,
followed by any peer replies. Roles alternate from the first turn onward.
A/B first messages contain only the packet.

The contract does not supply an initial prompt count, pilot selection, or C
participant instructions. This implementation makes those explicit operator
inputs for protocol review; it does not choose their live values. Initial bounds
must be established by the operator before sealing. Every later charged token
count comes from provider usage or an explicitly labelled unknown-cost reserve.

## Freeze and run

For a live pilot before sealing, pass `--pilot-only --pilot-packet PATH`, the
protocol, all five prompt arguments, and an output directory. This mode runs
only `pilot_arms`, writes `ACCOUNTING.json`, and stops. It needs no freeze, order,
or study packets. If both `--order` and `--packets` are supplied, the pilot must
differ from every listed packet. Full study runs retain all freeze, ten-packet,
and pilot-separation checks. The pilot descriptor records `pilot_only: true`.

Set `STUDY_ENDPOINT` to the complete HTTPS chat-completions URL and
`STUDY_API_KEY` through the operator's environment. Neither value is printed;
the credential is never written. No model/provider key is needed for tests or
dry runs. The request fixes model `deepseek-v4-pro`, temperature `0.3`, top-p `1`,
and non-streaming completions. It sends no reasoning-effort field.

From the repository root, with your sealed input paths:

```bash
runner=research/collab-study/runner/study_runner.py
args=(--protocol /operator/protocol.json --order /operator/order.json
      --packets /operator/packets --output /operator/output
      --prompt system=/operator/system.txt --prompt continue=/operator/continue.txt
      --prompt c1=/operator/c1.txt --prompt c2=/operator/c2.txt --prompt c3=/operator/c3.txt
      --parallel 6)
.venv/bin/python "$runner" "${args[@]}" --print-freeze > /operator/freeze.json
# Include that exact JSON in the combined study seal before executing.
.venv/bin/python "$runner" "${args[@]}" --freeze /operator/freeze.json
```

Add `--pilot-packet /operator/pilot-fixture` to **both** commands to run the
explicit `pilot_arms` before study jobs, with the same prompts and dollar ledger.
The pilot is refused if its sorted file-hash digest matches any ordered packet,
even when copied to a different path. Its content hash is also frozen. Changing
prompts after the pilot cannot affect the in-memory study and invalidates a
subsequent run against the same freeze.

The freeze includes runner/protocol/prompt/order SHA-256 values, sorted per-file
packet hashes and tree hash, deployment/model, endpoint hash, request settings,
caps, prices, turn/retry rules, pilot selection and parallelism. A live freeze
cannot be used for a dry run or vice versa. A missing or mismatched freeze is
refused before output creation and model calls. Output must be outside the study
and pilot packet directories. `--print-freeze` only prints the
descriptor; it does not run the study. Output must start empty. No resume or
overwrite mode exists.

## Execution and accounting

A has one 120,000-token agent. B runs three isolated 40,000-token agents
concurrently, with independent findings. C rotates agents 1, 2, 3, skipping
stopped agents; a nonwriter's `FINAL` is recorded and that agent keeps taking
turns. Writer 1's `FINAL` ends the arm only after agents 2 and 3 have each had
a turn; a capped or failed agent also satisfies this participation rule.
An early writer `FINAL` remains timed in the history and rotation continues.
Select the last writer `FINAL` emitted after both peers' participation. If none
arrives before the cap or deadline, select the last emitted fixed-format set
(`FINDINGS` or `FINAL`) from any agent, including an early writer `FINAL`.
With no set, record a failed run. Explicit empty sets still count as sets;
late or failed responses remain in the history but cannot supply the result.
Each arm has one 900-second deadline. Jobs start in order with at most `--parallel` arm workers
(1–6, default 6). B's three internal agents are part of one arm worker.

Before each attempt, the token prompt bound and bounded output must fit the
agent's remaining cap. Its first request uses the sealed `initial_prompt_tokens`
bound plus any peer completion usage already accumulated before its turn. Later
requests use its last provider-reported prompt usage, plus reported
completion tokens for its own and all peer replies appended since that request,
plus the serialized bytes of newly appended framing, labels, separators and
continue/turn prompts. Earlier text is already covered by the reported prompt
usage; reply text uses reported completion tokens, not its byte length.

Dollar reservations separately use the larger of the usage-based bound and the
byte length of the complete ASCII-escaped JSON message list. This conservative
byte floor covers the entire request but never drives token-cap stopping.
Neither bound is a measured token count; charged tokens still come exclusively
from provider usage, except labelled unknown charges. A thread-safe ledger
reserves the maximum dollar cost, including other in-flight calls. If that
would cross the dollar cap, all subsequent calls stop; remaining jobs receive
empty findings and stop receipts. Provider prompt counts can grow beyond the
previous count: any resulting over-reservation, token overspend, or dollar
overshoot is recorded, never hidden as an exact pre-call token measurement.

Cached input and reasoning details are included in raw usage; standard OpenAI
usage reports them as subsets of prompt/completion totals, so they are not added
twice. Cached input uses its sealed price. Reservations use the more expensive
of cached/uncached input. Unknown or partial failed usage charges at least the
whole reservation, or a higher reported cost when available.

Only evidenced DNS failure, connection refusal, or certificate verification
failure before sending can be retried, once before the agent's first success,
after ten seconds and fresh cap/deadline checks. Generic TLS errors, resets,
HTTP errors including 429/5xx, and timeouts are not retried. A wall deadline
also bounds a transport that keeps delivering bytes; its late result cannot
change receipts. An unconfirmed provider request may still finish remotely and
is charged as unknown. Keys echoed by a response are withheld from all outputs.

Each job contains:

* `job.json`: metadata, UTC timestamps, wall duration, per-agent caps/usage,
  request IDs, failures, unknown charges, token overspend, job dollar charges,
  the run's dollar overshoot/stop state as of that job's completion, and
  `history_complete`. That flag is false after a dollar-cap stop, failure, missing/unparsed reply,
  or reply received beyond the deadline, even if a later retry succeeds.
  One monotonic arm start, after output setup and before execution, anchors the
  900-second deadline, `wall_seconds`, and every emitted `elapsed_s`. Each
  agent's `agent_s` sums its request durations; the job's `agent_s` sums all
  agents, so overlapping B requests count separately. Request durations include
  failed attempts but exclude receipt writing, parsing and retry sleep.
  For C, `c_turns` records which agents satisfied participation and how
  (`response`, `token_cap`, or the failure reason). `selection` identifies the
  selected `agent`, `set_index`, `kind`, and rule:
  `last_writer_final_after_peer_turns`, `last_emitted_set`, or `failed_run`.
  `failed` is true when no selectable set exists. Interrupted recovery uses
  `interrupted_run` and retains the existing incomplete-history behavior.
* `transcript.jsonl`: request-message hashes and every reply verbatim, including
  each attempt's scope, raw usage, reservations, `request_s` duration and
  accounting outcome. Durations also persist in `ACCOUNTING.json`.
* `emitted_sets.jsonl`: every set introduced by an exact `FINDINGS` or `FINAL`
  line anywhere in a reply, including C nonwriters' sets and malformed lines.
  Entries contain `job_id`, `arm`, `agent`, `set_index` (per agent, from zero),
  `kind`, `elapsed_s`, `findings`, `malformed`, and `discarded`. Malformed lines
  preserve their text and carry `malformed: true`. Time is taken from the runner's
  monotonic clock after parsing the reply, relative to the common arm start;
  model-written timestamps have no effect. Multiple sets in one reply share its
  parsing-completion time. Interim sets do not stop the agent. Late replies are
  retained for analysis even when they cannot supply the final arm result.
  When a reply has multiple FINALs, all remain recorded. For A/B,
  `selected_final` marks the last FINAL in the reply. For C it marks only the
  last eligible writer FINAL, so early writer and nonwriter FINALs are false;
  a fallback selection is identified by `job.json` instead. Per-agent
  `final_set_index` records the last emitted FINAL, whether selected or not.
* `findings.json`: `{findings, malformed, discarded}` for A/C; a map from agent
  number to that structure for B. No B merging is performed. At most 20 valid
  `{file, location, defect, evidence}` objects are kept. Malformed lines after
  `FINAL` remain recorded without repair. A/B require a final marker; C also
  permits the interim-set fallback described above.

At run level, `FREEZE.json` records the input seal, `ACCOUNTING.json` contains all
attempts and pilot/study/retry totals, and `RUN-MANIFEST.json` hashes every output
file except itself. Include the manifest in the output seal. The runner never
edits sealed results. On Linux, a process lock protects active runs. All records
are published atomically; `ACCOUNTING.json` is checkpointed before each request,
after each settlement, and on every execution exit. JSON escapes preserve lone
surrogates without breaking UTF-8 output. Rerunning an interrupted output with
the same inputs continues its ledger: pending reservations become unknown-cost
charges, completed jobs remain untouched, and interrupted jobs are marked
`interrupted_run` with incomplete histories. Their `wall_seconds` is null,
because monotonic timing cannot span processes. Completed request durations
survive recovery; an interrupted attempt with no duration makes the affected
agent's and arm's `agent_s` null, rather than reporting zero. An agent with no
attempts has zero request time. Only untouched jobs run next;
no interrupted request is replayed. Missing or inconsistent accounting is
refused. Exit 2 means invalid/inaccessible inputs or outputs; exit 0
means a recorded run completed, which can include cap stops or model failures.
The freeze declares `collab-study-output-v5`, binds C's amended selection and
first-turn rules in `turn_rule`, and the manifest hashes emitted-set
histories too. The runner has no correctness key and does not calculate
`first_correct`; analysis uses the histories and completeness flag to distinguish
an unobserved result from a complete history with no correct finding.

## Offline proof

```bash
.venv/bin/python -m pip install pytest requests
.venv/bin/python -m pytest -q research/collab-study/runner/tests
```

This creates two fake packets, runs the actual executable, and checks its hashes:

```bash
.venv/bin/python - <<'PY'
import json, subprocess, sys, tempfile
from pathlib import Path
root = Path('research/collab-study/runner').resolve()
sys.path.insert(0, str(root / 'tests'))
from test_cli import fixture
demo = Path(tempfile.mkdtemp(prefix='collab-study-demo-'))
args, _, _ = fixture(demo)
command = [sys.executable, str(root / 'study_runner.py'), *args]
frozen = subprocess.run(command + ['--print-freeze'], check=True, capture_output=True).stdout
(demo / 'freeze.json').write_bytes(frozen)
subprocess.run(command + ['--freeze', str(demo / 'freeze.json')], check=True)
manifest = json.loads((demo / 'output/RUN-MANIFEST.json').read_text())
import hashlib
assert len(manifest['files']) == 26
for path, digest in manifest['files'].items():
    assert hashlib.sha256((demo / 'output' / path).read_bytes()).hexdigest() == digest
print(demo, '6 jobs; 26 hashed output files')
PY
```

Repository gates are the ticket's Python controller and thermal unit tests and
HotSpot `make -j4 SUPERLU=1`; this repository has no npm/TypeScript gate manifest.
Tests never call a live provider. Live Azure compatibility and the operator's
sealed bounds/prices/prompts require review before the actual study.
