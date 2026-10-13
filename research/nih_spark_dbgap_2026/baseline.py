from __future__ import annotations

from typing import Any, Iterable, Mapping

from .contracts import Corpus, ResourceManifest
from .core import (
    ONT_NONE, SCHEMA_RUN_RECEIPT, ContractError, _identifier, _int, _string, canonical_bytes,
    load_json_strict, load_json_strict_bytes, semantic_sha256, sha256_bytes, text_digest,
)
from .track1 import evaluate_track1, rank_concepts, track1_predict
from .track2 import evaluate_track2, track2_rank

def build_run_receipt(*, track: int, corpus: Corpus, resources: ResourceManifest, input_obj: Any, output_obj: Any, source_version: str, policy: Mapping[str, Any]) -> dict[str, Any]:
    _int(track, "track", minimum=1, maximum=2)
    source_version = _identifier(source_version, "source_version")
    payload = {
        "schema": SCHEMA_RUN_RECEIPT,
        "track": track,
        "corpus_sha256": corpus.digest,
        "resources_sha256": resources.digest,
        "input_sha256": semantic_sha256(input_obj),
        "output_sha256": semantic_sha256(output_obj),
        "policy_sha256": semantic_sha256(dict(policy)),
        "source_version": source_version,
        "network_required": False,
        "controlled_access_data_used": False,
        "official_score_claimed": False,
    }
    payload["receipt_sha256"] = semantic_sha256(payload)
    return payload


def verify_run_receipt(receipt: Any, *, track: int, corpus: Corpus, resources: ResourceManifest, input_obj: Any, output_obj: Any, source_version: str, policy: Mapping[str, Any]) -> bool:
    expected = build_run_receipt(track=track, corpus=corpus, resources=resources, input_obj=input_obj, output_obj=output_obj, source_version=source_version, policy=policy)
    return type(receipt) is dict and receipt == expected


def scan_source_for_query_keyed_hardcoding(source_text: str, query_ids: Iterable[str]) -> list[str]:
    """Conservative anti-gaming guard: challenge/synthetic query IDs must not appear in runtime source."""
    _string(source_text, "source_text", max_len=2_000_000, allow_empty=True)
    hits: list[str] = []
    for qid in sorted(set(query_ids)):
        _identifier(qid, "query_id")
        if qid in source_text:
            hits.append(qid)
    return hits
