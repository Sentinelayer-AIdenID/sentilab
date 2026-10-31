"""Bounded research evidence, deliberately separate from accepted run ledgers.

Backends and admission records are injected by the host, never by tool callers.
Only the deterministic offline fixture is shipped. Evidence hashes are audit
references, not a claim that an external tool's data flows have been verified.
"""
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Protocol

from .ledger import lock

EVIDENCE = "untrusted_source_evidence"
MAX_QUESTION_BYTES = 8192
MAX_BYTES = 32768
MAX_JOURNAL_BYTES = 4 * 1024 * 1024
MAX_RECORDS = 512
NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")
SCOPE = {"run_id", "arm", "family", "seed", "lab"}


class ResearchError(ValueError):
    """Only constant error codes cross transport boundaries."""


def dumps(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _hash(value):
    return hashlib.sha256(dumps(value).encode()).hexdigest()


def _bounded(value):
    # Bound traversal before serialization, including cycles and huge integers.
    visited = 0

    def walk(item, depth=0):
        nonlocal visited
        visited += 1
        if depth > 8 or visited > 1024:
            raise ResearchError("oversize")
        if type(item) is dict:
            if len(item) > 32:
                raise ResearchError("oversize")
            for key, child in item.items():
                if type(key) is not str or len(key) > 64:
                    raise ResearchError("invalid_input")
                walk(child, depth + 1)
        elif type(item) is list:
            if len(item) > 32:
                raise ResearchError("oversize")
            for child in item:
                walk(child, depth + 1)
        elif type(item) is str:
            if len(item) > MAX_QUESTION_BYTES or len(item.encode("utf-8")) > MAX_QUESTION_BYTES:
                raise ResearchError("oversize")
        elif item is None or type(item) is bool:
            pass
        elif type(item) is int and abs(item) <= 9007199254740991:
            pass
        else:
            raise ResearchError("invalid_input")
    walk(value)
    if len(dumps(value).encode()) > MAX_BYTES:
        raise ResearchError("oversize")


def namespace(value):
    if type(value) is not dict or set(value) != SCOPE:
        raise ResearchError("invalid_namespace")
    for key in SCOPE - {"seed"}:
        if type(value[key]) is not str or not NAME.fullmatch(value[key]):
            raise ResearchError("invalid_namespace")
    if type(value["seed"]) is not int or not 0 <= value["seed"] <= 2147483647:
        raise ResearchError("invalid_namespace")
    return dict(value)


class ResearchBackend(Protocol):
    tool: str
    version: str
    underlying_model: str

    def request(self, request_hash: str, question: str) -> list[dict]: ...


class FixtureBackend:
    tool = "offline-fixture"
    version = "1"
    underlying_model = "none:deterministic-fixture"

    def request(self, request_hash, question):
        notes = (
            "Synthetic fixture: record the cited source version and reproduction inputs.",
            "Synthetic fixture: compare the reproduction procedure with the cited method.",
        )
        text = notes[int(request_hash, 16) % len(notes)]
        return [{"text": text, "citations": [{"uri": "urn:sentilab:research:fixture:1",
                  "title": "Offline research fixture (not a literature finding)",
                  "sha256": _hash(list(notes))}]}]


def _identity(backend):
    result = {key: getattr(backend, key, None) for key in ("tool", "version", "underlying_model")}
    if any(type(v) is not str or not v.strip() or len(v) > 128 for v in result.values()):
        raise ResearchError("invalid_backend")
    return result


def admit(backend: ResearchBackend, admission_record):
    """Validate host-owned admission; a client-supplied approver is not authority.

    Hashes bind the effective configuration and name separately reviewed control
    documentation/data-flow evidence. Reviewing those artifacts is a human duty.
    """
    identity = _identity(backend)
    if type(backend) is FixtureBackend:
        if identity != {"tool": "offline-fixture", "version": "1",
                        "underlying_model": "none:deterministic-fixture"}:
            raise ResearchError("invalid_backend")
        return {"backend": identity, "admission_sha256": None, "fixture": True}
    if type(admission_record) is not dict:
        raise ResearchError("backend_not_admitted")
    _bounded(admission_record)
    required = {"tool", "version", "underlying_model", "telemetry_setting", "effective_config",
                "evidence_hashes", "approver", "namespace"}
    if set(admission_record) != required:
        raise ResearchError("invalid_admission")
    record = admission_record
    if any(record[key] != identity[key] for key in identity):
        raise ResearchError("backend_identity_mismatch")
    if identity["underlying_model"].strip().lower() in {"unknown", "none", "unspecified"}:
        raise ResearchError("invalid_admission")
    namespace(record["namespace"])
    if type(record["approver"]) is not str or not record["approver"].strip() or len(record["approver"]) > 128:
        raise ResearchError("invalid_admission")
    setting, config = record["telemetry_setting"], record["effective_config"]
    if type(setting) is not str or not setting.strip() or type(config) is not dict or config.get(setting) != "off":
        raise ResearchError("telemetry_not_off")
    hashes = record["evidence_hashes"]
    if (type(hashes) is not dict or set(hashes) != {"effective_config", "documentation", "data_flow"} or
            any(type(v) is not str or not HASH.fullmatch(v) for v in hashes.values())):
        raise ResearchError("invalid_admission")
    if hashes["effective_config"] != _hash(config):
        raise ResearchError("config_evidence_mismatch")
    return {"backend": identity, "admission_sha256": _hash(record), "fixture": False,
            "admission": {"approver": record["approver"], "namespace": dict(record["namespace"]),
                          "telemetry_setting": setting, "effective_telemetry": "off",
                          "evidence_hashes": dict(hashes)}}


def _notes(value, provenance):
    _bounded(value)
    if type(value) is not list or not 1 <= len(value) <= 8:
        raise ResearchError("invalid_backend_output")
    result = []
    for note in value:
        if type(note) is not dict or set(note) != {"text", "citations"}:
            raise ResearchError("invalid_backend_output")
        if type(note["text"]) is not str or not note["text"].strip():
            raise ResearchError("invalid_backend_output")
        citations = note["citations"]
        if type(citations) is not list or not 1 <= len(citations) <= 8:
            raise ResearchError("invalid_backend_output")
        for citation in citations:
            if type(citation) is not dict or set(citation) != {"uri", "title", "sha256"}:
                raise ResearchError("invalid_backend_output")
            if any(type(citation[k]) is not str or not citation[k].strip() for k in citation):
                raise ResearchError("invalid_backend_output")
            if not citation["uri"].startswith(("https://", "urn:")) or not HASH.fullmatch(citation["sha256"]):
                raise ResearchError("invalid_backend_output")
        result.append({"type": EVIDENCE, **note, "provenance": provenance})
    # Detach any references retained by the backend.
    result = json.loads(dumps(result))
    _bounded(result)
    return result


def _paths(root, scope):
    root = Path(root).resolve()
    store = root / "research"
    if store.is_symlink():
        raise ResearchError("invalid_store")
    path = store / (_hash(scope) + ".jsonl")
    sidecar = path.with_suffix(".lock")
    if path.is_symlink() or sidecar.is_symlink():
        raise ResearchError("invalid_store")
    return root, store, path, sidecar


def _read(path, scope):
    if not path.exists():
        return []
    rows, previous = [], None
    with path.open("rb") as handle:
        if os.fstat(handle.fileno()).st_size > MAX_JOURNAL_BYTES:
            raise ResearchError("store_full")
        while raw := handle.readline(MAX_BYTES + 2):
            if len(raw) > MAX_BYTES + 1 or not raw.endswith(b"\n") or len(rows) >= MAX_RECORDS:
                raise ResearchError("invalid_store")
            row = json.loads(raw)
            _bounded(row)
            if type(row) is not dict:
                raise ResearchError("invalid_store")
            digest = row.pop("hash", None)
            if row.get("previous") != previous or digest != _hash(row) or row.get("namespace") != scope:
                raise ResearchError("invalid_store")
            row["hash"] = digest
            rows.append(row)
            previous = digest
    return rows


def _append(path, rows, record):
    row = {**record, "previous": rows[-1]["hash"] if rows else None}
    row["hash"] = _hash(row)
    _bounded(row)
    data = dumps(row).encode() + b"\n"
    if len(rows) >= MAX_RECORDS or (path.stat().st_size if path.exists() else 0) + len(data) > MAX_JOURNAL_BYTES:
        raise ResearchError("store_full")
    with path.open("ab") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    rows.append(row)


def _receipt(rows, request_id, exporting=False):
    matches = [row for row in rows if row.get("request_id") == request_id]
    if not matches:
        raise ResearchError("not_found")
    row = matches[-1]
    status = {"request": "pending", "completed": "completed", "failed": "failed"}.get(row.get("event"))
    if status is None:
        raise ResearchError("invalid_store")
    result = {"ok": True, "request_id": request_id, "namespace": row["namespace"],
              "status": status, "type": EVIDENCE, **row["provenance"]}
    if status == "failed":
        result["error"] = {"code": "backend_failed"}
    if exporting:
        if status != "completed":
            raise ResearchError("not_completed")
        result["notes"] = row["notes"]
    return result


def _request(context, *, namespace, question, backend=None, admission_record=None):
    scope = namespace
    backend = FixtureBackend() if backend is None else backend
    admission = admit(backend, admission_record)
    if not admission["fixture"] and admission_record["namespace"] != scope:
        raise ResearchError("admission_scope_mismatch")
    provenance = {**admission, "question_sha256": hashlib.sha256(question.encode()).hexdigest()}
    request_id = _hash({"namespace": scope, **provenance})
    provenance["request_id"] = request_id
    root, store, path, sidecar = _paths(context.root, scope)
    root.mkdir(parents=True, exist_ok=True)
    with lock(root / "admission.lock", blocking=False):
        if (root / "STOP").exists():
            raise ResearchError("stopped")
        store.mkdir(exist_ok=True)
        with lock(sidecar, blocking=False):
            rows = _read(path, scope)
            if any(row.get("request_id") == request_id for row in rows):
                return _receipt(rows, request_id)
            # Reserve space for both the request and its bounded terminal record.
            if len(rows) > MAX_RECORDS - 2 or (path.stat().st_size if path.exists() else 0) > MAX_JOURNAL_BYTES - 2 * (MAX_BYTES + 1):
                raise ResearchError("store_full")
            common = {"namespace": scope, "request_id": request_id, "provenance": provenance}
            _append(path, rows, {**common, "event": "request"})
            try:
                notes = _notes(backend.request(request_id, question), {"namespace": scope, **provenance})
                if (root / "STOP").exists():
                    raise ResearchError("stopped")
                terminal = {**common, "event": "completed", "notes": notes}
                _bounded({**terminal, "previous": "0" * 64, "hash": "0" * 64})
            except Exception:
                # Untrusted exceptions/output must never echo the submitted text.
                terminal = {**common, "event": "failed"}
            _append(path, rows, terminal)
            return _receipt(rows, request_id)


def _status(context, *, namespace, request_id, exporting=False):
    _, _, path, sidecar = _paths(context.root, namespace)
    if not path.exists():
        raise ResearchError("not_found")
    with lock(sidecar, shared=True, blocking=False):
        return _receipt(_read(path, namespace), request_id, exporting)


def request(context, **arguments):
    return execute("request", context, **arguments)


def status(context, **arguments):
    return execute("status", context, **arguments)


def export(context, **arguments):
    return execute("export", context, **arguments)


def execute(command, context, **arguments):
    """Single validation/auth/STOP/error boundary for both transports."""
    try:
        _bounded(arguments)
        if command not in {"request", "status", "export"}:
            raise ResearchError("invalid_operation")
        required = {"ai_off", "namespace", "question" if command == "request" else "request_id"}
        if set(arguments) != required:
            raise ResearchError("invalid_input")
        if arguments["ai_off"] is not True:
            raise ResearchError("ai_off_required")
        scope = namespace(arguments["namespace"])
        authorized = context.options.get("research_namespace")
        if authorized is None:
            raise ResearchError("namespace_not_authorized")
        if scope != namespace(authorized):
            raise ResearchError("namespace_not_authorized")
        if command == "request":
            question = arguments["question"]
            if type(question) is not str or not question.strip():
                raise ResearchError("invalid_input")
            return _request(context, namespace=scope, question=question,
                           backend=context.options.get("research_backend"),
                           admission_record=context.options.get("research_admission"))
        request_id = arguments["request_id"]
        if type(request_id) is not str or not HASH.fullmatch(request_id):
            raise ResearchError("invalid_input")
        return _status(context, namespace=scope, request_id=request_id, exporting=command == "export")
    except ResearchError as exc:
        return {"ok": False, "error": {"code": str(exc)}}
    except BlockingIOError:
        return {"ok": False, "error": {"code": "busy"}}
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        return {"ok": False, "error": {"code": "invalid_input"}}
    except OSError:
        return {"ok": False, "error": {"code": "storage_error"}}
