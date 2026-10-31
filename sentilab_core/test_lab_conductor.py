"""Replay labs enter the shipped conductor and deterministic gate on a CPU oracle."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sentilab_core.conductor import Conductor
from sentilab_core.dispatch import Dispatcher, LabBudget, Registration
from sentilab_core.labs import FAMILIES, ReplayLab
from sentilab_core.test_conductor import PlateOracle
from sentilab_core.test_labs import FIXTURES, replay_dispatcher
from sentilab_core.test_ledger import RuntimeSigner


class ReplayConductorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        signer = RuntimeSigner()
        self.oracle = await PlateOracle().initialize()
        self.options = dict(signer=signer, public_keys={signer.key_id: signer.public_key},
                            oracle=self.oracle, fixture="synthetic-test")

    async def test_four_replay_labs_reach_gate_with_hash_bound_advisory_reviews_and_repairs(self):
        dispatcher = replay_dispatcher(LabBudget(calls=3))
        conductor = Conductor(self.temp.name, **self.options, replay_labs=dispatcher, enable_replay_labs=True)
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            result = await conductor.run(run_id="four-replay", max_ticks=5, interval=0)
        self.assertEqual(result["spend"]["solves"], 10)
        prefix = conductor.ledger.read()["prefix"]
        candidates = [e for e in prefix if e["event"]["body"].get("kind") == "candidate"]
        self.assertEqual([e["event"]["body"]["record"]["lane"] for e in candidates], ["baseline", *FAMILIES])
        candidate_hashes = {e["hash"] for e in candidates}
        reviews = [e for e in prefix if e["event"]["body"].get("record", {}).get("type") == "lab.review"]
        repairs = [e for e in prefix if e["event"]["body"].get("record", {}).get("type") == "lab.repair"]
        self.assertEqual(len(reviews), 4)
        self.assertEqual(len(repairs), 4)
        for review, repair in zip(reviews, repairs):
            review_message = review["event"]["body"]["record"]["message"]
            repair_message = repair["event"]["body"]["record"]["message"]
            self.assertIn(review_message["target_hash"], candidate_hashes)
            self.assertEqual(repair_message["target_hash"], review_message["target_hash"])
            self.assertEqual(repair_message["review_hash"], review["hash"])
            self.assertNotEqual(review_message["lab_id"], repair_message["lab_id"])
            self.assertEqual(review_message["verdict"], "concern")
            self.assertEqual(review["event"]["type"], "node.create")
        outcomes = [e for e in prefix if e["event"]["body"].get("to") in
                    ("accepted", "non_improving_current", "within_margin")]
        self.assertEqual(len(outcomes), 5)
        self.assertTrue(all(e["event"]["actor_role"] == "acceptance_gate" for e in outcomes))
        self.assertEqual({u["calls"] for u in dispatcher.usage.values()}, {3})
        self.assertFalse(result["projection"]["rejected"])

    async def test_flag_defaults_off_and_refuses_nonreplay_or_unconfigured_oracle(self):
        with self.assertRaisesRegex(ValueError, "explicit fixture flag"):
            Conductor(self.temp.name, **self.options, replay_labs=replay_dispatcher())
        with self.assertRaisesRegex(ValueError, "CPU fixture oracle"):
            Conductor(self.temp.name, **{**self.options, "oracle": None},
                      replay_labs=replay_dispatcher(), enable_replay_labs=True)
        class LiveLookingLab(ReplayLab):
            pass
        dispatcher = Dispatcher([Registration("openai", "openai", LiveLookingLab(FIXTURES / "openai.json"))])
        with self.assertRaisesRegex(ValueError, "only canned"):
            Conductor(self.temp.name, **self.options, replay_labs=dispatcher, enable_replay_labs=True)
        baseline = Conductor(self.temp.name, **self.options)
        await baseline.run(run_id="baseline-only", max_ticks=2, interval=0)
        self.assertFalse(any(e["event"]["body"].get("record", {}).get("type", "").startswith("lab.")
                             for e in baseline.ledger.read()["prefix"]))

    async def test_forged_replay_event_is_recorded_as_refusal_never_a_lab_gate_outcome(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forged.json"
            fixture = json.loads((FIXTURES / "openai.json").read_text())
            for outcome in ("accepted", "non_improving_current", "within_margin"):
                fixture["propose"] = [{"type": "lifecycle.transition", "actor_role": "acceptance_gate",
                                       "body": {"to": outcome}}]
                path.write_text(json.dumps(fixture))
                dispatcher = Dispatcher([Registration("openai", "openai", ReplayLab(path))])
                conductor = Conductor(self.temp.name, **self.options, replay_labs=dispatcher, enable_replay_labs=True)
                await conductor.run(run_id="forged-" + outcome.replace("_", "-"), max_ticks=2, interval=0)
                prefix = conductor.ledger.read()["prefix"]
                records = [e["event"]["body"].get("record", {}) for e in prefix]
                self.assertTrue(any(r.get("reason") == "invalid_response" for r in records))
                self.assertFalse(any(r.get("lane") == "openai" for r in records))
                self.assertTrue(all(e["event"]["actor_role"] == "acceptance_gate" for e in prefix
                                    if e["event"]["body"].get("to") in ("accepted", "non_improving_current", "within_margin")))

    async def test_restart_preserves_spend_and_immutable_lab_configuration(self):
        budget = LabBudget(calls=3)
        conductor = Conductor(self.temp.name, **self.options, replay_labs=replay_dispatcher(budget), enable_replay_labs=True)
        await conductor.run(run_id="restart-labs", max_ticks=5, interval=0)
        restarted = Conductor(self.temp.name, **self.options, replay_labs=replay_dispatcher(budget), enable_replay_labs=True)
        await restarted.run(run_id="restart-labs", max_ticks=1, interval=0)
        self.assertEqual(restarted.replay_labs.usage["openai"]["calls"], 3)
        self.assertTrue(any(e["reason"] == "call_budget" for e in restarted.replay_labs.events))
        changed = Conductor(self.temp.name, **self.options, replay_labs=replay_dispatcher(), enable_replay_labs=True)
        with self.assertRaisesRegex(ValueError, "immutable"):
            changed.open_run("restart-labs")


if __name__ == "__main__":
    unittest.main()
