#!/usr/bin/env python3
"""Provider-authenticated append-only delta ledger for canonical Muse v2 receipts.

Each provider generation stores one fixed-size delta record. Verification walks the
single-parent ledger chain once, reads each manifest and newly-added receipt by
exact provider path, and authenticates adjacent commit diffs. It never recursively
enumerates the repository tree or reparses cumulative historical manifests.
"""
from __future__ import annotations

import argparse, base64, hashlib, json, os, re, sys, urllib.error, urllib.parse, urllib.request
from typing import Any, Mapping
from tools.outbound_send_guard import muse_election_v2 as gate

PROVIDER_OWNER = "woahwhattheheck"
PROVIDER_REPO = "commons"
PROVIDER_REPO_FULL_NAME = PROVIDER_OWNER + "/" + PROVIDER_REPO
PROVIDER_API = "https://api.github.com"
PROVIDER_REF = "refs/heads/muse-provider-receipt-ledger-v1"
PROVIDER_BRANCH = "muse-provider-receipt-ledger-v1"
TOKEN_ENV = "MUSE_LEDGER_GITHUB_TOKEN"
LEDGER_SCHEMA = "outbound-muse-provider-receipt-ledger/v1"
ENTRY_SCHEMA = "outbound-muse-provider-receipt-ledger-entry/v1"
PROOF_SCHEMA = "outbound-muse-provider-receipt-ledger-proof/v1"
PREFIX_SCHEMA = "outbound-muse-provider-receipt-ledger-prefix/v1"
PROVIDER_MANIFEST_SCHEMA = "outbound-muse-provider-receipt-ledger-delta-manifest/v1"
MANIFEST_PATH = "provider/muse_receipt_ledger_v1/manifest.json"
RECEIPT_PREFIX = "provider/muse_receipt_ledger_v1/receipts/"
MAX_ENTRIES = 4096
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_LEDGER_FILE_BYTES = 256 * 1024
HEX40_64_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
ENTRY_FIELDS = {"schema_version","ordinal","receipt_sha256","receipt_path","request_sha256","request_id","publication_key","candidate_sha256","decision","compiled_at","selection_message_ts"}
MANIFEST_FIELDS = {"schema_version","provider_repo","provider_ref","generation","genesis_parent_sha","previous_head_sha","entries","complete_prefix_sha256"}
PROVIDER_MANIFEST_FIELDS = {"schema_version","provider_repo","provider_ref","generation","genesis_parent_sha","previous_head_sha","previous_prefix_sha256","entry","complete_prefix_sha256"}
PROOF_FIELDS = {"schema_version","provider_repo","provider_ref","provider_head_sha","generation","entry_count","complete_prefix_sha256","manifest_sha256","request_sha256","request_id","publication_key","candidate_sha256","prior_receipt_ledger_authenticated","ledger_complete","terminal_election_authorized","requires_current_worker_lease_possession","requires_fresh_provider_preflight","external_send_authorized","side_effects_authorized"}

class MuseProviderReceiptLedgerError(ValueError):
    pass


def _strict_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out: raise MuseProviderReceiptLedgerError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _parse_json_bytes(raw: bytes, label: str) -> Any:
    if type(raw) is not bytes: raise MuseProviderReceiptLedgerError(f"{label}: bytes required")
    try: text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as exc: raise MuseProviderReceiptLedgerError(f"{label}: UTF-8 required") from exc
    try:
        return json.loads(text, object_pairs_hook=_strict_pairs,
                          parse_constant=lambda x: (_ for _ in ()).throw(MuseProviderReceiptLedgerError(f"{label}: non-finite {x}")))
    except MuseProviderReceiptLedgerError: raise
    except json.JSONDecodeError as exc: raise MuseProviderReceiptLedgerError(f"{label}: invalid JSON") from exc


def _canon(value: Any) -> bytes:
    try: text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc: raise MuseProviderReceiptLedgerError("value is not canonical JSON") from exc
    return (text + "\n").encode()


def _digest(value: Any) -> str: return hashlib.sha256(_canon(value)).hexdigest()
def _sha(value: Any, label: str) -> str:
    if type(value) is not str or not HEX40_64_RE.fullmatch(value): raise MuseProviderReceiptLedgerError(f"{label}: Git object id required")
    return value
