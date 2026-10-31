"""SLAB-044: exercise shipped isolation/admission paths with zero model spend."""
from dataclasses import replace
import unittest

from sentilab_core.leads import (
    AdmissionRecord, DeterministicJudge, DeterministicLead, IsolatedLabs,
    LabAdapters, NotAdmitted, OverCap, Readiness, StandInAdmission,
)
from sentilab_core.envelope import canonical
from sentilab_core.labs import FAMILIES


INITIAL = {"width_mm": 10, "height_mm": 10, "gap_mm": 0,
           "chiplets": [{"id": "a", "width_mm": 1, "height_mm": 1, "power_w": 1}],
           "positions": [[1, 1]]}
RUN = {"run_id": "adapter-proof", "arm": "isolated", "family": "fixture", "seed": 11}


def fleet(admission=None, **kwargs):
    return IsolatedLabs([LabAdapters(name, name, DeterministicLead(), DeterministicJudge())
                         for name in FAMILIES], admission=admission or StandInAdmission(), **kwargs)


class LeadTests(unittest.IsolatedAsyncioTestCase):
    async def test_admission_and_meter_cover_both_roles_before_execution(self):
        admission = StandInAdmission()
        labs = fleet(admission)
        records = []
        proposal = await labs.propose("openai", RUN, INITIAL, [], 0, sink=records.append)
        review = await labs.review("openai", RUN, proposal.message, [], "a" * 64, 0, sink=records.append)
        self.assertEqual(len(admission.checks), 2)
        self.assertEqual(admission.charges, [(DeterministicLead.model_id, 0.0),
                                             (DeterministicJudge.model_id, 0.0)])
        self.assertEqual(review.message["verdict"], "abstain")
        self.assertEqual([r["status"] for r in records], ["reserved", "completed"] * 2)
        for result in (proposal, review):
            self.assertEqual(result.provenance["seed"], 11)
            self.assertEqual(len(result.provenance["prompt_hash"]), 64)
            self.assertEqual(result.provenance["originator"], "openai")

    async def test_denied_and_overcap_calls_do_not_execute_or_retry(self):
        class Denied(StandInAdmission):
            def check(self, model_id):
                raise NotAdmitted("not released")
        class Capped(StandInAdmission):
            def meter(self, model_id, usd):
                raise OverCap("exhausted")
        for admission, reason in ((Denied(), "not_admitted"), (Capped(), "over_cap")):
            labs, records = fleet(admission), []
            result = await labs.propose("openai", RUN, INITIAL, [], 0, sink=records.append)
            self.assertIsNone(result.message)
            self.assertEqual(result.reason, reason)
            again = await labs.propose("openai", RUN, INITIAL, records, 0, sink=records.append)
            self.assertIsNone(again.message)
            self.assertEqual(again.reason, "already_attempted")
            self.assertFalse(any(r["status"] == "completed" for r in records))

    async def test_context_memory_and_outputs_are_isolated_and_repeatable(self):
        own = {"node": "own", "lane": "openai", "design": INITIAL, "index": 1}
        foreign = {"node": "foreign", "lane": "claude", "design": {"secret": "other-lab-output"}, "index": 2}
        records = [{"type": "candidate", **own}, {"type": "candidate", **foreign},
                   {"type": "measurement", "candidate_node": "foreign", "j": -900}]
        first = await fleet().propose("openai", RUN, INITIAL, records, 1)
        foreign["design"] = {"secret": "changed-other-lab-output"}
        second = await fleet().propose("openai", RUN, INITIAL, [{"type": "candidate", **own},
                                         {"type": "candidate", **foreign}], 1)
        self.assertEqual(first, second)
        self.assertNotIn(b"other-lab", canonical(first.context))
        self.assertEqual(first.context["memory"], [{"candidate": own, "evidence": []}])
        fresh = await fleet().propose("openai", {**RUN, "run_id": "new-run"}, INITIAL, [], 1)
        self.assertEqual(fresh.context["memory"], [])

    async def test_failure_is_frozen_missing_data_and_reservation_survives_restart(self):
        entries = [LabAdapters("openai", "openai", DeterministicLead(outage=True), DeterministicJudge())]
        labs, records = IsolatedLabs(entries, admission=StandInAdmission()), []
        result = await labs.propose("openai", RUN, INITIAL, [], 0, sink=records.append)
        self.assertEqual(result.reason, "provider_outage")
        self.assertEqual(records[-1]["missing_data_policy"], "record_missing_no_retry")
        restarted = IsolatedLabs(entries, admission=StandInAdmission())
        repeated = await restarted.propose("openai", RUN, INITIAL, records, 0, sink=records.append)
        self.assertEqual(repeated.reason, "already_attempted")
        self.assertEqual(len([r for r in records if r["status"] == "reserved"]), 1)

    async def test_real_adapter_refused_even_with_green_readiness(self):
        class RealLead:
            model_id, version = "provider/model", "pinned-version"
            async def propose(self, context):
                self.fail_if_called = True
                raise AssertionError("real provider must never execute")
        class Permissive(StandInAdmission):
            def check(self, model_id):
                return AdmissionRecord(model_id, "pinned-version", fixture_only=False)
        for readiness in (Readiness(), Readiness(headroom="PASS", frozen=True, freeze_id="fixture-freeze")):
            lead = RealLead()
            labs = IsolatedLabs([LabAdapters("openai", "openai", lead, DeterministicJudge())],
                                admission=Permissive(), readiness=readiness)
            result = await labs.propose("openai", RUN, INITIAL, [], 0)
            self.assertIn(result.reason, ("readiness_hold", "real_calls_disabled"))
            self.assertFalse(hasattr(lead, "fail_if_called"))

    async def test_prompt_and_model_pins_and_call_budget_are_enforced(self):
        labs = fleet(call_limit=1)
        first = await labs.propose("openai", RUN, INITIAL, [], 0)
        exhausted = await labs.propose("openai", RUN, INITIAL, [], 1)
        self.assertEqual(exhausted.reason, "call_budget")
        self.assertEqual(first.provenance["model_id"], DeterministicLead.model_id)
        self.assertEqual(first.provenance["model_version"], DeterministicLead.version)
        class WrongVersion(StandInAdmission):
            def check(self, model_id):
                return AdmissionRecord(model_id, "different-version")
        mismatch = await fleet(WrongVersion()).propose("openai", RUN, INITIAL, [], 0)
        self.assertEqual(mismatch.reason, "pin_mismatch")
        with self.assertRaises(ValueError):
            Readiness(missing_data_policy="retry")
        self.assertNotEqual(fleet().describe(), fleet(call_limit=1).describe())


if __name__ == "__main__":
    unittest.main()
