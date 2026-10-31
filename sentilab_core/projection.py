"""Python replay of contracts/contract-0.2/evidence-projection.mjs.

The pinned JavaScript contract is the independent CI oracle, never a runtime
subprocess. Authenticated envelopes still require these semantic checks: rejected
events stay in the audit but cannot mutate the projected evidence graph.
"""
from .envelope import canonical

KINDS = {"candidate", "measurement", "comparison", "claim", "source", "example",
         "dataset", "adapter", "benchmark_result"}
ROOT_KINDS = {"source", "measurement", "example", "dataset", "adapter"}
SEMANTICS = ("task_contract", "metric_id", "evaluator_version", "coordinate_frame")
TIERS = {"replayed", "cross_solver", "cross_arch", "analytic"}
DECISIONS = {"retrained", "accepted_with_disclosure", "retired"}
TRANSITIONS = {
    "proposed": {"rejected_schema", "validated", "cancelled"},
    "validated": {"rejected_constraints", "simulation_pending", "cancelled"},
    "simulation_pending": {"failed_run", "evaluated", "cancelled"},
    "evaluated": {"non_improving", "tie", "inconclusive", "reproduction_pending", "cancelled"},
    "reproduction_pending": {"reproduction_failed", "reproduced", "cancelled"},
    "reproduced": {"non_improving_current", "within_margin", "accepted"},
}


def _truthy(value):
    # JavaScript regards even empty arrays/objects as true.
    return isinstance(value, (dict, list)) or bool(value)


def _semantic_key(value):
    # JS Set uses object identity and distinguishes booleans from numbers.
    if isinstance(value, (dict, list)):
        return ("object", id(value))
    return ("number" if type(value) in (int, float) else type(value).__name__, value)


def _members(body, key):
    value = body.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("invalid projection member list")
    return value


