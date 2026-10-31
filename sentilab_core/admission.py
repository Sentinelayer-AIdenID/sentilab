"""Human-reviewed admission and durable cost reservations before model transport.

Registry and ledger paths are service-owned configuration, never lab input.
There is deliberately no API to approve a model or to provision credentials.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator, FormatChecker

from .ledger import atomic_json, lock

DIRECTORY = Path(__file__).resolve().parents[1] / "docs/sentilab/admission"
DEFAULT_REGISTRY = DIRECTORY / "registry.json"
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}")
_ACTIVE = ContextVar("model_admission", default=None)


class NotAdmitted(ValueError):
    """Missing, incomplete, expired, wrong-scope or unproven admission."""


class OverCap(ValueError):
    """Invalid cost, exhausted cap or unavailable accounting state."""


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _read(path, limit=1024 * 1024):
    with Path(path).open("rb") as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("oversize admission data")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite number")))


def _identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError("invalid admission identifier")
    return value


def public_name(value):
    """Only non-secret identifiers belong in admission/probe artifacts."""
    _identifier(value)
    if re.search(r"(?i)(?:^|/)(?:sk[-_]|gh[pousr]_|xox[baprs]-|AKIA|eyJ)", value):
        raise ValueError("credential-like identifier")
    return value


def _usd(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise OverCap("invalid USD amount")
    try:
        text = value if isinstance(value, str) else format(Decimal(str(value)), "f")
        if not re.fullmatch(r"(0|[1-9][0-9]{0,11})(\.[0-9]{1,12})?", text):
            raise OverCap("invalid USD amount")
        return Decimal(text)
    except (InvalidOperation, ValueError):
        raise OverCap("invalid USD amount") from None


def _money(value):
    return format(value, "f").rstrip("0").rstrip(".") if value % 1 else str(int(value))


def _time(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timezone required")
    return result


@lru_cache(maxsize=1)
def schema():
    value = _read(DIRECTORY / "MODEL-ADMISSION.schema.json")
    Draft202012Validator.check_schema(value)
    return value


@dataclass(frozen=True)
class AdmissionRecord:
    provider: str
    model_id: str
    model_version: str
    roles: tuple[str, ...]
    run_id: str
    arm_id: str
    payer: str
    entitlement_source: str
    approver: str
    approval_ref: str
    approved_at: str
    expires_at: str
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    arm_cap_usd: Decimal
    run_cap_usd: Decimal
    probe_checked_at: str

    def ceiling_usd(self, input_tokens, output_tokens):
        for value in (input_tokens, output_tokens):
            if type(value) is not int or not 0 <= value <= 1000000000:
                raise OverCap("invalid token ceiling")
        return (input_tokens * self.input_usd_per_million +
                output_tokens * self.output_usd_per_million) / Decimal(1000000)


def _records(path):
    try:
        data = _read(path)
        Draft202012Validator(schema(), format_checker=FormatChecker()).validate(data)
        rows, seen, runs, arms = [], set(), {}, {}
        now = datetime.now(timezone.utc)
        for raw in data["records"]:
            row = dict(raw)
            probe = row.pop("probe")
            for field in ("provider", "model_id", "model_version", "run_id", "arm_id",
                          "payer", "entitlement_source", "approval_ref"):
                public_name(row[field])
            for value in (probe["provider"], probe["entitlement_source"], *probe["models"]):
                public_name(value)
            if not (_time(probe["checked_at"]) <= _time(row["approved_at"]) <= now < _time(row["expires_at"])):
                raise ValueError("admission dates invalid")
            if (probe["status_code"] != 200 or row["model_id"] not in probe["models"] or
                    probe["provider"] != row["provider"] or
                    probe["entitlement_source"] != row["entitlement_source"]):
                raise ValueError("entitlement not proven")
            for field in ("input_usd_per_million", "output_usd_per_million", "arm_cap_usd", "run_cap_usd"):
                row[field] = _usd(row[field])
            key = (row["run_id"], row["arm_id"], row["model_id"])
            if key in seen:
                raise ValueError("ambiguous model admission")
            seen.add(key)
            run = (row["payer"], row["run_cap_usd"])
            arm = row["arm_cap_usd"]
            if runs.setdefault(key[0], run) != run or arms.setdefault(key[:2], arm) != arm:
                raise ValueError("inconsistent shared cap or payer")
            if arm > row["run_cap_usd"]:
                raise ValueError("arm cap exceeds run cap")
            row["roles"] = tuple(row["roles"])
            rows.append(AdmissionRecord(**row, probe_checked_at=probe["checked_at"]))
        return rows
    except Exception:
        # Validation errors can embed input values: never surface their content.
        raise NotAdmitted("invalid or unavailable admission registry") from None


class Admission:
    """Bind the agreed check/meter interface to a trusted run, arm and ledger.

    All arms/processes of a run must use the SAME durable spend_path. Never
    delete it to restart a run. Reservations charge full ceilings, without refund.
    """
    def __init__(self, registry_path=DEFAULT_REGISTRY, *, run_id, arm_id, spend_path):
        self.registry_path = Path(registry_path)
        self.run_id, self.arm_id = _identifier(run_id), _identifier(arm_id)
        self.spend_path = Path(spend_path)
        self.lock_path = self.spend_path.with_name(self.spend_path.name + ".lock")
        self.spend_path.parent.mkdir(parents=True, exist_ok=True)
        with lock(self.lock_path):
            if not self.spend_path.exists():
                atomic_json(self.spend_path, {"schema_version": 1, "reservations": []})

    def check(self, model_id):
        try:
            _identifier(model_id)
        except ValueError:
            raise NotAdmitted("invalid model id") from None
        rows = _records(self.registry_path)
        for row in rows:
            if (row.run_id, row.arm_id, row.model_id) == (self.run_id, self.arm_id, model_id):
                return row
        raise NotAdmitted("model is not admitted for this run and arm")

    def _ledger(self):
        try:
            state = _read(self.spend_path, 8 * 1024 * 1024)
            if (not isinstance(state, dict) or set(state) != {"schema_version", "reservations"} or
                    type(state["schema_version"]) is not int or state["schema_version"] != 1 or
                    not isinstance(state["reservations"], list)):
                raise ValueError("invalid accounting state")
            for row in state["reservations"]:
                if not isinstance(row, dict) or set(row) != {"run_id", "arm_id", "model_id", "usd"}:
                    raise ValueError("invalid accounting row")
                for field in ("run_id", "arm_id", "model_id"):
                    _identifier(row[field])
                _usd(row["usd"])
            return state
        except Exception:
            raise OverCap("unavailable or corrupt spend ledger") from None

    def _totals(self, state):
        run = [r for r in state["reservations"] if r["run_id"] == self.run_id]
        return (sum((_usd(r["usd"]) for r in run if r["arm_id"] == self.arm_id), Decimal(0)),
                sum((_usd(r["usd"]) for r in run), Decimal(0)))

    def meter(self, model_id, usd, *, expected_record=None):
        """Reserve a conservative USD ceiling atomically BEFORE any paid I/O."""
        amount = _usd(usd)
        record = self.check(model_id)
        if expected_record is not None and record != expected_record:
            raise NotAdmitted("admission changed since the cost quote")
        try:
            with lock(self.lock_path):
                state = self._ledger()
                arm, run = self._totals(state)
                if arm + amount > record.arm_cap_usd or run + amount > record.run_cap_usd:
                    raise OverCap("model call exceeds arm or run cap")
                state["reservations"].append(dict(run_id=self.run_id, arm_id=self.arm_id,
                                                  model_id=model_id, usd=_money(amount)))
                atomic_json(self.spend_path, state)
        except OSError:
            raise OverCap("spend reservation could not be persisted") from None

    def spent(self):
        with lock(self.lock_path, shared=True):
            arm, run = self._totals(self._ledger())
        return {"arm_usd": _money(arm), "run_usd": _money(run)}


@contextmanager
def bind(gate):
    """Service-owned context for callers using module-level check()/meter()."""
    if type(gate) is not Admission:
        raise NotAdmitted("invalid admission context")
    token = _ACTIVE.set(gate)
    try:
        yield gate
    finally:
        _ACTIVE.reset(token)


def check(model_id):
    gate = _ACTIVE.get()
    if gate is None:
        raise NotAdmitted("no run and arm admission context")
    return gate.check(model_id)


def meter(model_id, usd):
    gate = _ACTIVE.get()
    if gate is None:
        raise NotAdmitted("no run and arm admission context")
    return gate.meter(model_id, usd)
