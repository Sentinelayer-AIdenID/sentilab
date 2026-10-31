"""Exercise admission and durable accounting using synthetic, non-secret records."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

from sentilab_core import admission


def registry_record(model_id="fixture-model", arm_id="arm-a", **changes):
    now = datetime.now(timezone.utc)
    row = dict(provider="fixture-provider", model_id=model_id, model_version="fixture-version",
               roles=["lead", "judge"], run_id="fixture-run", arm_id=arm_id,
               payer="fixture-payer", input_usd_per_million="1", output_usd_per_million="2",
               arm_cap_usd="1", run_cap_usd="2", entitlement_source="fixture-entitlement",
               approver="Carter", approval_ref="fixture-approval",
               approved_at=now.isoformat(), expires_at=(now + timedelta(days=1)).isoformat(),
               probe=dict(provider="fixture-provider", entitlement_source="fixture-entitlement",
                          checked_at=now.isoformat(), status_code=200, models=[model_id]))
    return {**row, **changes}


def write_registry(path, rows):
    path.write_text(json.dumps(dict(schema_version=1, records=rows)), encoding="utf-8")


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.registry = self.root / "registry.json"
        write_registry(self.registry, [registry_record()])

    def gate(self, arm="arm-a"):
        return admission.Admission(self.registry, run_id="fixture-run", arm_id=arm,
                                   spend_path=self.root / "spend.json")

    def test_empty_default_and_unbound_interface_refuse(self):
        for model in ("fixture-model", "deepseek-v4-pro", ""):
            with self.subTest(model=model), self.assertRaises(admission.NotAdmitted):
                admission.check(model)
        write_registry(self.registry, [])
        with self.assertRaises(admission.NotAdmitted):
            self.gate().check("fixture-model")

    def test_complete_record_and_scoped_interface(self):
        gate = self.gate()
        with admission.bind(gate):
            record = admission.check("fixture-model")
            self.assertIsInstance(record, admission.AdmissionRecord)
            self.assertEqual(record.provider, "fixture-provider")
            self.assertEqual(record.ceiling_usd(100, 50), Decimal("0.0002"))
            admission.meter("fixture-model", Decimal("1"))
            with self.assertRaises(admission.OverCap):
                admission.meter("fixture-model", "0.000001")
        with self.assertRaises(admission.NotAdmitted):
            admission.meter("fixture-model", 0)

    def test_incomplete_malformed_and_unproven_records_refuse(self):
        row = registry_record()
        variants = [{k: v for k, v in row.items() if k != missing} for missing in row]
        variants += [{**row, **change} for change in (
            {"roles": []}, {"approver": "agent"}, {"payer": " "},
            {"input_usd_per_million": "NaN"}, {"arm_cap_usd": "-1"},
            {"arm_cap_usd": True}, {"expires_at": "yesterday"},
            {"expires_at": "2000-01-01T00:00:00Z"},
            {"approved_at": "2999-01-01T00:00:00Z"},
            {"credential_value": "forbidden-fixture"})]
        for change in ({"status_code": 401}, {"models": []}, {"provider": "wrong-provider"},
                       {"entitlement_source": "wrong-entitlement"},
                       {"checked_at": "2999-01-01T00:00:00Z"}):
            variants.append({**row, "probe": {**row["probe"], **change}})
        for variant in variants:
            with self.subTest(variant=variant):
                write_registry(self.registry, [variant])
                with self.assertRaises(admission.NotAdmitted):
                    self.gate().check("fixture-model")
        self.registry.write_text('{"schema_version":1,"records":[],"records":[]}')
        with self.assertRaises(admission.NotAdmitted):
            self.gate().check("fixture-model")

    def test_scope_conflicts_duplicates_and_revocation_refuse(self):
        row = registry_record()
        for rows in ([row, row], [row, registry_record("second", run_cap_usd="3")],
                     [row, registry_record("second", arm_cap_usd="0.5")],
                     [row, registry_record("second", payer="different-payer")]):
            write_registry(self.registry, rows)
            with self.assertRaises(admission.NotAdmitted):
                self.gate().check("fixture-model")
        write_registry(self.registry, [row])
        gate = self.gate()
        with self.assertRaises(admission.NotAdmitted):
            self.gate("wrong-arm").check("fixture-model")
        gate.check("fixture-model")
        write_registry(self.registry, [])
        with self.assertRaises(admission.NotAdmitted):
            gate.meter("fixture-model", 0)

    def test_arm_and_run_caps_aggregate_across_models_and_restart(self):
        write_registry(self.registry, [registry_record(), registry_record("second"),
                                      registry_record("third", "arm-b", arm_cap_usd="2")])
        self.gate().meter("fixture-model", "0.6")
        self.gate().meter("second", "0.4")
        with self.assertRaises(admission.OverCap):
            self.gate().meter("second", "0.000001")
        other = self.gate("arm-b")
        other.meter("third", 1)
        with self.assertRaises(admission.OverCap):
            other.meter("third", "0.000001")

    def test_invalid_spend_and_corrupt_ledger_never_refund(self):
        gate = self.gate()
        for value in (-1, True, float("nan"), float("inf"), "-0.1", None, "1e-9"):
            with self.subTest(value=value), self.assertRaises(admission.OverCap):
                gate.meter("fixture-model", value)
        gate.meter("fixture-model", "0.9")
        self.assertEqual(gate.spent(), {"arm_usd": "0.9", "run_usd": "0.9"})
        (self.root / "spend.json").write_text('{}')
        with self.assertRaises(admission.OverCap):
            gate.meter("fixture-model", "0.1")
        with self.assertRaises(admission.OverCap):
            self.gate().meter("fixture-model", "0.1")

    def test_concurrent_reservations_cannot_overspend(self):
        gates = [self.gate() for _ in range(8)]
        def reserve(gate):
            try:
                gate.meter("fixture-model", "0.3")
                return True
            except admission.OverCap:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(reserve, gates)), 3)
        self.assertEqual(self.gate().spent()["arm_usd"], "0.9")


if __name__ == "__main__":
    unittest.main()