def project(prefix):
    nodes, rejected = {}, []

    def reaches(start, target, relation, visited=None):
        if start == target:
            return True
        visited = set() if visited is None else visited
        if start in visited:
            return False
        visited.add(start)
        node = nodes[start]
        children = (node["links"] if relation == "links" else
                    [member for members in node["sets"].values() for member in members])
        return any(reaches(child, target, relation, visited) for child in children)

    def has_withdrawn(node_id, seen=None):
        seen = set() if seen is None else seen
        if node_id in seen:
            return False
        seen.add(node_id)
        node = nodes[node_id]
        return node["withdrawn"] or any(has_withdrawn(member, seen)
                                        for members in node["sets"].values() for member in members)

    def validity(node_id, memo=None):
        memo = {} if memo is None else memo
        if node_id in memo:
            return memo[node_id]
        node = nodes[node_id]
        if node["withdrawn"]:
            result = "withdrawn"
        elif not node["sets"]:
            result = "valid" if node["kind"] in ROOT_KINDS else "unverified"
        elif any(all(validity(member, memo) == "valid" for member in members)
                 for members in node["sets"].values()):
            result = "valid"
        else:
            result = "stale" if has_withdrawn(node_id) else "unverified"
        memo[node_id] = result
        return result

    def apply(event):
        body, kind = event["body"], event["type"]
        node = nodes.get(body.get("node"))
        if kind == "node.create":
            node_id = body["id"]
            if node_id in nodes:
                return "duplicate_node"
            if body.get("kind") not in KINDS:
                return "unknown_kind"
            semantics = body.get("semantics")
            semantics = semantics if isinstance(semantics, dict) else {}
            if body["kind"] in {"measurement", "comparison"} and any(
                    not _truthy(semantics.get(field)) for field in SEMANTICS):
                return "missing_semantics"
            nodes[node_id] = {"kind": body["kind"], "semantics": semantics, "sets": {},
                              "checks": [], "withdrawn": False, "withdraw_epoch": 0,
                              "covers": {}, "links": [], "accepted_ever": False,
                              "lifecycle": "proposed" if body["kind"] == "candidate" else None}
        elif kind == "support.add":
            if node is None:
                return "unknown_node"
            members = _members(body, "members")
            if not members:
                return "empty_support_set"
            if any(member not in nodes for member in members):
                return "unknown_node"
            if body["set_id"] in node["sets"]:
                return "duplicate_set"
            if any(reaches(member, body["node"], "sets") for member in members):
                return "cycle"
            for field in SEMANTICS:
                declared = [n["semantics"].get(field) for n in [node, *(nodes[m] for m in members)]]
                if len({_semantic_key(value) for value in declared if _truthy(value)}) > 1:
                    return "semantics_mismatch"
            node["sets"][body["set_id"]] = list(members)
        elif kind == "lifecycle.transition":
            if node is None:
                return "unknown_node"
            if node["kind"] != "candidate":
                return "not_a_candidate"
            if body.get("to") not in TRANSITIONS.get(node["lifecycle"], set()):
                return "illegal_transition"
            if body["to"] == "accepted":
                if event.get("actor_role") != "acceptance_gate":
                    return "unauthorized_actor"
                if validity(body["node"]) != "valid":
                    return "unsupported_acceptance"
            node["lifecycle"] = body["to"]
            node["accepted_ever"] |= body["to"] == "accepted"
        elif kind == "verify.add":
            if node is None:
                return "unknown_node"
            if body.get("tier") not in TIERS:
                return "unknown_tier"
            evidence = _members(body, "evidence")
            if any(member not in nodes for member in evidence):
                return "unknown_node"
            if not evidence or any(reaches(member, body["node"], "sets") for member in evidence):
                return "bad_evidence"
            node["checks"].append((body["tier"], list(evidence)))
        elif kind in ("withdraw", "withdraw.retract"):
            if node is None:
                return "unknown_node"
            if kind == "withdraw":
                if node["withdrawn"]:
                    return "already_withdrawn"
                node["withdrawn"] = True
                node["withdraw_epoch"] += 1
            else:
                if not node["withdrawn"]:
                    return "not_withdrawn"
                node["withdrawn"] = False
        elif kind == "link.add":
            if body.get("rel") not in {"trained_on", "contains"}:
                return "unknown_rel"
            if body.get("from") not in nodes or body.get("to") not in nodes:
                return "unknown_node"
            source, target = nodes[body["from"]], nodes[body["to"]]
            allowed = (source["kind"] == "adapter" and target["kind"] == "dataset"
                       if body["rel"] == "trained_on" else source["kind"] == "dataset" and
                       target["kind"] in {"example", "dataset"})
            if not allowed:
                return "bad_link_kinds"
            if reaches(body["to"], body["from"], "links"):
                return "cycle"
            source["links"].append(body["to"])
        elif kind == "review.resolve":
            if node is None:
                return "unknown_node"
            if body.get("decision") not in DECISIONS:
                return "unknown_decision"
            covers = _members(body, "covers")
            if any(member not in nodes for member in covers):
                return "unknown_node"
            for member in covers:
                node["covers"][member] = nodes[member]["withdraw_epoch"]
        else:
            return "unknown_event_type"
        return None

    seen_ids, seen_seq = {}, set()
    events = [envelope["event"] for envelope in prefix]
    for event in sorted(events, key=lambda e: (e["seq"], e["event_id"])):
        fingerprint = canonical({"type": event["type"], "body": event["body"],
                                 "actor_role": event.get("actor_role")})
        event_id = event["event_id"]
        if event_id in seen_ids:
            if seen_ids[event_id] != fingerprint:
                rejected.append({"event_id": event_id, "code": "event_id_conflict"})
            continue
        seen_ids[event_id] = fingerprint
        if event["seq"] in seen_seq:
            rejected.append({"event_id": event_id, "code": "duplicate_seq"})
            continue
        seen_seq.add(event["seq"])
        code = apply(event)
        if code:
            rejected.append({"event_id": event_id, "code": code})

    final_memo, roots_memo, review_memo = {}, {}, {}

    def withdrawn_roots(node_id):
        if node_id in roots_memo:
            return roots_memo[node_id]
        node, found = nodes[node_id], set()
        roots_memo[node_id] = found
        if node["withdrawn"]:
            found.add(node_id)
        elif validity(node_id, final_memo) != "valid":
            for members in node["sets"].values():
                for member in members:
                    if validity(member, final_memo) != "valid":
                        found.update(withdrawn_roots(member))
        return found

    def taint(node_id):
        found, visited = set(), set()

        def collect(member):
            if member in visited:
                return
            visited.add(member)
            node = nodes[member]
            if node["withdrawn"]:
                found.add(member)
            for members in node["sets"].values():
                for child in members:
                    collect(child)
            for child in node["links"]:
                collect(child)

        for member in nodes[node_id]["links"]:
            collect(member)
        return found

    def review_required(node_id):
        if node_id in review_memo:
            return review_memo[node_id]
        review_memo[node_id] = False
        node = nodes[node_id]
        uncovered = any(node["covers"].get(source) != nodes[source]["withdraw_epoch"]
                        for source in taint(node_id))
        result = uncovered or any(review_required(member)
                                  for members in node["sets"].values() for member in members)
        review_memo[node_id] = result
        return result

    output = {}
    for node_id, node in sorted(nodes.items()):
        status = validity(node_id, final_memo)
        output[node_id] = {
            "kind": node["kind"], "lifecycle": node["lifecycle"], "accepted_ever": node["accepted_ever"],
            "validity": status, "stale_because": sorted(withdrawn_roots(node_id)) if status == "stale" else [],
            "support_status": {key: "valid" if all(validity(member, final_memo) == "valid" for member in members)
                               else "broken" for key, members in node["sets"].items()},
            "tiers": sorted({tier for tier, evidence in node["checks"]
                             if all(validity(member, final_memo) == "valid" for member in evidence)}),
            "tainted_by": sorted(taint(node_id)), "review_required": review_required(node_id),
        }
    return {"nodes": output, "rejected": rejected}


def board(prefix, projection=None):
    projection = project(prefix) if projection is None else projection
    rejected = {event['event_id'] for event in projection['rejected']}
    for envelope in reversed(prefix):
        event = envelope['event']
        if event['event_id'] in rejected:
            continue
        if event['type'] == 'lifecycle.transition' and event['body'].get('to') == 'accepted':
            node = event['body']['node']
            if projection['nodes'].get(node, {}).get('validity') == 'valid':
                decision = event['body']['record']
                return {'candidate_id': node, 'j': decision['inputs']['reproduction']['j'],
                        'seq': event['seq']}
    return None
