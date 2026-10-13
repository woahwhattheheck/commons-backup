from __future__ import annotations
import hashlib, json, sys
from pathlib import Path

EXPECTED_SCHEMA = "commons.multi-framework-evidence-freshness-commercial-offer/v1"
EXPECTED_SAMPLE_SCHEMA = "commons.multi-framework-evidence-freshness-commercial-sample/v1"
EXPECTED_MERGE = "183aa75b65cdec2cca6cf95a4d2e0b7d9674fd3c"
EXPECTED_CORPUS = "bb97f376875421b13762aa2297e9620bb68bd019b47a13f25d80f6d6672bd5a0"
EXPECTED_COUNTS = {"REUSABLE":240,"STALE":50,"SCOPE_MISMATCH":40,"MISSING_OWNER":35,"INCOMPLETE":35}
EXPECTED_OFFER_SHA256 = "1fb6379d7f3ff326f13f020fbfea122db4edf45e09b9a98698debe777a52fd66"
EXPECTED_SAMPLE_SHA256 = "3ab5cd82edb18f5c9d2fe923cf7c4f04d1bfcae0c5501b1708ec174659a294c8"

class CommercialPacketError(ValueError): pass

def _pairs(pairs):
    out={}
    for k,v in pairs:
        if k in out: raise CommercialPacketError(f"duplicate_json_key:{k}")
        out[k]=v
    return out

def _load(path):
    raw=Path(path).read_bytes()
    if len(raw)>1_000_000: raise CommercialPacketError("file_too_large")
    try: text=raw.decode("utf-8","strict")
    except UnicodeDecodeError as exc: raise CommercialPacketError("invalid_utf8") from exc
    try:
        return json.loads(text, object_pairs_hook=_pairs,
                          parse_constant=lambda tok: (_ for _ in ()).throw(CommercialPacketError(f"non_finite:{tok}")))
    except json.JSONDecodeError as exc:
        raise CommercialPacketError("invalid_json") from exc

def _canon(o): return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",",":")).encode()
def _sha(o): return hashlib.sha256(_canon(o)).hexdigest()
def _exact_dict(o, keys, where):
    if type(o) is not dict: raise CommercialPacketError(f"{where}:object_required")
    if set(o)!=set(keys): raise CommercialPacketError(f"{where}:unexpected_keys")

def verify(offer_path, sample_path):
    oe=_load(offer_path); se=_load(sample_path)
    _exact_dict(oe, {"offer","offer_sha256"}, "offer_envelope")
    _exact_dict(se, {"sample","sample_sha256"}, "sample_envelope")
    offer=oe["offer"]; sample=se["sample"]
    if _sha(offer)!=oe["offer_sha256"]: raise CommercialPacketError("offer_digest_mismatch")
    if _sha(sample)!=se["sample_sha256"]: raise CommercialPacketError("sample_digest_mismatch")
    if offer.get("schema")!=EXPECTED_SCHEMA: raise CommercialPacketError("offer_schema")
    if sample.get("schema")!=EXPECTED_SAMPLE_SCHEMA: raise CommercialPacketError("sample_schema")
    if offer.get("price")!={"currency":"USD","amount_cents":350000,"status":"TEST_PRICE_NOT_ACCEPTED"}:
        raise CommercialPacketError("diagnostic_price")
    if offer.get("scope",{}).get("max_evidence_objects")!=500: raise CommercialPacketError("scope_ceiling")
    integ=offer.get("optional_integration",{}).get("price")
    if integ!={"currency":"USD","amount_cents":1000000,"status":"TEST_PRICE_NOT_ACCEPTED"}:
        raise CommercialPacketError("integration_price")
    prov=offer.get("acceptance",{}).get("engine_provenance",{})
    if prov.get("merge_commit")!=EXPECTED_MERGE: raise CommercialPacketError("engine_merge")
    if prov.get("golden_corpus_sha256")!=EXPECTED_CORPUS: raise CommercialPacketError("corpus_digest")
    if prov.get("golden_object_count")!=400: raise CommercialPacketError("golden_count")
    if prov.get("golden_state_counts")!=EXPECTED_COUNTS: raise CommercialPacketError("golden_distribution")
    if sample.get("offer_sha256")!=oe["offer_sha256"]: raise CommercialPacketError("sample_offer_binding")
    if sample.get("engine_provenance")!=prov: raise CommercialPacketError("sample_engine_binding")
    if sample.get("synthetic") is not True or sample.get("contains_buyer_data") is not False:
        raise CommercialPacketError("sample_data_posture")
    summary=sample.get("summary",{})
    if summary.get("objects_evaluated")!=400 or summary.get("counts")!=EXPECTED_COUNTS:
        raise CommercialPacketError("sample_distribution")
    if summary.get("reusable_rate_basis_points")!=6000: raise CommercialPacketError("sample_rate")
    auth=offer.get("authority")
    expected_auth={"buyer_acceptance":False,"audit_opinion":False,"certification":False,"payment_received":False,"revenue_recognized":False}
    if auth!=expected_auth: raise CommercialPacketError("authority_escalation")
    if oe["offer_sha256"]!=EXPECTED_OFFER_SHA256: raise CommercialPacketError("offer_contract_mismatch")
    if se["sample_sha256"]!=EXPECTED_SAMPLE_SHA256: raise CommercialPacketError("sample_contract_mismatch")
    return oe["offer_sha256"], se["sample_sha256"]

def main(argv=None):
    argv=sys.argv[1:] if argv is None else argv
    if len(argv)!=2:
        print("usage: verify_commercial.py OFFER_JSON SAMPLE_JSON", file=sys.stderr); return 2
    try:
        od,sd=verify(argv[0],argv[1])
    except (CommercialPacketError,OSError) as exc:
        print(f"HOLD:{exc}"); return 2
    print(f"VERIFIED:{od}:{sd}"); return 0

if __name__=="__main__": raise SystemExit(main())