def _hex64(value: Any, label: str) -> str:
    if type(value) is not str or not HEX64_RE.fullmatch(value): raise MuseProviderReceiptLedgerError(f"{label}: SHA-256 required")
    return value
def _text(value: Any, label: str, max_len: int = 256) -> str:
    if type(value) is not str or not value or len(value) > max_len or any(ord(c) < 0x20 or ord(c) == 0x7f for c in value):
        raise MuseProviderReceiptLedgerError(f"{label}: bounded printable string required")
    return value
def _uint(value: Any, label: str, limit: int) -> int:
    if type(value) is bool or type(value) is not int or value < 0 or value > limit: raise MuseProviderReceiptLedgerError(f"{label}: integer out of range")
    return value
def _exact(obj: Any, fields: set[str], label: str) -> dict[str, Any]:
    if type(obj) is not dict or set(obj) != fields: raise MuseProviderReceiptLedgerError(f"{label}: exact fields required")
    return obj


def _token() -> str:
    value = os.environ.get(TOKEN_ENV)
    if type(value) is not str or not value or len(value) > 4096 or any(ord(c) < 0x21 or ord(c) > 0x7e for c in value):
        raise MuseProviderReceiptLedgerError(f"{TOKEN_ENV}: printable token required")
    return value


def _api(method: str, path: str, *, body: Mapping[str, Any] | None = None, token: str) -> Any:
    if method not in {"GET","POST","PATCH"}: raise MuseProviderReceiptLedgerError("unsupported provider method")
    if not path.startswith(f"/repos/{PROVIDER_OWNER}/{PROVIDER_REPO}/"): raise MuseProviderReceiptLedgerError("provider path escaped fixed repository")
    req = urllib.request.Request(PROVIDER_API + path, data=None if body is None else _canon(body),
        headers={"Accept":"application/vnd.github+json","Authorization":"Bearer "+token,"Content-Type":"application/json","X-GitHub-Api-Version":"2022-11-28"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as response: raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc: raise MuseProviderReceiptLedgerError(f"GitHub {method} {path}: HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc: raise MuseProviderReceiptLedgerError(f"GitHub {method} {path}: transport failure") from exc
    if len(raw) > MAX_RESPONSE_BYTES: raise MuseProviderReceiptLedgerError("provider response too large")
    if not raw: return {}
    try: return json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc: raise MuseProviderReceiptLedgerError("provider returned invalid JSON") from exc


def _get_ref(token: str) -> str:
    value = _api("GET", f"/repos/{PROVIDER_OWNER}/{PROVIDER_REPO}/git/ref/heads/{PROVIDER_BRANCH}", token=token)
    try: return _sha(value["object"]["sha"], "provider ref sha")
    except (KeyError, TypeError) as exc: raise MuseProviderReceiptLedgerError("malformed provider ref") from exc
def _get_default_head(token: str) -> str:
    value = _api("GET", f"/repos/{PROVIDER_OWNER}/{PROVIDER_REPO}/git/ref/heads/main", token=token)
    try: return _sha(value["object"]["sha"], "main ref sha")
    except (KeyError, TypeError) as exc: raise MuseProviderReceiptLedgerError("malformed main ref") from exc
def _get_commit(token: str, sha: str, *, require_single_parent: bool = True) -> dict[str, Any]:
    sha = _sha(sha, "commit sha")
    value = _api("GET", f"/repos/{PROVIDER_OWNER}/{PROVIDER_REPO}/git/commits/{sha}", token=token)
    try:
        tree = _sha(value["tree"]["sha"], "tree sha"); parents = [_sha(x["sha"], "parent sha") for x in value["parents"]]
    except (KeyError, TypeError) as exc: raise MuseProviderReceiptLedgerError("malformed provider commit") from exc
    if require_single_parent and len(parents) != 1: raise MuseProviderReceiptLedgerError("ledger commit must have one parent")
    if not parents: raise MuseProviderReceiptLedgerError("provider commit must have at least one parent")
    return {"sha":sha,"tree_sha":tree,"parent_sha":parents[0] if len(parents)==1 else None,"parent_shas":parents}


def _content_file(token: str, path: str, ref: str, label: str) -> tuple[str, bytes]:
    safe_path = "/".join(urllib.parse.quote(part, safe="") for part in path.split("/"))
    query = urllib.parse.urlencode({"ref": _sha(ref,"content ref")})
    value = _api("GET", f"/repos/{PROVIDER_OWNER}/{PROVIDER_REPO}/contents/{safe_path}?{query}", token=token)
    if type(value) is not dict or value.get("type") != "file" or value.get("path") != path or value.get("encoding") != "base64" or type(value.get("content")) is not str:
        raise MuseProviderReceiptLedgerError(f"{label}: malformed exact-path provider file")
    blob = _sha(value.get("sha"), f"{label} blob")
    try: raw = base64.b64decode("".join(value["content"].split()), validate=True)
    except (ValueError, TypeError) as exc: raise MuseProviderReceiptLedgerError(f"{label}: invalid base64") from exc
    if len(raw) > MAX_LEDGER_FILE_BYTES: raise MuseProviderReceiptLedgerError(f"{label}: provider file too large")
    return blob, raw


def _compare_paths(token: str, parent: str, head: str) -> dict[str,str]:
    parent = _sha(parent,"compare parent"); head = _sha(head,"compare head")
    value = _api("GET", f"/repos/{PROVIDER_OWNER}/{PROVIDER_REPO}/compare/{parent}...{head}", token=token)
    if type(value) is not dict or value.get("status") != "ahead" or value.get("ahead_by") != 1 or value.get("behind_by") != 0 or value.get("total_commits") != 1 or type(value.get("files")) is not list:
        raise MuseProviderReceiptLedgerError("adjacent ledger compare malformed")
    out: dict[str,str] = {}
    for row in value["files"]:
        if type(row) is not dict: raise MuseProviderReceiptLedgerError("adjacent ledger compare row malformed")
        path = _text(row.get("filename"),"compare path",4096); status = row.get("status")
        if status not in {"added","modified","removed","renamed","copied","changed"} or path in out:
            raise MuseProviderReceiptLedgerError("adjacent ledger compare row invalid")
        out[path] = status
    return out


def _receipt_path(sha: str) -> str: return RECEIPT_PREFIX + _hex64(sha,"receipt sha256") + ".json"
EMPTY_PREFIX_SHA256 = _digest({"schema_version":PREFIX_SCHEMA,"empty":True})
def _prefix_step(previous: str, entry: Mapping[str,Any]) -> str:
    return _digest({"schema_version":PREFIX_SCHEMA,"previous_prefix_sha256":_hex64(previous,"previous prefix"),"entry":entry})
def _prefix_digest(entries) -> str:
    digest = EMPTY_PREFIX_SHA256
    for entry in entries: digest = _prefix_step(digest,entry)
    return digest


def _request_facts(request: Mapping[str,Any]) -> dict[str,str]:
    try: payload, request_sha, _ = gate._validate_request(request)
    except (KeyError, TypeError, ValueError) as exc: raise MuseProviderReceiptLedgerError("request: canonical v2 verification failed") from exc
    return {"request_sha256":_hex64(request_sha,"request sha"),"request_id":_text(payload["request_id"],"request id",160),"publication_key":_hex64(payload["publication_key"],"publication key"),"candidate_sha256":_hex64(payload["candidate_sha256"],"candidate sha")}


def _receipt_facts(receipt: Mapping[str,Any]) -> dict[str,Any]:
    if not gate.verify_receipt(receipt) or type(receipt) is not dict or set(receipt) != {"payload","receipt_sha256"}: raise MuseProviderReceiptLedgerError("canonical Muse v2 receipt required")
    p = receipt["payload"]; raw = _canon(receipt); decision = p.get("decision"); selection = p.get("selection_message_ts")
    if decision not in {"SELECTED","NOT_SELECTED","HOLD"} or (selection is not None and type(selection) is not str): raise MuseProviderReceiptLedgerError("receipt metadata invalid")
    return {"receipt_bytes":raw,"receipt_sha256":hashlib.sha256(raw).hexdigest(),"request_sha256":_hex64(p.get("request_sha256"),"receipt request sha"),"request_id":_text(p.get("request_id"),"receipt request id",160),"publication_key":_hex64(p.get("publication_key"),"receipt publication key"),"candidate_sha256":_hex64(p.get("candidate_sha256"),"receipt candidate sha"),"decision":decision,"compiled_at":_text(p.get("compiled_at"),"compiled at",32),"selection_message_ts":selection}


def _entry(facts: Mapping[str,Any], ordinal: int) -> dict[str,Any]:
    _uint(ordinal,"ordinal",MAX_ENTRIES-1)
    return {"schema_version":ENTRY_SCHEMA,"ordinal":ordinal,"receipt_sha256":facts["receipt_sha256"],"receipt_path":_receipt_path(facts["receipt_sha256"]),"request_sha256":facts["request_sha256"],"request_id":facts["request_id"],"publication_key":facts["publication_key"],"candidate_sha256":facts["candidate_sha256"],"decision":facts["decision"],"compiled_at":facts["compiled_at"],"selection_message_ts":facts["selection_message_ts"]}


def _validate_entry(raw: Any, ordinal: int) -> dict[str,Any]:
    row = _exact(raw,ENTRY_FIELDS,f"entry[{ordinal}]"); _uint(row["ordinal"],f"entry[{ordinal}].ordinal",MAX_ENTRIES-1)
    if row["schema_version"] != ENTRY_SCHEMA or row["ordinal"] != ordinal: raise MuseProviderReceiptLedgerError("entry schema/ordinal mismatch")
    out = {"schema_version":ENTRY_SCHEMA,"ordinal":ordinal,"receipt_sha256":_hex64(row["receipt_sha256"],"receipt sha"),"receipt_path":_text(row["receipt_path"],"receipt path",512),"request_sha256":_hex64(row["request_sha256"],"request sha"),"request_id":_text(row["request_id"],"request id",160),"publication_key":_hex64(row["publication_key"],"publication key"),"candidate_sha256":_hex64(row["candidate_sha256"],"candidate sha"),"decision":row["decision"],"compiled_at":_text(row["compiled_at"],"compiled at",32),"selection_message_ts":row["selection_message_ts"]}
    if out["receipt_path"] != _receipt_path(out["receipt_sha256"]) or out["decision"] not in {"SELECTED","NOT_SELECTED","HOLD"} or (out["selection_message_ts"] is not None and type(out["selection_message_ts"]) is not str): raise MuseProviderReceiptLedgerError("entry metadata invalid")
    return out


def _provider_manifest(generation: int, genesis: str, previous: str|None, previous_prefix: str|None, entry: Mapping[str,Any]|None) -> dict[str,Any]:
    generation = _uint(generation,"generation",MAX_ENTRIES); genesis = _sha(genesis,"genesis sha")
    if generation == 0:
        if previous is not None or previous_prefix is not None or entry is not None: raise MuseProviderReceiptLedgerError("generation zero delta must be empty")
        complete = EMPTY_PREFIX_SHA256
    else:
        previous = _sha(previous,"previous head"); previous_prefix = _hex64(previous_prefix,"previous prefix"); entry = _validate_entry(entry,generation-1); complete = _prefix_step(previous_prefix,entry)
    return {"schema_version":PROVIDER_MANIFEST_SCHEMA,"provider_repo":PROVIDER_REPO_FULL_NAME,"provider_ref":PROVIDER_REF,"generation":generation,"genesis_parent_sha":genesis,"previous_head_sha":previous,"previous_prefix_sha256":previous_prefix,"entry":entry,"complete_prefix_sha256":complete}


def _validate_provider_manifest(raw: Any) -> dict[str,Any]:
    value = _exact(raw,PROVIDER_MANIFEST_FIELDS,"provider manifest")
    if value["schema_version"] != PROVIDER_MANIFEST_SCHEMA or value["provider_repo"] != PROVIDER_REPO_FULL_NAME or value["provider_ref"] != PROVIDER_REF: raise MuseProviderReceiptLedgerError("provider manifest identity mismatch")
    generation = _uint(value["generation"],"generation",MAX_ENTRIES); genesis = _sha(value["genesis_parent_sha"],"genesis sha")
    manifest = _provider_manifest(generation,genesis,value["previous_head_sha"],value["previous_prefix_sha256"],value["entry"])
    if _hex64(value["complete_prefix_sha256"],"complete prefix") != manifest["complete_prefix_sha256"]: raise MuseProviderReceiptLedgerError("provider manifest prefix mismatch")
    return manifest


def _validate_unique_entries(entries: list[Mapping[str,Any]]) -> None:
    for field in ("receipt_sha256","request_sha256"):
        vals=[e[field] for e in entries]
        if len(vals)!=len(set(vals)): raise MuseProviderReceiptLedgerError(f"duplicate {field}")
    pairs=[(e["request_id"],e["candidate_sha256"]) for e in entries]
    if len(pairs)!=len(set(pairs)): raise MuseProviderReceiptLedgerError("duplicate request generation")
    selected=[e["selection_message_ts"] for e in entries if e["selection_message_ts"] is not None]
    if len(selected)!=len(set(selected)): raise MuseProviderReceiptLedgerError("duplicate selection evidence")


def _manifest_view(generation: int, genesis: str, previous: str|None, entries: list[Mapping[str,Any]], complete_prefix: str) -> dict[str,Any]:
    if len(entries) != generation: raise MuseProviderReceiptLedgerError("materialized generation mismatch")
    if _prefix_digest(entries) != _hex64(complete_prefix,"materialized prefix"): raise MuseProviderReceiptLedgerError("materialized prefix mismatch")
    return {"schema_version":LEDGER_SCHEMA,"provider_repo":PROVIDER_REPO_FULL_NAME,"provider_ref":PROVIDER_REF,"generation":generation,"genesis_parent_sha":_sha(genesis,"genesis sha"),"previous_head_sha":previous,"entries":list(entries),"complete_prefix_sha256":complete_prefix}


def _validate_manifest(raw: Any) -> dict[str,Any]:
    value = _exact(raw,MANIFEST_FIELDS,"manifest")
    if value["schema_version"] != LEDGER_SCHEMA or value["provider_repo"] != PROVIDER_REPO_FULL_NAME or value["provider_ref"] != PROVIDER_REF: raise MuseProviderReceiptLedgerError("manifest identity mismatch")
    generation=_uint(value["generation"],"generation",MAX_ENTRIES); rows=value["entries"]
    if type(rows) is not list or len(rows)!=generation: raise MuseProviderReceiptLedgerError("manifest generation mismatch")
    entries=[_validate_entry(row,i) for i,row in enumerate(rows)]; _validate_unique_entries(entries)
    previous=value["previous_head_sha"]
    if generation==0:
        if previous is not None: raise MuseProviderReceiptLedgerError("generation zero previous head must be null")
    else: previous=_sha(previous,"previous head")
    return _manifest_view(generation,_sha(value["genesis_parent_sha"],"genesis sha"),previous,entries,_hex64(value["complete_prefix_sha256"],"prefix sha"))


def _read_provider_manifest(token: str, head: str) -> tuple[dict[str,Any],dict[str,Any]]:
    commit=_get_commit(token,head); _blob,raw=_content_file(token,MANIFEST_PATH,head,"manifest")
    value=_parse_json_bytes(raw,"manifest")
    if _canon(value)!=raw: raise MuseProviderReceiptLedgerError("provider manifest not canonical")
    return _validate_provider_manifest(value),commit


def _read_receipt_for_entry(token: str, head: str, entry: Mapping[str,Any]) -> Mapping[str,Any]:
    _blob,raw=_content_file(token,entry["receipt_path"],head,entry["receipt_path"])
    obj=_parse_json_bytes(raw,entry["receipt_path"])
    if _canon(obj)!=raw or hashlib.sha256(raw).hexdigest()!=entry["receipt_sha256"]: raise MuseProviderReceiptLedgerError("receipt bytes/digest mismatch")
    facts=_receipt_facts(obj)
    for key in ("receipt_sha256","request_sha256","request_id","publication_key","candidate_sha256","decision","compiled_at","selection_message_ts"):
        if facts[key]!=entry[key]: raise MuseProviderReceiptLedgerError(f"receipt metadata mismatch: {key}")
    return obj


def _verify_remote_complete_prefix_state(token: str) -> dict[str,Any]:
    start=_get_ref(token); head=start; newer=None; current=None; current_previous=None; entries_rev=[]; receipts_rev=[]; expected_generation=None
    for _depth in range(MAX_ENTRIES+1):
        manifest,commit=_read_provider_manifest(token,head)
        if expected_generation is None:
            expected_generation=manifest["generation"]; current=manifest; current_previous=manifest["previous_head_sha"]
        if manifest["generation"]!=expected_generation: raise MuseProviderReceiptLedgerError("ledger generation gap")
        if newer is not None:
            if newer["previous_head_sha"]!=head or newer["generation"]!=manifest["generation"]+1 or newer["genesis_parent_sha"]!=manifest["genesis_parent_sha"] or newer["previous_prefix_sha256"]!=manifest["complete_prefix_sha256"]:
                raise MuseProviderReceiptLedgerError("non-append delta ledger history")
        changed=_compare_paths(token,commit["parent_sha"],head)
        if manifest["generation"]==0:
            if commit["parent_sha"]!=manifest["genesis_parent_sha"] or changed!={MANIFEST_PATH:"added"}: raise MuseProviderReceiptLedgerError("invalid ledger genesis commit")
            break
        entry=manifest["entry"]
        expected={MANIFEST_PATH:"modified",entry["receipt_path"]:"added"}
        if commit["parent_sha"]!=manifest["previous_head_sha"] or changed!=expected: raise MuseProviderReceiptLedgerError("ledger generation changed undeclared paths")
        receipts_rev.append(_read_receipt_for_entry(token,head,entry)); entries_rev.append(entry)
        newer=manifest; head=commit["parent_sha"]; expected_generation-=1
    else: raise MuseProviderReceiptLedgerError("ledger chain too long")
    entries=list(reversed(entries_rev)); receipts=list(reversed(receipts_rev)); _validate_unique_entries(entries)
    if current is None or len(entries)!=current["generation"]: raise MuseProviderReceiptLedgerError("ledger materialization mismatch")
    view=_manifest_view(current["generation"],current["genesis_parent_sha"],current_previous,entries,current["complete_prefix_sha256"])
    if _get_ref(token)!=start: raise MuseProviderReceiptLedgerError("provider head changed during verification")
    return {"provider_head_sha":start,"manifest":view,"provider_manifest":current,"receipts":receipts}


def verify_remote_complete_prefix(*, token: str|None=None) -> dict[str,Any]:
    token=_token() if token is None else token; state=_verify_remote_complete_prefix_state(token)
    return {"provider_head_sha":state["provider_head_sha"],"manifest":state["manifest"]}


def _post_tree(token: str, base: str, files: Mapping[str,bytes]) -> str:
    rows=[{"path":p,"mode":"100644","type":"blob","content":raw.decode("utf-8","strict")} for p,raw in sorted(files.items())]
    value=_api("POST",f"/repos/{PROVIDER_OWNER}/{PROVIDER_REPO}/git/trees",body={"base_tree":_sha(base,"base tree"),"tree":rows},token=token)
    try:return _sha(value["sha"],"created tree")
    except (KeyError,TypeError) as exc: raise MuseProviderReceiptLedgerError("create-tree malformed") from exc
def _post_commit(token: str, tree: str, parent: str, generation: int) -> str:
    value=_api("POST",f"/repos/{PROVIDER_OWNER}/{PROVIDER_REPO}/git/commits",body={"message":f"Muse receipt ledger generation {generation}","tree":_sha(tree,"tree"),"parents":[_sha(parent,"parent")]},token=token)
    try:return _sha(value["sha"],"created commit")
    except (KeyError,TypeError) as exc: raise MuseProviderReceiptLedgerError("create-commit malformed") from exc


def initialize_remote_ledger(*, token: str|None=None) -> dict[str,Any]:
    token=_token() if token is None else token; genesis=_get_default_head(token); base=_get_commit(token,genesis,require_single_parent=False)
    manifest=_provider_manifest(0,genesis,None,None,None); tree=_post_tree(token,base["tree_sha"],{MANIFEST_PATH:_canon(manifest)}); commit=_post_commit(token,tree,genesis,0)
    value=_api("POST",f"/repos/{PROVIDER_OWNER}/{PROVIDER_REPO}/git/refs",body={"ref":PROVIDER_REF,"sha":commit},token=token)
    try: observed=_sha(value["object"]["sha"],"created ref")
    except (KeyError,TypeError) as exc: raise MuseProviderReceiptLedgerError("create-ref malformed") from exc
    if observed!=commit or _get_ref(token)!=commit: raise MuseProviderReceiptLedgerError("exclusive ref readback mismatch")
    return verify_remote_complete_prefix(token=token)


def append_receipt(receipt: Mapping[str,Any], *, token: str|None=None) -> dict[str,Any]:
    token=_token() if token is None else token; state=_verify_remote_complete_prefix_state(token); old=state["provider_head_sha"]; view=state["manifest"]
    if view["generation"]>=MAX_ENTRIES: raise MuseProviderReceiptLedgerError("ledger capacity exhausted")
    facts=_receipt_facts(receipt); entry=_entry(facts,view["generation"])
    if any(e["receipt_sha256"]==entry["receipt_sha256"] or e["request_sha256"]==entry["request_sha256"] or (e["request_id"],e["candidate_sha256"])==(entry["request_id"],entry["candidate_sha256"]) or (entry["selection_message_ts"] is not None and e["selection_message_ts"]==entry["selection_message_ts"]) for e in view["entries"]):
        raise MuseProviderReceiptLedgerError("duplicate receipt/request/selection evidence")
    new=_provider_manifest(view["generation"]+1,view["genesis_parent_sha"],old,view["complete_prefix_sha256"],entry)
    base=_get_commit(token,old); tree=_post_tree(token,base["tree_sha"],{entry["receipt_path"]:facts["receipt_bytes"],MANIFEST_PATH:_canon(new)}); commit=_post_commit(token,tree,old,new["generation"])
    _api("PATCH",f"/repos/{PROVIDER_OWNER}/{PROVIDER_REPO}/git/refs/heads/{PROVIDER_BRANCH}",body={"sha":commit,"force":False},token=token)
    if _get_ref(token)!=commit: raise MuseProviderReceiptLedgerError("provider CAS/readback mismatch")
    return verify_remote_complete_prefix(token=token)


def _build_request_bound_proof_with_state(request: Mapping[str,Any], token: str):
    req=_request_facts(request); state=_verify_remote_complete_prefix_state(token); manifest=state["manifest"]
    if any(e["request_sha256"]==req["request_sha256"] for e in manifest["entries"]): raise MuseProviderReceiptLedgerError("current request already in prior ledger")
    payload={"schema_version":PROOF_SCHEMA,"provider_repo":PROVIDER_REPO_FULL_NAME,"provider_ref":PROVIDER_REF,"provider_head_sha":state["provider_head_sha"],"generation":manifest["generation"],"entry_count":len(manifest["entries"]),"complete_prefix_sha256":manifest["complete_prefix_sha256"],"manifest_sha256":_digest(manifest),**req,"prior_receipt_ledger_authenticated":True,"ledger_complete":True,"terminal_election_authorized":False,"requires_current_worker_lease_possession":True,"requires_fresh_provider_preflight":True,"external_send_authorized":False,"side_effects_authorized":False}
    return {"payload":payload,"proof_sha256":_digest(payload)},state


def build_request_bound_proof(request: Mapping[str,Any], *, token: str|None=None) -> dict[str,Any]:
    token=_token() if token is None else token; proof,_state=_build_request_bound_proof_with_state(request,token); return proof


def _verify_request_bound_proof_with_state(request: Mapping[str,Any], proof: Mapping[str,Any], token: str):
    try:
        if type(proof) is not dict or set(proof)!={"payload","proof_sha256"}: return False,None
        p=_exact(proof["payload"],PROOF_FIELDS,"proof"); _sha(p["provider_head_sha"],"proof head"); _uint(p["generation"],"proof generation",MAX_ENTRIES); _uint(p["entry_count"],"proof entry count",MAX_ENTRIES)
        for key in ("complete_prefix_sha256","manifest_sha256","request_sha256","publication_key","candidate_sha256"): _hex64(p[key],f"proof {key}")
        _text(p["request_id"],"proof request id",160)
        if p["schema_version"]!=PROOF_SCHEMA or p["provider_repo"]!=PROVIDER_REPO_FULL_NAME or p["provider_ref"]!=PROVIDER_REF or proof["proof_sha256"]!=_digest(p): return False,None
        if p["prior_receipt_ledger_authenticated"] is not True or p["ledger_complete"] is not True or p["terminal_election_authorized"] is not False or p["requires_current_worker_lease_possession"] is not True or p["requires_fresh_provider_preflight"] is not True or p["external_send_authorized"] is not False or p["side_effects_authorized"] is not False: return False,None
        req=_request_facts(request)
        if any(p[k]!=req[k] for k in req): return False,None
        expected,state=_build_request_bound_proof_with_state(request,token)
        if expected!=proof: return False,None
        return True,state
    except (MuseProviderReceiptLedgerError,KeyError,TypeError,ValueError,OSError): return False,None


def verify_request_bound_proof(request: Mapping[str,Any], proof: Mapping[str,Any], *, token: str|None=None) -> bool:
    token=_token() if token is None else token; ok,_state=_verify_request_bound_proof_with_state(request,proof,token); return ok


def load_prior_receipts(request: Mapping[str,Any], proof: Mapping[str,Any], *, token: str|None=None):
    token=_token() if token is None else token; ok,state=_verify_request_bound_proof_with_state(request,proof,token)
    if not ok: raise MuseProviderReceiptLedgerError("ledger proof is not current")
    if _get_ref(token)!=state["provider_head_sha"]: raise MuseProviderReceiptLedgerError("provider head changed during load")
    return list(state["receipts"])


def verify_terminal_coordination(request: Mapping[str,Any], slack_provider_receipt: Mapping[str,Any], ledger_proof: Mapping[str,Any], *, token: str|None=None) -> bool:
    try: from tools.outbound_send_guard import muse_slack_provider_v1 as slack_provider
    except ImportError: return False
    try:
        if not slack_provider.verify_provider_evidence(request,slack_provider_receipt) or not verify_request_bound_proof(request,ledger_proof,token=token): return False
        req=_request_facts(request); sp=slack_provider_receipt.get("payload"); lp=ledger_proof.get("payload")
        if type(sp) is not dict or type(lp) is not dict: return False
        if sp.get("schema_version")!=slack_provider.PROVIDER_SCHEMA or sp.get("authority_mode")!=slack_provider.AUTHORITY_MODE or sp.get("visibility_model")!=slack_provider.VISIBILITY_MODEL: return False
        if sp.get("current_visible_effective_observation")!="SELECTED": return False
        if sp.get("deleted_history_authenticated") is not False or sp.get("requester_control_history_authenticated") is not False or sp.get("prior_receipt_ledger_authenticated") is not False or sp.get("terminal_election_authorized") is not False: return False
        if any(sp.get(k)!=req[k] or lp.get(k)!=req[k] for k in req): return False
        for p in (sp,lp):
            if p.get("external_send_authorized") is not False or p.get("side_effects_authorized") is not False or p.get("requires_current_worker_lease_possession") is not True or p.get("requires_fresh_provider_preflight") is not True: return False
        return True
    except (AttributeError,MuseProviderReceiptLedgerError,KeyError,TypeError,ValueError,OSError): return False


def _read(path: str, label: str):
    try:
        with open(path,"rb") as f: return _parse_json_bytes(f.read(),label)
    except OSError as exc: raise MuseProviderReceiptLedgerError(f"{label}: read failed") from exc
def _write(value): sys.stdout.buffer.write(_canon(value))
def _parser():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest="command",required=True); sub.add_parser("init")
    a=sub.add_parser("append"); a.add_argument("--receipt",required=True); q=sub.add_parser("proof"); q.add_argument("--request",required=True); v=sub.add_parser("verify-proof"); v.add_argument("--request",required=True); v.add_argument("--proof",required=True); return p
def main(argv=None):
    args=_parser().parse_args(argv)
    try:
        if args.command=="init": _write(initialize_remote_ledger()); return 0
        if args.command=="append": _write(append_receipt(_read(args.receipt,"receipt"))); return 0
        if args.command=="proof": _write(build_request_bound_proof(_read(args.request,"request"))); return 0
        ok=verify_request_bound_proof(_read(args.request,"request"),_read(args.proof,"proof")); _write({"valid":ok}); return 0 if ok else 2
    except (MuseProviderReceiptLedgerError,OSError,KeyError,TypeError,ValueError) as exc: print(f"ERROR: {exc}",file=sys.stderr); return 2

if __name__ == "__main__": raise SystemExit(main())
