// Reference core for the ResultCheck contract (v0.2). Deterministic: no clock, randomness, network or model.
import { createHash } from "node:crypto";

export const CHECKER_VERSION = "resultcheck-ref-0.2";
const SCOPE = "Checks submitted-data consistency and arithmetic only. Does not certify that measurements are authentic or that any model is physically valid.";
const ID_PATTERN = /^[A-Za-z0-9._:-]{1,128}$/;
const TEMPERATURE_WORDS = new Set(["", "c", "f", "k", "r", "celsius", "centigrade", "fahrenheit", "kelvin", "kelvins", "rankine"]);
const ESTIMANDS = new Set(["mean_difference", "percent_change_of_means", "mean_of_percent_changes"]);
const MAX_PAIRS = 10000;
const MAX_BYTES = 1024 * 1024;
const MAX_NOTES = 4096;
const MAX_DEPTH = 8;
const MAX_VALUES = 200000;
const MIN_NON_TIED_FOR_INFERENCE = 6;
const DEFAULT_RELATIVE_TOLERANCE = 0.001;

export function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value) ?? "null";
}
const sha256 = (text) => createHash("sha256").update(text, "utf8").digest("hex");
const round6 = (x) => { const r = Number(x.toFixed(6)); return Object.is(r, -0) ? 0 : r; };
const isObject = (x) => x !== null && typeof x === "object" && !Array.isArray(x);
const onlyKeys = (obj, allowed) => Object.keys(obj).every((key) => allowed.includes(key));
const finite = (x) => typeof x === "number" && Number.isFinite(x);
const mean = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;

// Compatibility unit spellings like U+2103 and U+212A fold under NFKC.
function isTemperatureUnit(unit) {
  const folded = unit.normalize("NFKC").toLowerCase().replace(/degrees?|deg|[\s_.\-°º]/g, "");
  return TEMPERATURE_WORDS.has(folded);
}

// Bounded, non-recursive walk, safe to run before anything else touches the input.
function structureError(request) {
  const stack = [[request, 1]];
  let values = 0;
  while (stack.length > 0) {
    const [value, depth] = stack.pop();
    values += 1;
    if (values > MAX_VALUES) return "request_too_large";
    if (value === null || typeof value !== "object") continue;
    if (depth > MAX_DEPTH) return "request_too_deep";
    for (const child of Array.isArray(value) ? value : Object.values(value)) stack.push([child, depth + 1]);
  }
  return null;
}

function validate(request) {
  if (!isObject(request)) return ["not_an_object"];
  if (Buffer.byteLength(canonical(request), "utf8") > MAX_BYTES) return ["request_too_large"];
  const errors = [];
  if (!onlyKeys(request, ["schema_version", "request_id", "metric", "pairs", "claim", "notes"])) errors.push("unknown_field");
  if (request.schema_version !== "resultcheck.request.v2") errors.push("bad_schema_version");
  if (typeof request.request_id !== "string" || !ID_PATTERN.test(request.request_id)) errors.push("bad_request_id");

  const metric = request.metric;
  if (!isObject(metric) || !onlyKeys(metric, ["name", "unit", "direction", "scale", "tie_tolerance"]) ||
      typeof metric.name !== "string" || metric.name.length < 1 || metric.name.length > 128 ||
      typeof metric.unit !== "string" || metric.unit.length > 32 ||
      !["lower_is_better", "higher_is_better"].includes(metric.direction) ||
      (metric.scale !== undefined && !["ratio", "interval"].includes(metric.scale)) ||
      (metric.tie_tolerance !== undefined && (!finite(metric.tie_tolerance) || metric.tie_tolerance < 0))) errors.push("bad_metric");

  if (!Array.isArray(request.pairs)) errors.push("bad_pairs");
  else if (request.pairs.length > MAX_PAIRS) errors.push("too_many_pairs");
  else {
    const validValue = (x) => x === null || finite(x);
    let grouped = 0;
    for (const pair of request.pairs) {
      if (!isObject(pair) || !onlyKeys(pair, ["id", "baseline", "candidate", "group"])) { errors.push("bad_pairs"); break; }
      if (typeof pair.id !== "string" || !ID_PATTERN.test(pair.id)) { errors.push("bad_pair_id"); break; }
      if (!("baseline" in pair) || !("candidate" in pair) || !validValue(pair.baseline) || !validValue(pair.candidate)) { errors.push("bad_pair_value"); break; }
      if (pair.group !== undefined) {
        if (typeof pair.group !== "string" || !ID_PATTERN.test(pair.group)) { errors.push("bad_pair_group"); break; }
        grouped += 1;
      }
    }
    if (grouped > 0 && grouped < request.pairs.length && !errors.includes("bad_pair_group") && !errors.includes("bad_pairs") && !errors.includes("bad_pair_id") && !errors.includes("bad_pair_value")) errors.push("bad_pair_group");
  }

  if (request.claim !== undefined) {
    const claim = request.claim;
    if (!isObject(claim) || !onlyKeys(claim, ["estimand", "value", "tolerance"]) || !ESTIMANDS.has(claim.estimand) ||
        !finite(claim.value) || (claim.tolerance !== undefined && (!finite(claim.tolerance) || claim.tolerance < 0))) errors.push("bad_claim");
  }
  if (request.notes !== undefined && (typeof request.notes !== "string" || request.notes.length > MAX_NOTES)) errors.push("bad_notes");
  return errors;
}

