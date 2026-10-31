"""Four isolated labs through the real conductor, ledger and AcceptanceGate."""
import json
import tempfile
import unittest
from unittest.mock import patch

from sentilab_core.conductor import Conductor
from sentilab_core.envelope import digest
from sentilab_core.labs import FAMILIES
from sentilab_core.leads import DeterministicJudge, DeterministicLead, IsolatedLabs, LabAdapters, StandInAdmission
from sentilab_core.test_conductor import PlateOracle
from sentilab_core.test_ledger import RuntimeSigner


def fleet(*, verdict=None, outage=False, admission=None):
    return IsolatedLabs([LabAdapters(name, name, DeterministicLead(outage=outage and name == "openai"),
                                     DeterministicJudge(verdict=verdict)) for name in FAMILIES],
                        admission=admission or StandInAdmission())


class LeadConductorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        signer = RuntimeSigner()
        self.oracle = await PlateOracle().initialize()
        self.options = dict(signer=signer, public_keys={signer.key_id: signer.public_key},
                            oracle=self.oracle, fixture="synthetic-test")

    def conductor(self, labs, root=None):
        return Conductor(root or self.temp.name, **self.options, isolated_labs=labs)

    @staticmethod
    def records(conductor):
        return [e["event"]["body"].get("record", {}) for e in conductor.ledger.read()["prefix"]]

    async def test_four_labs_two_rounds_have_only_own_memory_and_zero_model_spend(self):
        admission = StandInAdmission()
        labs = fleet(admission=admission)
        conductor = self.conductor(labs)
        lead_inputs, judge_inputs = [], []
        propose, review = DeterministicLead.propose, DeterministicJudge.review

        async def observe_lead(lead, context):
            lead_inputs.append(json.loads(context.data))
            return await propose(lead, context)

        async def observe_judge(judge, candidate, evidence):
            judge_inputs.append((json.loads(candidate), json.loads(evidence)))
            return await review(judge, candidate, evidence)

        with patch.object(DeterministicLead, "propose", observe_lead), \
                patch.object(DeterministicJudge, "review", observe_judge), \
                patch("socket.socket", side_effect=AssertionError("network forbidden")):
            result = await conductor.run(run_id="isolated-proof", max_ticks=9, interval=0)
        records = self.records(conductor)
        proposals = [r for r in records if r.get("operator") == "stand-in-lead"]
        self.assertEqual([r["lane"] for r in proposals], list(FAMILIES) * 2)
        reviews = [r for r in records if r.get("type") == "lab.review"]
        self.assertEqual(len(reviews), 8)
        self.assertEqual(len(admission.checks), 16)
        self.assertEqual(len(admission.charges), 16)
        self.assertEqual(sum(usd for _, usd in admission.charges), 0)
        self.assertEqual(result["spend"]["solves"], 18)  # synthetic regression oracle, no experiment
        self.assertEqual(len(lead_inputs), 8)
        self.assertEqual(len(judge_inputs), 8)
        for index, (context, proposal, (candidate, advice)) in enumerate(zip(lead_inputs, proposals, judge_inputs)):
            self.assertEqual(context["scope"]["lab_id"], proposal["lane"])
            self.assertEqual(len(context["memory"]), index // 4)
            self.assertTrue(all(m["candidate"]["lane"] == proposal["lane"] for m in context["memory"]))
            self.assertEqual(proposal["originator"]["context_hash"], digest(context))
            self.assertEqual(set(context), {"scope", "ordinal", "initial", "memory", "prompt"})
            self.assertEqual(candidate, proposal["design"])
            self.assertEqual(advice["scope"]["lab_id"], proposal["lane"])
            self.assertEqual(len(advice["evidence"]), 2)
            self.assertTrue(all(e["candidate_node"] == proposal["node"] for e in advice["evidence"]))
        flattened = conductor._isolated_records()
        for lab_id in FAMILIES:
            call = await fleet().propose(lab_id, conductor.meta["run"], conductor.config["initial"], flattened, 2)
            memory = call.context["memory"]
            self.assertEqual(len(memory), 2)
            self.assertEqual({m["candidate"]["lane"] for m in memory}, {lab_id})
            self.assertTrue(all(e["candidate_node"] == m["candidate"]["node"]
                                for m in memory for e in m["evidence"]))
            self.assertTrue(all(len(m["evidence"]) == 2 for m in memory))
        for proposal in proposals:
            origin = proposal["originator"]
            self.assertEqual(origin["originator"], proposal["lane"])
            self.assertEqual(origin["model_id"], DeterministicLead.model_id)
            self.assertEqual(origin["seed"], conductor.config["seed"])
            self.assertEqual(len(origin["context_hash"]), 64)
        self.assertFalse(result["projection"]["rejected"])

    async def test_changing_judge_verdict_cannot_change_gate_outcomes(self):
        outcomes = []
        for verdict in ("concern", "no_concern", "abstain"):
            with tempfile.TemporaryDirectory() as root:
                conductor = self.conductor(fleet(verdict=verdict), root)
                await conductor.run(run_id="same-inputs", max_ticks=5, interval=0)
                records = self.records(conductor)
                self.assertEqual({r["message"]["verdict"] for r in records if r.get("type") == "lab.review"}, {verdict})
                transitions = [e["event"] for e in conductor.ledger.read()["prefix"]
                               if e["event"]["body"].get("to") in ("accepted", "within_margin", "non_improving_current")]
                self.assertEqual(len(transitions), 5)
                self.assertEqual({e["actor_role"] for e in transitions}, {"acceptance_gate"})
                outcomes.append([(e["body"]["node"], e["body"]["to"]) for e in transitions])
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(outcomes[1], outcomes[2])

    async def test_outage_consumes_slot_without_fallback_solve_or_retry(self):
        labs = fleet(outage=True)
        conductor = self.conductor(labs)
        result = await conductor.run(run_id="outage-proof", max_ticks=5, interval=0)
        records = self.records(conductor)
        failed = [r for r in records if r.get("lane") == "openai"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["missing"], "provider_outage")
        self.assertEqual(result["spend"]["solves"], 8)
        self.assertEqual([r["lane"] for r in records if r.get("operator") == "stand-in-lead"], list(FAMILIES))
        self.assertEqual(len([r for r in records if r.get("type") == "lab.adapter_call"
                              and r["scope"]["lab_id"] == "openai" and r["status"] == "reserved"]), 1)
        self.assertEqual(result["projection"]["nodes"][failed[0]["node"]]["lifecycle"], "cancelled")
        transition = next(e["event"]["body"] for e in conductor.ledger.read()["prefix"]
                          if e["event"]["type"] == "lifecycle.transition"
                          and e["event"]["body"]["node"] == failed[0]["node"])
        self.assertEqual(transition["record"]["outcome"], "inconclusive")

    async def test_restart_pins_config_and_never_retries_an_interrupted_call(self):
        conductor = self.conductor(fleet())
        conductor.open_run("interrupted-proof")
        await conductor.tick()  # baseline
        await conductor._isolated_propose(1)  # model result recorded, no candidate yet
        restarted = self.conductor(fleet())
        result = await restarted.run(run_id="interrupted-proof", max_ticks=1, interval=0)
        self.assertEqual(result["spend"]["solves"], 2)
        records = self.records(restarted)
        self.assertTrue(any(r.get("missing") == "already_attempted" for r in records))
        self.assertEqual(len([r for r in records if r.get("type") == "lab.adapter_call" and r["status"] == "reserved"]), 1)
        changed = self.conductor(fleet(verdict="concern"))
        with self.assertRaisesRegex(ValueError, "immutable"):
            changed.open_run("interrupted-proof")
        next_run = self.conductor(fleet())
        next_run.open_run("new-proof")
        context = await next_run.isolated_labs.propose("openai", next_run.meta["run"], next_run.config["initial"],
                                                      next_run._isolated_records(), 0)
        self.assertEqual(context.context["memory"], [])

    async def test_real_oracle_and_provider_subclasses_remain_disabled(self):
        with self.assertRaisesRegex(ValueError, "CPU fixture oracle"):
            Conductor(self.temp.name, **{**self.options, "oracle": None}, isolated_labs=fleet())
        class LiveLead(DeterministicLead):
            pass
        labs = IsolatedLabs([LabAdapters("openai", "openai", LiveLead(), DeterministicJudge())], admission=StandInAdmission())
        with self.assertRaisesRegex(ValueError, "only deterministic"):
            self.conductor(labs)


if __name__ == "__main__":
    unittest.main()
