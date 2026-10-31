"""The open-proposal contract v1 (OP-F1): the Python reference for contracts/open-proposal-v1/.

Pure: no network, no solver, no clock. Geometric legality beyond exact integer checks (TapGeometry's margin, halo and
spacing rules) and routed wire belong to the check (OP-F7), which plugs in through validate_*(layout_checker=...).
"""
from .canonical import (actor_slot, body_sha256, conductor_geometry, digest, geometry_object, geometry_sha256,
                        manifest_id, participant_ref, proposal_sha256, run_id, source_ref, transport_id)
from .labels import label_for, label_for_all
from .states import (SUMMARY, Decision, Entry, OrderError, Revision, TransitionRefused, created_at_ns,
                     decide_revision, order_key, sort_replies, transition)
from .validator import (Outcome, Reply, validate_check_note, validate_check_request, validate_record,
                        validate_submission)

__all__ = ["actor_slot", "body_sha256", "conductor_geometry", "digest", "geometry_object", "geometry_sha256",
           "manifest_id", "participant_ref", "proposal_sha256", "run_id", "source_ref", "transport_id", "label_for",
           "label_for_all", "SUMMARY", "Decision", "Entry", "OrderError", "Revision", "TransitionRefused",
           "created_at_ns", "decide_revision", "order_key", "sort_replies", "transition", "Outcome", "Reply",
           "validate_check_note", "validate_check_request", "validate_record", "validate_submission"]
