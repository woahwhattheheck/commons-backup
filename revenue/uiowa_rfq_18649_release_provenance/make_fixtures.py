"""Generate entirely fictional, deterministic assessment examples."""
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ARTIFACT = b"SYNTHETIC RELEASE 057\nFictional service; this file is not executable.\n"

def build():
    digest = hashlib.sha256(ARTIFACT).hexdigest()
    evidence = [{"id": "ev-" + name, "locator": "synthetic-records.md#" + name,
                 "owner_role": role, "kind": "synthetic", "captured_at": "2026-01-12T10:00:00Z"}
                for name, role in [("approval", "Service change coordinator"),
                    ("build", "Build-platform maintainer"), ("artifact", "Release custodian"),
                    ("deployment", "Service operations owner")]]
    complete = dict(schema_version=1, packet_id="SYNTHETIC-057-complete", data_class="synthetic",
        evidence=evidence,
        sources=[dict(id="s1", repository="https://example.invalid/fictional-ess-service",
            revision="a"*40, approved_revision="a"*40,
            approved_at="2026-01-12T09:00:00Z", approval_evidence_id="ev-approval")],
        builds=[dict(id="b1", source_id="s1", observed_repository="https://example.invalid/fictional-ess-service",
            observed_revision="a"*40, builder_id="synthetic/build-platform",
            recipe_uri="synthetic-records.md#build", recipe_sha256=hashlib.sha256(b"fictional-recipe-057").hexdigest(),
            started_at="2026-01-12T09:01:00Z", finished_at="2026-01-12T09:02:00Z",
            evidence_id="ev-build", input_coverage="declared_complete",
            materials=[dict(uri="synthetic:toolchain", sha256="b"*64),
                       dict(uri="synthetic:dependency-lock", sha256="c"*64)])],
        artifacts=[dict(id="a1", build_id="b1", version="fictional-1.0", sha256=digest,
            local_path="demo-artifact.txt", evidence_id="ev-artifact")],
        deployments=[dict(id="d1", artifact_id="a1", environment="ESS-rehearsal",
            observed_version="fictional-1.0", observed_sha256=digest,
            observed_at="2026-01-12T09:03:00Z", evidence_id="ev-deployment")])
    missing = copy.deepcopy(complete)
    missing["packet_id"] = "SYNTHETIC-057-missing-build"
    missing["builds"] = []
    mismatch = copy.deepcopy(complete)
    mismatch["packet_id"] = "SYNTHETIC-057-digest-mismatch"
    mismatch["deployments"][0]["observed_sha256"] = "d"*64
    return {"complete": complete, "missing-build": missing, "digest-mismatch": mismatch}

if __name__ == "__main__":
    from provenance import schema
    (ROOT / "demo-artifact.txt").write_bytes(ARTIFACT)
    (ROOT / "fixtures.json").write_text(json.dumps(build(), indent=2, sort_keys=True)+"\n", encoding="utf-8")
    (ROOT / "packet.schema.json").write_text(json.dumps(schema(), indent=2, sort_keys=True)+"\n", encoding="utf-8")