// Exact two-sided sign test in log space, so it stays finite at the 10,000 pair limit.
function signTest(wins, losses) {
  const n = wins + losses;
  const k = Math.max(wins, losses);
  let logCoefficient = 0;
  let tail = 0;
  for (let i = 0; i <= n; i += 1) {
    if (i >= k) tail += Math.exp(logCoefficient - n * Math.LN2);
    logCoefficient += Math.log(n - i) - Math.log(i + 1);
  }
  return Math.min(1, 2 * tail);
}

function checkClaim(claim, metric, units, improvements, flags) {
  const base = { estimand: claim.estimand, claimed: claim.value };
  const refuse = (flag) => { flags.add(flag); return { ...base, recomputed: null, difference: null, tolerance: null, tolerance_basis: null, outcome: "refused" }; };
  let recomputed;
  if (claim.estimand === "mean_difference") {
    recomputed = mean(improvements);
  } else {
    // Fail closed: percentages need a declared ratio scale and a non-temperature unit.
    if (metric.scale !== "ratio" || isTemperatureUnit(metric.unit)) return refuse("invalid_normalization");
    if (claim.estimand === "percent_change_of_means") {
      const meanBaseline = mean(units.map((u) => u.baseline));
      if (meanBaseline === 0) return refuse("zero_denominator");
      recomputed = (mean(improvements) / Math.abs(meanBaseline)) * 100;
    } else {
      if (units.some((u) => u.baseline === 0)) return refuse("zero_denominator");
      recomputed = mean(units.map((u, i) => improvements[i] / Math.abs(u.baseline))) * 100;
    }
  }
  const declared = claim.tolerance !== undefined;
  const tolerance = declared ? claim.tolerance : Math.max(1e-12, DEFAULT_RELATIVE_TOLERANCE * Math.max(Math.abs(recomputed), Math.abs(claim.value)));
  const difference = Math.abs(recomputed - claim.value);
  const matches = difference <= tolerance + 1e-12;
  if (!matches) flags.add("arithmetic_discrepancy");
  return {
    ...base,
    recomputed: round6(recomputed),
    difference: round6(difference),
    tolerance: round6(tolerance),
    tolerance_basis: declared ? "declared" : "default_relative",
    outcome: matches ? "matches" : "discrepancy",
  };
}

function rejectedReceipt(errors, requestHash, requestId = null, notesPresent = false) {
  return seal({
    schema_version: "resultcheck.receipt.v2", checker_version: CHECKER_VERSION, scope: SCOPE,
    request_hash: requestHash, request_id: requestId, notes_present: notesPresent,
    status: "rejected", errors, counts: null, flags: [], statistics: null, claim_result: null,
  });
}

// Entry point for transports: checks the byte size before parsing anything.
export function checkRaw(text) {
  const requestHash = sha256(text);
  if (Buffer.byteLength(text, "utf8") > MAX_BYTES) return rejectedReceipt(["request_too_large"], requestHash);
  let parsed;
  try { parsed = JSON.parse(text); } catch (error) {
    return rejectedReceipt([error instanceof RangeError ? "request_too_deep" : "not_json"], requestHash);
  }
  return check(parsed);
}

