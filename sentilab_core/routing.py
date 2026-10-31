"""Deterministic advisory routing over a declared registry and frozen examples.

A task is an adapter proposal ``{"candidate": route_id, "score": raw_score}``,
not a request to call a model. Scores are calibrated by empirical correctness
within route/score buckets on the fitting split only. Unseen buckets abstain.
The held-out report measures this interface; synthetic examples do not prove
deployment accuracy. This module grants no permissions or acceptance authority.
"""
import json
import math
from pathlib import Path
from types import MappingProxyType


BUCKET_EDGES = (0.0, 0.25, 0.5, 0.75, 1.0)


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value


def _probability(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number in [0, 1]")
    if not 0 <= value <= 1 or not math.isfinite(value):
        raise ValueError(f"{field} must be a finite number in [0, 1]")
    return float(value)


def _bucket(score):
    # Left closed, right open, except the final bucket also includes 1.
    return min(int(score * 4), 3)


class AdvisoryRouter:
    """Read-only registry with training-only, per-route histogram calibration.

    Each example has id, family, task and expected (route ID or null). IDs and
    families must be disjoint between fitting and evaluation. Family names are
    supplied by the fixture owner; this check cannot establish real provenance.
    """

    def __init__(self, registry, calibration_examples, *, threshold=0.75):
        self.threshold = _probability(threshold, "threshold")
        if not isinstance(registry, dict) or not registry:
            raise ValueError("registry must be a nonempty object")
        routes = {}
        for name, info in registry.items():
            _text(name, "route ID")
            if not isinstance(info, dict) or set(info) != {"kind", "description"}:
                raise ValueError("route metadata requires kind and description")
            if info["kind"] not in ("capability", "lab"):
                raise ValueError("route kind must be capability or lab")
            description = _text(info["description"], "description")
            routes[name] = MappingProxyType({"kind": info["kind"], "description": description})
        self.registry = MappingProxyType(routes)
        examples = self._examples(calibration_examples)
        self._fitting_ids = frozenset(row["id"] for row in examples)
        self._fitting_families = frozenset(row["family"] for row in examples)
        fitted = {}
        for row in examples:
            candidate, score = self._proposal(row["task"])
            key = (candidate, _bucket(score))
            correct, total = fitted.get(key, (0, 0))
            fitted[key] = (correct + int(candidate == row["expected"]), total + 1)
        self._fitted = MappingProxyType(fitted)

    def _known(self, candidate):
        _text(candidate, "candidate")
        if candidate not in self.registry:
            raise ValueError(f"unknown route: {candidate}")
        return candidate

    def _proposal(self, task):
        if not isinstance(task, dict) or set(task) != {"candidate", "score"}:
            raise ValueError("task requires exactly candidate and score")
        # Reject unregistered routes even when their score would cause abstention.
        candidate = self._known(task["candidate"])
        return candidate, _probability(task["score"], "score")

    def _examples(self, examples):
        if not isinstance(examples, list):
            raise ValueError("examples must be a list")
        seen = set()
        normalized = []
        for row in examples:
            if not isinstance(row, dict) or set(row) != {"id", "family", "task", "expected"}:
                raise ValueError("example requires id, family, task and expected")
            sample_id = _text(row["id"], "example id")
            family = _text(row["family"], "example family")
            if sample_id in seen:
                raise ValueError(f"duplicate example id: {sample_id}")
            seen.add(sample_id)
            candidate, score = self._proposal(row["task"])
            expected = row["expected"]
            if expected is not None:
                self._known(expected)
            normalized.append({"id": sample_id, "family": family,
                               "task": {"candidate": candidate, "score": score},
                               "expected": expected})
        return normalized

    def route(self, task):
        """Suggest a registered route or abstain; never execute or accept it."""
        candidate, score = self._proposal(task)
        correct, total = self._fitted.get((candidate, _bucket(score)), (0, 0))
        confidence = correct / total if total else 0.0
        abstained = total == 0 or confidence < self.threshold
        reason = "uncalibrated" if total == 0 else "below_threshold" if abstained else "suggested"
        return {"choice": None if abstained else candidate,
                "candidate": candidate, "confidence": confidence, "raw_score": score,
                "calibration_samples": total, "threshold": self.threshold,
                "abstained": abstained, "reason": reason, "advisory": True}

    def calibrate(self, fixture_set):
        """Report held-out calibration without fitting or tuning any state.

        Bucket accuracy is candidate correctness before abstention; selective
        accuracy covers suggestions only. Decision accuracy also counts correct
        abstentions when the fixture's expected route is null.
        """
        examples = self._examples(fixture_set)
        if not examples:
            raise ValueError("held-out fixture set must not be empty")
        if self._fitting_ids.intersection(row["id"] for row in examples):
            raise ValueError("held-out IDs overlap calibration fitting IDs")
        if self._fitting_families.intersection(row["family"] for row in examples):
            raise ValueError("held-out families overlap calibration fitting families")
        buckets = [{"lower": BUCKET_EDGES[i], "upper": BUCKET_EDGES[i + 1],
                    "upper_inclusive": i == 3, "count": 0, "correct": 0,
                    "abstained": 0, "confidence_sum": 0.0} for i in range(4)]
        predictions = []
        candidate_correct = decision_correct = answered = answered_correct = abstained = 0
        for row in examples:
            result = self.route(row["task"])
            correct = int(result["candidate"] == row["expected"])
            decision_correct += int(result["choice"] == row["expected"])
            candidate_correct += correct
            abstained += int(result["abstained"])
            answered += int(not result["abstained"])
            answered_correct += correct if not result["abstained"] else 0
            bucket = buckets[_bucket(result["confidence"])]
            bucket["count"] += 1
            bucket["correct"] += correct
            bucket["abstained"] += int(result["abstained"])
            bucket["confidence_sum"] += result["confidence"]
            predictions.append({"id": row["id"], "expected": row["expected"], **result})
        for bucket in buckets:
            count = bucket["count"]
            confidence_sum = bucket.pop("confidence_sum")
            bucket["accuracy"] = bucket["correct"] / count if count else None
            bucket["mean_confidence"] = confidence_sum / count if count else None
        total = len(examples)
        return {"advisory": True, "method": "per-route empirical score buckets",
                "score_bucket_edges": list(BUCKET_EDGES), "threshold": self.threshold,
                "fitting_count": len(self._fitting_ids), "count": total,
                "candidate_accuracy": candidate_correct / total,
                "decision_accuracy": decision_correct / total,
                "selective_accuracy": answered_correct / answered if answered else None,
                "abstention_rate": abstained / total, "answered": answered,
                "buckets": buckets, "predictions": predictions}


def load_router_fixture(path):
    """Load versioned local interface evidence; return (router, heldout examples)."""
    fixture = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(fixture, dict) or fixture.get("schema_version") != "slab-routing-1":
        raise ValueError("unsupported routing fixture schema")
    required = {"schema_version", "evidence_kind", "description", "registry", "threshold", "calibration", "heldout"}
    if set(fixture) != required:
        raise ValueError("routing fixture has missing or unknown fields")
    if fixture["evidence_kind"] != "synthetic-interface-fixture":
        raise ValueError("routing fixture must explicitly declare synthetic interface evidence")
    _text(fixture["description"], "fixture description")
    router = AdvisoryRouter(fixture["registry"], fixture["calibration"], threshold=fixture["threshold"])
    router.calibrate(fixture["heldout"])
    return router, fixture["heldout"]
