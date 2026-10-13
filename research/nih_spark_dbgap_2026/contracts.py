from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .core import (
    ONT_NONE, SCHEMA_CORPUS, SCHEMA_RESOURCES, ContractError, _ALLOWED_RESOURCE_KINDS,
    _array, _exact_keys, _identifier, _object, _sha, _string, normalized_tokens,
    semantic_sha256, text_digest,
)

@dataclass(frozen=True)
class Concept:
    concept_id: str
    label: str
    synonyms: tuple[str, ...]

    @property
    def phrases(self) -> tuple[tuple[str, ...], ...]:
        return tuple(normalized_tokens(x) for x in (self.label, *self.synonyms))


@dataclass(frozen=True)
class Variable:
    study_id: str
    variable_id: str
    text: str


@dataclass(frozen=True)
class Study:
    study_id: str
    title: str
    description: str
    variable_ids: tuple[str, ...]


@dataclass(frozen=True)
class Corpus:
    studies: tuple[Study, ...]
    variables: tuple[Variable, ...]
    concepts: tuple[Concept, ...]
    digest: str

    @classmethod
    def from_obj(cls, raw: Any) -> "Corpus":
        root = _object(raw, "corpus")
        _exact_keys(root, {"schema", "studies", "variables", "concepts", "corpus_sha256"}, "corpus")
        if root["schema"] != SCHEMA_CORPUS:
            raise ContractError("unsupported corpus schema")

        study_rows = _array(root["studies"], "studies")
        variable_rows = _array(root["variables"], "variables")
        concept_rows = _array(root["concepts"], "concepts")
        if not study_rows or not variable_rows or not concept_rows:
            raise ContractError("studies, variables, and concepts must be non-empty")

        study_ids: set[str] = set()
        studies: list[Study] = []
        for i, item in enumerate(study_rows):
            row = _object(item, f"studies[{i}]")
            _exact_keys(row, {"study_id", "title", "description", "text_sha256"}, f"studies[{i}]")
            sid = _identifier(row["study_id"], f"studies[{i}].study_id")
            if sid in study_ids:
                raise ContractError(f"duplicate study_id: {sid}")
            study_ids.add(sid)
            title = _string(row["title"], f"studies[{i}].title", max_len=2048)
            desc = _string(row["description"], f"studies[{i}].description", max_len=32_768)
            expected = text_digest(title + "\n" + desc)
            if _sha(row["text_sha256"], f"studies[{i}].text_sha256") != expected:
                raise ContractError(f"study text digest mismatch: {sid}")
            studies.append(Study(sid, title, desc, ()))

        variable_ids: set[tuple[str, str]] = set()
        variables: list[Variable] = []
        by_study: dict[str, list[str]] = {sid: [] for sid in study_ids}
        for i, item in enumerate(variable_rows):
            row = _object(item, f"variables[{i}]")
            _exact_keys(row, {"study_id", "variable_id", "text", "text_sha256"}, f"variables[{i}]")
            sid = _identifier(row["study_id"], f"variables[{i}].study_id")
            vid = _identifier(row["variable_id"], f"variables[{i}].variable_id")
            if sid not in study_ids:
                raise ContractError(f"variable references unknown study: {sid}")
            key = (sid, vid)
            if key in variable_ids:
                raise ContractError(f"duplicate variable identity: {sid}/{vid}")
            variable_ids.add(key)
            text = _string(row["text"], f"variables[{i}].text", max_len=8192)
            if _sha(row["text_sha256"], f"variables[{i}].text_sha256") != text_digest(text):
                raise ContractError(f"variable text digest mismatch: {sid}/{vid}")
            variables.append(Variable(sid, vid, text))
            by_study[sid].append(vid)

        studies = [Study(s.study_id, s.title, s.description, tuple(sorted(by_study[s.study_id]))) for s in studies]

        concept_ids: set[str] = set()
        concepts: list[Concept] = []
        for i, item in enumerate(concept_rows):
            row = _object(item, f"concepts[{i}]")
            _exact_keys(row, {"concept_id", "label", "synonyms"}, f"concepts[{i}]")
            cid = _identifier(row["concept_id"], f"concepts[{i}].concept_id")
            if cid == ONT_NONE:
                raise ContractError("ONT_NONE is reserved and must not appear in concept catalog")
            if cid in concept_ids:
                raise ContractError(f"duplicate concept_id: {cid}")
            concept_ids.add(cid)
            label = _string(row["label"], f"concepts[{i}].label", max_len=1024)
            synonyms_raw = _array(row["synonyms"], f"concepts[{i}].synonyms", max_len=256)
            synonyms: list[str] = []
            seen_syn: set[str] = set()
            for j, syn in enumerate(synonyms_raw):
                value = _string(syn, f"concepts[{i}].synonyms[{j}]", max_len=1024)
                key = " ".join(normalized_tokens(value))
                if key in seen_syn:
                    raise ContractError(f"duplicate normalized synonym for concept {cid}")
                seen_syn.add(key)
                synonyms.append(value)
            concepts.append(Concept(cid, label, tuple(sorted(synonyms))))

        normalized = {
            "schema": SCHEMA_CORPUS,
            "studies": [
                {"study_id": s.study_id, "title": s.title, "description": s.description, "text_sha256": text_digest(s.title + "\n" + s.description)}
                for s in sorted(studies, key=lambda x: x.study_id)
            ],
            "variables": [
                {"study_id": v.study_id, "variable_id": v.variable_id, "text": v.text, "text_sha256": text_digest(v.text)}
                for v in sorted(variables, key=lambda x: (x.study_id, x.variable_id))
            ],
            "concepts": [
                {"concept_id": c.concept_id, "label": c.label, "synonyms": list(c.synonyms)}
                for c in sorted(concepts, key=lambda x: x.concept_id)
            ],
        }
        digest = semantic_sha256(normalized)
        if _sha(root["corpus_sha256"], "corpus.corpus_sha256") != digest:
            raise ContractError("corpus_sha256 mismatch")
        return cls(tuple(sorted(studies, key=lambda x: x.study_id)), tuple(sorted(variables, key=lambda x: (x.study_id, x.variable_id))), tuple(sorted(concepts, key=lambda x: x.concept_id)), digest)


