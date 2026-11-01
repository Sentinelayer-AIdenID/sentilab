"""The open-proposal contract v1 (OP-F1, DESIGN rev 3): the Python reference for contracts/open-proposal-v1/.

Pure: no network, no solver, no clock. Geometric legality beyond the exact integer checks (TapGeometry's margin, halo
and spacing rules, and keepouts) belongs to OP-F7 and plugs in through layout_checker=...; unsealing plugs in through
opener=... (age_tools.reference_opener for the test identities).
"""
from .canonical import (actor_slot, body_sha256, conductor_geometry, content_sha256, digest, geometry_object,
                        geometry_sha256, logical_key, manifest_id, participant_ref, proposal_sha256, r_key,
                        request_sha256, run_id, sealed_header, source_ref, transport_key, transport_key_for,
                        transport_key_object)
from .labels import label_for, label_for_all
from .predicates import apply_suppression, evaluate_labels, record_diagnostic
from .states import (CHARGED, LEDGER, SUMMARY, Decision, Entry, OrderError, Prior, TransitionRefused, created_at_ns,
                     decide, decide_publish, ledger_lifecycle, order_key, sort_replies, transition)
from .validator import Outcome, Reply, Unopenable, validate_local, validate_record, validate_reply

__all__ = ["actor_slot", "body_sha256", "conductor_geometry", "content_sha256", "digest", "geometry_object",
           "geometry_sha256", "logical_key", "manifest_id", "participant_ref", "proposal_sha256", "r_key",
           "request_sha256", "run_id", "sealed_header", "source_ref", "transport_key", "transport_key_for",
           "transport_key_object", "label_for", "label_for_all", "apply_suppression", "evaluate_labels",
           "record_diagnostic", "CHARGED", "LEDGER", "SUMMARY", "Decision", "Entry", "OrderError", "Prior",
           "TransitionRefused", "created_at_ns", "decide", "decide_publish", "ledger_lifecycle", "order_key",
           "sort_replies", "transition", "Outcome", "Reply", "Unopenable", "validate_local", "validate_record",
           "validate_reply"]
