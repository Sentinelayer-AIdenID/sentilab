"""Pure sequential admission over recorded, core-validated evidence.

The positive diagnostic margin is provisional. It is neither PLAN 5.3's
uncertainty rule nor evidence of independent physical validation.
"""
from decimal import Decimal
import math


def _number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


class AcceptanceGate:
    def __init__(self, *, margin, reproduction_tolerance=0.001):
        if not _number(margin) or margin < 0:
            raise ValueError("a nonnegative provisional margin is required")
        if not _number(reproduction_tolerance) or reproduction_tolerance < 0:
            raise ValueError("a nonnegative reproduction tolerance is required")
        self.margin = margin
        self.reproduction_tolerance = reproduction_tolerance

    def decide(self, *, geometry_valid, wire_cap_mm, evaluation, reproduction,
               current, binding, stopped=False):
        """No I/O or mutations. The conductor serializes comparison and append.

        Geometry is the core's recorded pre-solve legality result, never a lab's
        assertion. All numerical evidence remains recorded after a rejection.
        """
        result = {"ai_mode": "AI off", "margin": self.margin,
                  "margin_label": "provisional margin",
                  "reproduction_label": "same-solver reproduction",
                  "current": current, "improvement": None}

        def outcome(reason):
            return {**result, "outcome": reason}

        def valid(measurement):
            return (isinstance(measurement, dict) and
                    measurement.get("type") != "untrusted_source_evidence" and
                    measurement.get("success") is True and
                    _number(measurement.get("j")) and _number(measurement.get("wire_mm")) and
                    measurement["wire_mm"] >= 0 and
                    isinstance(measurement.get("process_id"), str) and bool(measurement["process_id"]))

        if stopped is not False:
            return outcome("stopped")
        if geometry_valid is not True:
            return outcome("invalid_geometry")
        if not _number(wire_cap_mm) or wire_cap_mm <= 0:
            return outcome("invalid_wire_cap")
        if not valid(evaluation):
            return outcome("evaluation_failed")
        if evaluation["wire_mm"] > wire_cap_mm:
            return outcome("wire_cap_exceeded")
        if not valid(reproduction):
            return outcome("reproduction_failed")
        required = {"candidate_id", "task_id", "fixture_id", "metric_id", "scenario_id", "solver_id"}
        if (not isinstance(binding, dict) or set(binding) != required or
                any(not isinstance(value, str) or not value for value in binding.values()) or
                evaluation.get("binding") != binding or reproduction.get("binding") != binding):
            return outcome("binding_mismatch")
        if reproduction["process_id"] == evaluation["process_id"]:
            return outcome("fresh_process_required")
        if reproduction["wire_mm"] > wire_cap_mm:
            return outcome("wire_cap_exceeded")
        delta = abs(Decimal(str(evaluation["j"])) - Decimal(str(reproduction["j"])))
        if (delta > Decimal(str(self.reproduction_tolerance)) or
                reproduction["wire_mm"] != evaluation["wire_mm"]):
            return outcome("reproduction_mismatch")
        if current is None:
            return outcome("accepted")
        if not isinstance(current, dict) or not _number(current.get("j")):
            return outcome("invalid_current")
        improvement = Decimal(str(current["j"])) - Decimal(str(reproduction["j"]))
        result["improvement"] = float(improvement)
        if improvement <= 0:
            return outcome("non_improving_current")
        if improvement <= Decimal(str(self.margin)):
            return outcome("within_margin")
        return outcome("accepted")