@dataclass(frozen=True)
class ResourceManifest:
    digest: str
    resources: tuple[dict[str, str], ...]

    @classmethod
    def from_obj(cls, raw: Any) -> "ResourceManifest":
        root = _object(raw, "resources")
        _exact_keys(root, {"schema", "resources", "manifest_sha256"}, "resources")
        if root["schema"] != SCHEMA_RESOURCES:
            raise ContractError("unsupported resources schema")
        rows = _array(root["resources"], "resources", max_len=1000)
        if not rows:
            raise ContractError("resources must be non-empty")
        normalized: list[dict[str, str]] = []
        ids: set[str] = set()
        for i, item in enumerate(rows):
            row = _object(item, f"resources[{i}]")
            _exact_keys(row, {"resource_id", "kind", "name", "version", "license", "provenance", "digest"}, f"resources[{i}]")
            rid = _identifier(row["resource_id"], f"resources[{i}].resource_id")
            if rid in ids:
                raise ContractError(f"duplicate resource_id: {rid}")
            ids.add(rid)
            kind = _string(row["kind"], f"resources[{i}].kind", max_len=32)
            if kind not in _ALLOWED_RESOURCE_KINDS:
                raise ContractError(f"unsupported resource kind: {kind}")
            normalized.append({
                "resource_id": rid,
                "kind": kind,
                "name": _string(row["name"], f"resources[{i}].name", max_len=256),
                "version": _string(row["version"], f"resources[{i}].version", max_len=128),
                "license": _string(row["license"], f"resources[{i}].license", max_len=256),
                "provenance": _string(row["provenance"], f"resources[{i}].provenance", max_len=2048),
                "digest": _sha(row["digest"], f"resources[{i}].digest"),
            })
        normalized.sort(key=lambda x: x["resource_id"])
        payload = {"schema": SCHEMA_RESOURCES, "resources": normalized}
        digest = semantic_sha256(payload)
        if _sha(root["manifest_sha256"], "resources.manifest_sha256") != digest:
            raise ContractError("manifest_sha256 mismatch")
        return cls(digest, tuple(normalized))

