"""A door result's evaluator identity string, and so its temperature label (contracts/open-proposal-v1/builds.json).

Every scored result names the full identity its run attests, in the builds.json form (builds.build_id): engine and
engine commit, binary, the configuration files' hashes, grid and the seal over every field. The fields come from:
  engine, engine_commit   the signed manifest's statistic.evaluator (kind hotspot6 is HotSpot-6.0; its upstream)
  binary_sha256           the bound evaluation receipt's binary
  config_sha256           the bound evaluation receipt's input hashes, for exactly a registered build's config files
  image                   a registered build's image, attested by digest alone (image_attested): the bound receipt's
                          image_digest and the signed grant's scorer_image_digest are that build's recorded
                          image_digest; otherwise absent. No tag is read: a tag is mutable and proves no image
  grid, centre_mapping    the signed manifest's statistic
never from constants here. When they are all a registered build's, the string is that build's, and label_for reads it
"reproduction_tested"; any other run's string (another image digest or none, another or a missing config file, another
binary, commit, grid or mapping) is one no list names, and reads unvalidated. A build whose recorded image_digest is
null is never matched: builds.json records none for the gate-zero image, so until one is recorded every door result
reads unvalidated. ALIAS, the broad string the door named before builds.json, keeps its meaning: it names no build and
reads unvalidated.

The label is the build's. It never changes a result's own qualifiers: replay status, binding basis and mismatch, a
missing grid, the active guard and the candidate verdict stay exactly what the result's verification says.
"""
from __future__ import annotations

from open_proposals.contract import builds

from .scorer import EVALUATOR_BINARY_SHA256, IMAGE

ENGINES = {"hotspot6": builds.ENGINE}
ALIAS = f"hotspot6:{EVALUATOR_BINARY_SHA256}:grid:64x64"


def image_attested(build: dict, receipt: dict, grant) -> bool:
    """Whether this run proves, by digest, that it ran the build's image: the digest builds.json records for the build
    is well-formed (sha256: and 64 lower-case hex), and the receipt's image_digest and the grant's scorer_image_digest
    each equal it, so they equal each other. A null or malformed recorded digest matches nothing, not even a run that
    carries no digest either."""
    recorded = build.get("image_digest")
    if not isinstance(recorded, str) or not IMAGE.match(recorded):
        return False
    return receipt.get("image_digest") == recorded and getattr(grant, "scorer_image_digest", None) == recorded


def attested(build: dict, receipt, manifest, grant) -> dict:
    """The identity this run attests, over the fields (and configuration file names) of a registered build."""
    receipt = receipt if isinstance(receipt, dict) else {}
    statistic = manifest.get("statistic", {}) if isinstance(manifest, dict) else {}
    evaluator = statistic.get("evaluator", {})
    inputs = receipt.get("input_sha256") if isinstance(receipt.get("input_sha256"), dict) else {}
    return {"schema": builds.BUILD_SCHEMA, "engine": ENGINES.get(evaluator.get("kind")),
            "engine_commit": evaluator.get("upstream"), "binary_sha256": receipt.get("binary_sha256"),
            "image": build["identity"]["image"] if image_attested(build, receipt, grant) else None,
            "config_sha256": {name: inputs.get(name) for name in build["identity"]["config_sha256"]},
            "grid": statistic.get("grid"), "centre_mapping": statistic.get("centre_mapping")}


def evaluator_identity(receipt, manifest, grant, registered=None) -> str:
    """The identity string this run attests: a registered build's when every field is that build's, otherwise the
    same form over what the run does attest (no list names it)."""
    known = builds.registered() if registered is None else registered
    if not known:
        return ALIAS
    for build in known:
        if builds.build_id(attested(build, receipt, manifest, grant)) == build["id"]:
            return build["id"]
    return builds.build_id(attested(known[0], receipt, manifest, grant))
