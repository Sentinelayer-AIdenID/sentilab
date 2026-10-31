# SentiLab

A hands-off lab for chiplet thermal placement. Labs propose layouts, a deterministic referee (HotSpot 7 + SuperLU)
scores them, an AcceptanceGate accepts or rejects each result, and every step lands in a signed record. The live
page is the running system, not a replay.

## Where things are

- `docs/sentilab/draft-0.5/`: the plan (PLAN.md), requirements, ticket graph (TICKETS.json) and reviews.
- `sundai_hotspot/`: HotSpot 7 (C source, built with SuperLU) and the oracle adapter (`tap_oracle.py`).
- `sundai_tap/`: TAP-2.5D configs, including `sys_ascend910.cfg` (6 chiplets, 350 W) and `sys_micro150.cfg`
  (8 chiplets, 680 W).
- `sundai_controller/`: the placement controller, lanes and flight records.
- `app/`: the API service. `web/`: the live and replay view.
- `PROVENANCE.json`: every imported file, byte-identical to `thermal-flight-lab@2199612`, with its sha256.

## Run the checks

```
python3.12 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
(cd sundai_controller && python -m unittest -v test_controller.py test_experiment.py)
python -m unittest discover -s sundai_thermal -p 'test_*.py'
docker build .   # builds HotSpot with SuperLU and runs scripts/container_smoke.sh
```

Without Docker, build HotSpot with `apt-get install build-essential libsuperlu-dev libblas-dev` and
`(cd sundai_hotspot && make -j4 SUPERLU=1)`.

## Imported results (regression-tested)

These figures come from thermal-flight-lab and are checked to seven decimals by
`sundai_thermal/test_tfl14_regression.py`:

- Independent synthetic search, equal evaluation budget, three-seed mean best objective:
  random 79.9564865°C; local annealing 78.7703960°C; surrogate-screened 79.8820836°C.
  Local annealing beat this surrogate setup. This says nothing about LLM labs.
- TFL-08 on Ascend910 (16x16, 10 seeds): random and the local-policy lane tie for the best median, which is why
  SentiLab gates every LLM lab on a headroom check first (SLAB-039).

## Rules

- Work arrives as SLAB tickets in the SentiLab room; each PR names its ticket.
- No keys, seeds or tokens in the repo. Signing keys never sit on a lab box.
- Held-out cases are never read by a lab or written to memory.

Third-party licenses: `sundai_hotspot/LICENSE`, `sundai_tap/LICENSE`, `THIRD_PARTY_NOTICES.md`.