export function check(request) {
  const structure = structureError(request);
  if (structure) return rejectedReceipt([structure], null);

  const requestId = isObject(request) && typeof request.request_id === "string" && ID_PATTERN.test(request.request_id) ? request.request_id : null;
  const notesPresent = isObject(request) && typeof request.notes === "string";
  const requestHash = sha256(canonical(request));
  const errors = validate(request);
  if (errors.length > 0) return rejectedReceipt(errors, requestHash, requestId, notesPresent);

  const receipt = {
    schema_version: "resultcheck.receipt.v2", checker_version: CHECKER_VERSION, scope: SCOPE,
    request_hash: requestHash, request_id: requestId, notes_present: notesPresent,
  };

  const occurrences = new Map();
  for (const pair of request.pairs) occurrences.set(pair.id, (occurrences.get(pair.id) ?? 0) + 1);
  const duplicates = [...occurrences].filter(([, count]) => count > 1).map(([id]) => id).sort();
  const distinct = request.pairs.filter((pair) => occurrences.get(pair.id) === 1);
  const missing = distinct.filter((pair) => pair.baseline === null || pair.candidate === null);
  const used = distinct.filter((pair) => pair.baseline !== null && pair.candidate !== null);

  // The unit of analysis is the group when groups are declared, so nested replicates can't inflate n.
  const grouped = request.pairs.length > 0 && request.pairs[0].group !== undefined;
  let units = used.map((pair) => ({ baseline: pair.baseline, candidate: pair.candidate }));
  if (grouped) {
    const byGroup = new Map();
    for (const pair of used) {
      if (!byGroup.has(pair.group)) byGroup.set(pair.group, []);
      byGroup.get(pair.group).push(pair);
    }
    units = [...byGroup.keys()].sort().map((group) => ({
      baseline: mean(byGroup.get(group).map((p) => p.baseline)),
      candidate: mean(byGroup.get(group).map((p) => p.candidate)),
    }));
  }

  const flags = new Set();
  if (duplicates.length > 0) flags.add("duplicate_ids");
  if (missing.length > 0) flags.add("missing_pairs");
  const counts = {
    submitted: request.pairs.length,
    duplicates_excluded: request.pairs.length - distinct.length,
    missing_excluded: missing.length,
    used: used.length,
    analysis_unit: grouped ? "group" : "pair",
    units: units.length,
  };
  const details = { duplicate_ids: duplicates, missing_ids: missing.map((pair) => pair.id).sort() };

  if (units.length < 2) {
    return seal({ ...receipt, status: "insufficient_data", errors: [], counts, details, flags: [...flags].sort(), statistics: null, claim_result: null });
  }

  const lower = request.metric.direction === "lower_is_better";
  const tieTolerance = request.metric.tie_tolerance ?? 0;
  const improvements = units.map((u) => (lower ? u.baseline - u.candidate : u.candidate - u.baseline));
  const n = improvements.length;
  const average = mean(improvements);
  const sorted = [...improvements].sort((a, b) => a - b);
  const median = n % 2 === 1 ? sorted[(n - 1) / 2] : (sorted[n / 2 - 1] + sorted[n / 2]) / 2;
  const variance = improvements.reduce((a, d) => a + (d - average) ** 2, 0) / (n - 1);
  const wins = improvements.filter((d) => d > tieTolerance).length;
  const losses = improvements.filter((d) => d < -tieTolerance).length;
  const enough = wins + losses >= MIN_NON_TIED_FOR_INFERENCE;
  if (!enough) flags.add("insufficient_for_inference");

  const statistics = {
    mean_improvement: round6(average),
    median_improvement: round6(median),
    sd_sample: round6(Math.sqrt(variance)),
    min: round6(sorted[0]),
    max: round6(sorted[n - 1]),
    wins,
    losses,
    ties: n - wins - losses,
    tie_tolerance: tieTolerance,
    sign_test_p_two_sided: enough ? round6(signTest(wins, losses)) : null,
  };
  const claimResult = request.claim ? checkClaim(request.claim, request.metric, units, improvements, flags) : null;
  return seal({
    ...receipt,
    status: flags.size > 0 ? "checked_with_flags" : "checked",
    errors: [],
    counts,
    details,
    flags: [...flags].sort(),
    statistics,
    claim_result: claimResult,
  });
}

function seal(receipt) {
  return { ...receipt, receipt_hash: sha256(canonical(receipt)) };
}
