// Reference projection for the evidence contract (v0.2). Pure function of the event list.
const KINDS = new Set(["candidate", "measurement", "comparison", "claim", "source", "example", "dataset", "adapter", "benchmark_result"]);
// Primary evidence can stand alone. Anything else needs support before it can be valid.
const ROOT_KINDS = new Set(["source", "measurement", "example", "dataset", "adapter"]);
const SEMANTICS = ["task_contract", "metric_id", "evaluator_version", "coordinate_frame"];
const NEEDS_SEMANTICS = new Set(["measurement", "comparison"]);
const TIERS = new Set(["replayed", "cross_solver", "cross_arch", "analytic"]);
const DECISIONS = new Set(["retrained", "accepted_with_disclosure", "retired"]);
const TRANSITIONS = {
  proposed: ["rejected_schema", "validated", "cancelled"],
  validated: ["rejected_constraints", "simulation_pending", "cancelled"],
  simulation_pending: ["failed_run", "evaluated", "cancelled"],
  evaluated: ["non_improving", "tie", "inconclusive", "reproduction_pending", "cancelled"],
  reproduction_pending: ["reproduction_failed", "reproduced", "cancelled"],
  reproduced: ["non_improving_current", "within_margin", "accepted"],
};

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value) ?? "null";
}

export function project(events) {
  const nodes = new Map();
  const rejected = [];

  const supportReaches = (from, target, visited = new Set()) => {
    if (from === target) return true;
    if (visited.has(from)) return false;
    visited.add(from);
    return nodes.get(from).sets.some((set) => set.members.some((member) => supportReaches(member, target, visited)));
  };
  const linkReaches = (from, target, visited = new Set()) => {
    if (from === target) return true;
    if (visited.has(from)) return false;
    visited.add(from);
    return nodes.get(from).links.some((link) => linkReaches(link.to, target, visited));
  };
  const withdrawnRootsBehind = (id, memo = new Map()) => {
    if (memo.has(id)) return memo.get(id);
    const node = nodes.get(id);
    const found = new Set();
    memo.set(id, found);
    if (node.withdrawn) { found.add(id); return found; }
    if (validity(id) !== "valid") {
      for (const set of node.sets) for (const member of set.members) {
        if (validity(member) !== "valid") for (const root of withdrawnRootsBehind(member, memo)) found.add(root);
      }
    }
    return found;
  };
  // Computed from current node state, so it is correct both during replay and at the end.
  // Memoized per call during replay, and once for the whole output after it, so diamonds stay linear.
  let finalMemo = null;
  const validity = (id, memo = finalMemo ?? new Map()) => {
    if (memo.has(id)) return memo.get(id);
    const node = nodes.get(id);
    let result;
    if (node.withdrawn) result = "withdrawn";
    else if (node.sets.length === 0) result = ROOT_KINDS.has(node.kind) ? "valid" : "unverified";
    else {
      const anyValid = node.sets.some((set) => set.members.every((member) => validity(member, memo) === "valid"));
      if (anyValid) result = "valid";
      else {
        const hasWithdrawnRoot = (nid, seen = new Set()) => {
          if (seen.has(nid)) return false;
          seen.add(nid);
          const n = nodes.get(nid);
          if (n.withdrawn) return true;
          return n.sets.some((set) => set.members.some((member) => hasWithdrawnRoot(member, seen)));
        };
        result = hasWithdrawnRoot(id) ? "stale" : "unverified";
      }
    }
    memo.set(id, result);
    return result;
  };

  const apply = (event) => {
    const { type, body } = event;
    const node = nodes.get(body.node);
    switch (type) {
      case "node.create": {
        if (nodes.has(body.id)) return "duplicate_node";
        if (!KINDS.has(body.kind)) return "unknown_kind";
        const semantics = body.semantics ?? {};
        if (NEEDS_SEMANTICS.has(body.kind) && SEMANTICS.some((field) => !semantics[field])) return "missing_semantics";
        nodes.set(body.id, {
          id: body.id, kind: body.kind, semantics, sets: [], withdrawn: false, withdrawEpoch: 0, verifications: [],
          covers: new Map(), links: [], lifecycle: body.kind === "candidate" ? "proposed" : null,
          history: body.kind === "candidate" ? ["proposed"] : [],
        });
        return null;
      }
      case "support.add": {
        if (!node) return "unknown_node";
        const members = body.members ?? [];
        if (members.length === 0) return "empty_support_set";
        if (members.some((member) => !nodes.has(member))) return "unknown_node";
        if (node.sets.some((set) => set.set_id === body.set_id)) return "duplicate_set";
        if (members.some((member) => supportReaches(member, body.node))) return "cycle";
        // The node and every member of the set must agree on each field any of them declares.
        for (const field of SEMANTICS) {
          const declared = new Set([node, ...members.map((member) => nodes.get(member))].map((n) => n.semantics[field]).filter(Boolean));
          if (declared.size > 1) return "semantics_mismatch";
        }
        node.sets.push({ set_id: body.set_id, members: [...members] });
        return null;
      }
      case "lifecycle.transition": {
        if (!node) return "unknown_node";
        if (node.kind !== "candidate") return "not_a_candidate";
        if (!(TRANSITIONS[node.lifecycle] ?? []).includes(body.to)) return "illegal_transition";
        if (body.to === "accepted") {
          if (event.actor_role !== "acceptance_gate") return "unauthorized_actor";
          if (validity(body.node) !== "valid") return "unsupported_acceptance";
        }
        node.lifecycle = body.to;
        node.history.push(body.to);
        return null;
      }
      case "verify.add": {
        if (!node) return "unknown_node";
        if (!TIERS.has(body.tier)) return "unknown_tier";
        const evidence = body.evidence ?? [];
        if (evidence.some((id) => !nodes.has(id))) return "unknown_node";
        if (evidence.length === 0 || evidence.some((id) => supportReaches(id, body.node))) return "bad_evidence";
        node.verifications.push({ tier: body.tier, evidence: [...evidence] });
        return null;
      }
      case "withdraw":
        if (!node) return "unknown_node";
        if (node.withdrawn) return "already_withdrawn";
        node.withdrawn = true;
        node.withdrawEpoch += 1;
        return null;
      case "withdraw.retract":
        if (!node) return "unknown_node";
        if (!node.withdrawn) return "not_withdrawn";
        node.withdrawn = false;
        return null;
      case "link.add": {
        if (body.rel !== "trained_on" && body.rel !== "contains") return "unknown_rel";
        if (!nodes.has(body.from) || !nodes.has(body.to)) return "unknown_node";
        const from = nodes.get(body.from).kind;
        const to = nodes.get(body.to).kind;
        const allowed = body.rel === "trained_on"
          ? from === "adapter" && to === "dataset"
          : from === "dataset" && (to === "example" || to === "dataset");
        if (!allowed) return "bad_link_kinds";
        if (linkReaches(body.to, body.from)) return "cycle";
        nodes.get(body.from).links.push({ rel: body.rel, to: body.to });
        return null;
      }
      case "review.resolve":
        if (!node) return "unknown_node";
        if (!DECISIONS.has(body.decision)) return "unknown_decision";
        if ((body.covers ?? []).some((id) => !nodes.has(id))) return "unknown_node";
        // A review covers one specific withdrawal. A later withdrawal of the same node needs a new review.
        for (const id of body.covers ?? []) node.covers.set(id, nodes.get(id).withdrawEpoch);
        return null;
      default:
        return "unknown_event_type";
    }
  };

  const seenIds = new Map();
  const seenSeq = new Map();
  const ordered = [...events].sort((a, b) => a.seq - b.seq || String(a.event_id).localeCompare(String(b.event_id)));
  for (const event of ordered) {
    const fingerprint = canonical({ type: event.type, body: event.body, actor_role: event.actor_role ?? null });
    if (seenIds.has(event.event_id)) {
      if (seenIds.get(event.event_id) !== fingerprint) rejected.push({ event_id: event.event_id, code: "event_id_conflict" });
      continue;
    }
    seenIds.set(event.event_id, fingerprint);
    if (seenSeq.has(event.seq)) { rejected.push({ event_id: event.event_id, code: "duplicate_seq" }); continue; }
    seenSeq.set(event.seq, event.event_id);
    const code = apply(event);
    if (code) rejected.push({ event_id: event.event_id, code });
  }

  finalMemo = new Map();

  // Taint follows everything actually consumed: contained items, their contents, and every support
  // set behind them, whether or not an OR alternative keeps the item valid.
  const taint = (id) => {
    const found = new Set();
    const visited = new Set();
    const collect = (nid) => {
      if (visited.has(nid)) return;
      visited.add(nid);
      const n = nodes.get(nid);
      if (n.withdrawn) found.add(nid);
      for (const set of n.sets) for (const member of set.members) collect(member);
      for (const link of n.links) collect(link.to);
    };
    for (const link of nodes.get(id).links) collect(link.to);
    return found;
  };
  const reviewMemo = new Map();
  const reviewRequired = (id) => {
    if (reviewMemo.has(id)) return reviewMemo.get(id);
    reviewMemo.set(id, false);
    const node = nodes.get(id);
    const uncovered = [...taint(id)].some((source) => node.covers.get(source) !== nodes.get(source).withdrawEpoch);
    const result = uncovered || node.sets.some((set) => set.members.some(reviewRequired));
    reviewMemo.set(id, result);
    return result;
  };

  const output = {};
  for (const id of [...nodes.keys()].sort()) {
    const node = nodes.get(id);
    const state = validity(id);
    output[id] = {
      kind: node.kind,
      lifecycle: node.lifecycle,
      accepted_ever: node.history.includes("accepted"),
      validity: state,
      stale_because: state === "stale" ? [...withdrawnRootsBehind(id)].sort() : [],
      support_status: Object.fromEntries(node.sets.map((set) => [set.set_id, set.members.every((member) => validity(member) === "valid") ? "valid" : "broken"])),
      tiers: [...new Set(node.verifications.filter((v) => v.evidence.every((e) => validity(e) === "valid")).map((v) => v.tier))].sort(),
      tainted_by: [...taint(id)].sort(),
      review_required: reviewRequired(id),
    };
  }
  return { nodes: output, rejected };
}
