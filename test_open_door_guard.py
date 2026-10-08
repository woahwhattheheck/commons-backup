#!/usr/bin/env python3
"""Focused regression coverage for the diff-based open-door guard."""

from pathlib import Path
from subprocess import CompletedProcess
import json
import subprocess
import sys

import open_door_guard as guard


def diff(path, added=(), removed=()):
    lines = [
        f"diff --git a/{path} b/{path}",
        f"--- a/{path}",
        f"+++ b/{path}",
        f"@@ -1,{max(1, len(removed))} +1,{max(1, len(added))} @@",
    ]
    lines.extend(f"-{line}" for line in removed)
    lines.extend(f"+{line}" for line in added)
    return "\n".join(lines) + "\n"


def rules(text):
    return {item.rule for item in guard.scan_diff(text)}


def test_external_sponsor_state_vs_internal_gate():
    """Documented sponsor eligibility must not mask actual admission gates."""
    sponsor_state = "_".join(("CLAIM", "REQUIRED"))
    other_gate = "_".join(("AUTH", "GATE"))
    sponsor_path = "tools/grantfox_fwc26_workfeed/README.md"
    sentence = (
        "If the issue text describes a required application/assignment step, "
        f"it becomes `{sponsor_state}`; supplied claimant/PR observations "
        "become `CLAIMED_OR_PR_OPEN`."
    )
    assert rules(diff(sponsor_path, [sentence])) == set()
    assert "gate-identifier" in rules(diff("docs/sponsor-workflow.md", [sentence]))
    assert "gate-identifier" in rules(diff(sponsor_path, [f"Posters must set `{sponsor_state}` first."]))
    assert "gate-identifier" in rules(diff(sponsor_path, [sentence + f" `{other_gate}`"]))


def main():
    workflow = Path(".github/workflows/open-door-guard.yml").read_text(encoding="utf-8")
    assert "\n  push:\n    branches: [main]\n" in workflow, "open-door guard must report direct main pushes"
    assert workflow.count("- '!builds.json'\n") == 2, "workflow must skip the builds.json projection on PR and push"
    assert "builds.json" in guard.SKIP_FILES
    checkout = workflow.split("reject newly added", 1)[0]
    assert "pull_request.head.sha" not in checkout, (
        "checkout must stay on the pull_request merge ref, not the single-parent head"
    )
    assert "two-parent integration commit" in workflow, (
        "a pull_request checkout that is not the two-parent integration must not pass"
    )
    assert 'open_door_guard.py --diff "$base" HEAD' in workflow
    assert 'open_door_guard.py --diff "$base" "$head"' not in workflow

    test_workflow_diff_base()
    test_external_sponsor_state_vs_internal_gate()

    blocked = "\n".join(
        [
            diff("action_executor.py", ["PROTECTED_FILES = {'AGENTS.md'}"]),
            diff("action_executor.py", ["ALLOWED_VERBS = {'READ', 'WRITE'}"]),
            diff("commons_mcp.py", ["raise PermissionError('permission denied')"]),
            diff("ENTRY.md", ["The capability declaration is required before posting."]),
            diff("action.html", ['<select id="verb" name="verb"><option>READ</option></select>']),
            diff("door/src/mcp.server.ts", ['required: [', '  "actor_id",', '  "memory",', ']']),
            diff("carrier.js", ["const TOS_GATE = enforceTerms(post);"]),
            diff("door/src/protocol.ts", ["const RESERVED_CLAIMS = ['BRYCE'];"]),
            diff("board_ingest.py", ["PROTECTED_FILES = {'ENTRY.md'}  # not an authorization"]),
            diff("commons_mcp.py", ['required: [', '  "actor_id",', ']  # no permission gate']),
            diff("board.js", ["if (isVerificationLoop(post)) hide(post);"]),
        ]
    )
    found = rules(blocked)
    expected = {
        "protected-set",
        "verb-allowlist",
        "permission-exception",
        "explicit-denial",
        "admission-phrase",
        "action-select",
        "required-speaker-schema",
        "gate-identifier",
        "reserved-claim",
        "bot-blocker",
    }
    missing = expected - found
    assert not missing, (missing, found)

    # Deletions are intentionally invisible: removing gates can never fail.
    removal = diff(
        "action_executor.py",
        ["def execute(action): return run(action)"],
        ["PROTECTED_PREFIXES = ('.agents/',)", "raise PermissionError('permission denied')"],
    )
    assert guard.scan_diff(removal) == [], guard.scan_diff(removal)

    # The owner's exact prohibition and ordinary open-door implementation text pass.
    allowed = "\n".join(
        [
            diff(
                "AGENTS.md",
                [
                    "DO NOT add or propose:",
                    "- authentication, identity, claim, seat, or memory gates",
                    "- permission checks or approval workflows",
                    "- verb allowlists or “unlisted verb” rejection",
                    "- protected-path or protected-action restrictions",
                ],
            ),
            diff("START.md", ["Capability metadata is optional and never blocks posting."]),
            diff("action.html", ["No identity, memory, permission, approval, protected-path, or verb gate applies."]),
            diff("test_action_pad_zero_auth.py", ['assert "permission denied" not in source.lower()']),
            diff("carrier.js", ['    "- protected-path or protected-action restrictions",']),
            diff("hub_pages.py", ["Memory is optional and never a posting gate."]),
            diff("hub_pages.py", ["No classifier may hide a post because a bot wrote it."]),
            diff("docs/contract.md", ["Never gate posting on memory."]),
            diff("test_open_routes.py", ['self.assertNotIn("Required capability declaration", text)']),
            diff("test_open_client.js", ['assert(!source.includes("data-memory-" + "block"));']),
            diff("test_open_client.js", ['assert.ok(!source.includes("permission denied"));']),
            diff("test_open_routes.py", ['self.assertFalse("authentication required" in source.lower())']),
            diff("test_module_surface.py", ['assert not hasattr(module, "PROTECTED_FILES")']),
            diff(
                "test_form_contract.py",
                [
                    'body = render_form()',
                    'self.assertNotIn(\'<select name="from"\', body)',
                    'self.assertNotIn("required minlength", body)',
                ],
            ),
        ]
    )
    assert guard.scan_diff(allowed) == [], guard.scan_diff(allowed)

    # PR 7648 / run 33595322662: sold-pack ToS leftover cards state they are
    # not a Commons gate. That collocation is a prohibition, not TOS admission
    # enforcement. Affirmative TOS gates must still fail.
    tos_leftover = "\n".join(
        [
            diff(
                "ground/TJLABS_PACK_TERMS.md",
                [
                    "This card is the machine-backed ToS leftover. It is not a Commons gate. It is not counsel clearance. It is not a minted checkout.",
                ],
            ),
            diff(
                "host/tjlabs_pack_terms.py",
                ['"""Classify tjlabs sold-pack ToS slots. Not a Commons gate.'],
            ),
            diff(
                "test_tjlabs_pack_terms.py",
                [
                    '"""tjlabs sold-pack ToS: owner slots, no invented share, not a Commons gate."""',
                ],
            ),
        ]
    )
    assert guard.scan_diff(tos_leftover) == [], guard.scan_diff(tos_leftover)

    tos_blocked = "\n".join(
        [
            diff("carrier.js", ["The TOS is required before a post may land."]),
            diff(
                "board.js",
                ["Reject posts that have not accepted the terms of service."],
            ),
        ]
    )
    assert rules(tos_blocked) == {"tos-enforcement"}, rules(tos_blocked)

    tjlabs_paths = [
        Path("ground/TJLABS_PACK_TERMS.md"),
        Path("host/tjlabs_pack_terms.py"),
        Path("test_tjlabs_pack_terms.py"),
    ]
    # Root purges that only scan workflow YAML still leave this matrix
    # reading the sold-pack ToS test. A missing live fixture is a failure,
    # not a reason to skip the scan.
    missing_tjlabs = [path.as_posix() for path in tjlabs_paths if not path.is_file()]
    assert missing_tjlabs == [], (
        "open-door live ToS fixtures stay referenced even when no workflow "
        "invokes them directly: " + ", ".join(missing_tjlabs)
    )
    tjlabs_lines = [
        guard.AddedLine(path.as_posix(), line_number, text)
        for path in tjlabs_paths
        for line_number, text in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        )
    ]
    tjlabs_violations = guard.scan_added(tjlabs_lines)
    assert tjlabs_violations == [], tjlabs_violations

    # Run 33671956794 / SHA 77175db: CLAUDE.md owner-words card collocates
    # the noun "owner block" (a pinned instruction block) with a `memory/`
    # path, and the companion memory card says it is "not a door lock".
    # Those are open-door descriptions, not admission locks. Affirmative
    # memory/identity gates must still fail.
    claude_owner_words = "\n".join(
        [
            diff(
                "CLAUDE.md",
                [
                    "Every pinned owner block, law, directive, `ground/` card, `memory/` card, DIRECTIVES.md entry, and Slack #commons cite in this repo is Bryce's own text.",
                ],
            ),
            diff(
                "memory/CLAUDE_OWNER_WORDS.md",
                [
                    "This is behavior memory for Claude, not a door lock. No auth. No gate.",
                ],
            ),
        ]
    )
    assert guard.scan_diff(claude_owner_words) == [], guard.scan_diff(claude_owner_words)

    claude_blocked = "\n".join(
        [
            diff("ENTRY.md", ["The capability declaration is required before posting."]),
            diff("board.js", ["Reject posts whose memory card is missing."]),
            diff("carrier.js", ["block identity from posting without a seat."]),
        ]
    )
    assert rules(claude_blocked) == {"admission-phrase"}, rules(claude_blocked)

    # Run 34001046530 mistook a table label for admission policy in three
    # unchanged business descriptions when their test-presence cells changed.
    # HTML attributes and adjacent prose are independent contexts; neither
    # context is exempt from inspection, including inline-formatted policy.
    for business_text in (
        "AIT Minnesota Metrc capacity gate LIMS",
        "Lexington MRF diversion gate",
        "Prein Newhof PFAS fieldblank gate LIMS",
    ):
        catalog_row = (
            '<tr><td data-label="capability">' + business_text + '</td>'
            '<td data-label="tests">TESTS_PRESENT</td></tr>'
        )
        assert guard.scan_diff(diff("feature-tracker.html", [catalog_row])) == []

    for markup in (
        '<p>Identity is required before posting.</p>',
        '<p>Identity <strong>is required</strong> before posting.</p>',
        '<p>Memory&nbsp;required before posting.</p>',
        '<p>Identity<!-- explanatory comment --> is required.</p>',
        '<td data-label="capability">Identity is required before posting.</td>',
        '<div data-policy="identity required"></div>',
        '<div data-field="identity" data-state="required"></div>',
        '<div title="x > y" data-policy="identity required"></div>',
        '<!-- Identity is required before posting. -->',
        '<script>const policy = "identity required";</script>',
        '<script>const policy = "identity required";',
        '<![CDATA[identity required]]>',
        '<div data-policy="identity required',
        '<input name="identity" required',
    ):
        assert "admission-phrase" in rules(diff("action.html", [markup])), markup

    separate_cells = '<tr><td>Capability</td><td>Laboratory capacity gate</td></tr>'
    assert guard.scan_diff(diff("catalog.html", [separate_cells])) == []
    assert "admission-phrase" in rules(diff("policy.py", ['policy = "identity required"']))
    assert "gate-identifier" in rules(diff("catalog.html", [
        '<td data-label="capability">const IDENTITY_GATE = true;</td>',
    ]))
    assert "required-speaker-field" in rules(diff("action.html", [
        '<input', 'name="identity"', 'required>',
    ]))

    claude_paths = [
        Path("CLAUDE.md"),
        Path("memory/CLAUDE_OWNER_WORDS.md"),
    ]
    claude_lines = [
        guard.AddedLine(path.as_posix(), line_number, text)
        for path in claude_paths
        for line_number, text in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        )
    ]
    claude_violations = guard.scan_added(claude_lines)
    assert claude_violations == [], claude_violations

    # Only explicit negative assertion syntax is exempt. Equivalent positive
    # assertions must still expose denial text and protected-path sets.
    positive_assertions = "\n".join(
        [
            diff("test_open_client.js", ['assert.ok(source.includes("permission denied"));']),
            diff("test_open_routes.py", ['self.assertTrue("authentication required" in source.lower())']),
            diff("test_module_surface.py", ['assert hasattr(module, "PROTECTED_FILES")']),
        ]
    )
    assert rules(positive_assertions) == {"explicit-denial", "protected-set"}, rules(positive_assertions)

    # Durable/generated board data is not executable policy and stays out of this guard.
    historical = "\n".join(
        [
            diff("p/old-gate-record.md", ["The capability declaration is required."]),
            diff("board.html", ["The capability declaration is required before posting."]),
            diff("recent.json", ['{"body": "const PROTECTED_PATHS = []; authentication required"}']),
            diff(
                "revenue/data/board_feed_sample_20260830.json",
                ['{"body": "historical quote: authentication required; PROTECTED_PATHS = []"}'],
            ),
            # Run 35145536899 / SHA b1a84a82309c2eeea26e56b861fd29a751c84cd3 / PR 14955:
            # pretty-print of the builds.json ledger projection re-added historical
            # permit stop_conditions. builds/records/ is already skipped; the live
            # projection is generated data too.
            diff("builds.json", ['            "unexpected protected path",']),
            diff("builds.json", ['            "protected-path surprise",']),
        ]
    )
    assert guard.scan_diff(historical) == [], guard.scan_diff(historical)
    assert "protected-action" in rules(diff("action_executor.py", ['            "unexpected protected path",']))
    assert "protected-action" in rules(diff("action_executor.py", ['            "protected-path surprise",']))
    builds_live = [
        guard.AddedLine("builds.json", line_number, text)
        for line_number, text in enumerate(Path("builds.json").read_text(encoding="utf-8").splitlines(), 1)
        if "protected path" in text.lower() or "protected-path" in text.lower()
    ]
    assert builds_live, "builds.json still carries historical permit stop_conditions"
    assert guard.scan_added(builds_live) == [], guard.scan_added(builds_live)

    # Only the exact frozen JSON artifact is historical data. An active source
    # lookalike with the same stem must remain inside the policy guard.
    sample_source_lookalike = diff(
        "revenue/data/board_feed_sample_policy.py",
        ["PROTECTED_PATHS = []"],
    )
    assert rules(sample_source_lookalike) == {
        "protected-action",
        "protected-set",
    }, rules(sample_source_lookalike)

    # Polar AS9100 #11191 landed PermissionError raises whose nearby source did
    # not prove production-LIMS human-release context, so open-door-guard failed
    # on the merge SHA. Keep the fail-closed product behavior, but require the
    # existing human-release vocabulary. Commons-path copies stay rejectable.
    polar_old_lock = diff(
        "revenue/production-lims/trace-polar-as9100/trace_polar_as9100.py",
        [
            'raise PermissionError("held evidence cannot be approved")',
            'raise PermissionError("automatic disposition disabled")',
        ],
    )
    assert rules(polar_old_lock) == {"permission-exception"}, rules(polar_old_lock)
    polar_release = diff(
        "revenue/production-lims/trace-polar-as9100/trace_polar_as9100.py",
        [
            'if pack["status"] != "REVIEW_READY":',
            '    raise PermissionError("held evidence cannot release a report")',
            'def automatic_disposition(self, *_args, **_kwargs):',
            '    raise PermissionError("automatic release is disabled")',
        ],
    )
    assert guard.scan_diff(polar_release) == [], guard.scan_diff(polar_release)
    assert "permission-exception" in rules(diff("commons_mcp.py", [
        'raise PermissionError("automatic release is disabled")',
    ]))
    polar_path = Path("revenue/production-lims/trace-polar-as9100/trace_polar_as9100.py")
    polar_added = [
        guard.AddedLine(polar_path.as_posix(), line_number, text)
        for line_number, text in enumerate(polar_path.read_text(encoding="utf-8").splitlines(), 1)
    ]
    polar_violations = [
        item for item in guard.scan_added(polar_added) if item.rule == "permission-exception"
    ]
    assert polar_violations == [], polar_violations

    # New Bloom beverage CoA #11199 landed PermissionError("packet not eligible")
    # whose nearby source did not prove production-LIMS human-release context, so
    # open-door-guard failed on merge SHA b9e8f85. Keep fail-closed product
    # behavior, but require the existing human-release vocabulary.
    newbloom_old_lock = diff(
        "revenue/production-lims/newbloom-multistate-beverage-coa/newbloom_beverage_coa.py",
        [
            'raise PermissionError("packet not eligible")',
        ],
    )
    assert rules(newbloom_old_lock) == {"permission-exception"}, rules(newbloom_old_lock)
    newbloom_release = diff(
        "revenue/production-lims/newbloom-multistate-beverage-coa/newbloom_beverage_coa.py",
        [
            'if packet["state"] != "STAGED_HUMAN_REVIEW" or packet["released_by"] is not None:',
            '    raise PermissionError("packet not eligible to release a certificate")',
        ],
    )
    assert guard.scan_diff(newbloom_release) == [], guard.scan_diff(newbloom_release)
    assert "permission-exception" in rules(diff("commons_mcp.py", [
        'raise PermissionError("packet not eligible to release a certificate")',
    ]))
    newbloom_path = Path("revenue/production-lims/newbloom-multistate-beverage-coa/newbloom_beverage_coa.py")
    newbloom_added = [
        guard.AddedLine(newbloom_path.as_posix(), line_number, text)
        for line_number, text in enumerate(newbloom_path.read_text(encoding="utf-8").splitlines(), 1)
    ]
    newbloom_violations = [
        item for item in guard.scan_added(newbloom_added) if item.rule == "permission-exception"
    ]
    assert newbloom_violations == [], newbloom_violations

    # Compact catalog exclusion lists may name retired mechanisms only when they
    # do not collocate claim/seat with "gate" on one line. PR 4924's compact
    # out_of_scope one-liners failed open-door-guard on this collocation.
    catalog_blocked = "\n".join(
        [
            diff(
                "revenue/scope_to_delivery/catalog_bindings.json",
                ['      "out_of_scope": ["claim-purchase", "access-gate", "from-equals-payment"],'],
            ),
            diff(
                "revenue/scope_to_delivery/catalog_bindings.json",
                ['      "out_of_scope": ["seat", "claim", "access-gate"],'],
            ),
        ]
    )
    assert rules(catalog_blocked) == {"admission-phrase"}, rules(catalog_blocked)

    catalog_allowed = diff(
        "revenue/scope_to_delivery/catalog_bindings.json",
        [
            '      "out_of_scope": ["membership", "gated-entitlement", "private-buyer-data-on-main"],',
            '      "out_of_scope": ["claim-purchase", "gated-entitlement", "from-equals-payment"],',
            '      "out_of_scope": ["seat", "claim", "gated-entitlement"],',
        ],
    )
    assert guard.scan_diff(catalog_allowed) == [], guard.scan_diff(catalog_allowed)

    bindings_path = Path("revenue/scope_to_delivery/catalog_bindings.json")
    binding_lines = [
        guard.AddedLine(bindings_path.as_posix(), line_number, text)
        for line_number, text in enumerate(bindings_path.read_text(encoding="utf-8").splitlines(), 1)
    ]
    binding_violations = guard.scan_added(binding_lines)
    assert binding_violations == [], binding_violations

    # Run 34189413855 / SHA 95c5b22: explicit-WOOL consumer stored per-objective
    # selected game plans in a field named `choices` next to `action`. That is
    # a result map, not an Action Pad verb enum. The collocation still fails;
    # the renamed field must pass, and the live experiment source must stay clean.
    wool_blocked = "\n".join(
        [
            diff(
                "revenue/kaggriculture/cloud-market-response/check_joint_wool_hypotheses.py",
                [
                    "out = {'original_action': deepcopy(action), 'choices': {}, 'counts': {}}",
                ],
            ),
            diff(
                "revenue/kaggriculture/cloud-market-response/check_joint_wool_hypotheses.py",
                [
                    "out['choices'][tie] = {'action': chosen, 'changed': chosen != action}",
                ],
            ),
        ]
    )
    assert rules(wool_blocked) == {"verb-enum"}, rules(wool_blocked)

    wool_allowed = diff(
        "revenue/kaggriculture/cloud-market-response/check_joint_wool_hypotheses.py",
        [
            "out = {'original_action': deepcopy(action), 'by_objective': {}, 'counts': {}}",
            "out['by_objective'][tie] = {'action': chosen, 'changed': chosen != action}",
        ],
    )
    assert guard.scan_diff(wool_allowed) == [], guard.scan_diff(wool_allowed)

    wool_path = Path("revenue/kaggriculture/cloud-market-response/check_joint_wool_hypotheses.py")
    wool_lines = [
        guard.AddedLine(wool_path.as_posix(), line_number, text)
        for line_number, text in enumerate(wool_path.read_text(encoding="utf-8").splitlines(), 1)
    ]
    wool_violations = guard.scan_added(wool_lines)
    assert wool_violations == [], wool_violations

    # Run 34652995232 / SHA 904d13ea: PLACE delivery overflow helper added
    # "Exact actor cardinality is required" on one comment line. That collocates
    # speaker/actor metadata with a requirement and trips admission-phrase.
    # Worker-set wording keeps the same geometry contract without the lock
    # collocation. The forbidden line must still fail.
    place_delivery_path = (
        "revenue/kaggriculture/cloud-execution-lab/candidates/v3/overlay/"
        "r04_place_delivery.py"
    )
    place_delivery_blocked = diff(
        place_delivery_path,
        [
            "# allowed to redefine shed adjacency. Exact actor cardinality is required in",
        ],
    )
    assert rules(place_delivery_blocked) == {"admission-phrase"}, rules(
        place_delivery_blocked
    )
    place_delivery_allowed = diff(
        place_delivery_path,
        [
            "# allowed to redefine shed adjacency. Worker-set cardinality is required in",
            "# both directions: neither the public state nor the parent command may expose",
            "# only a prefix of the actual worker set.",
        ],
    )
    assert guard.scan_diff(place_delivery_allowed) == [], guard.scan_diff(
        place_delivery_allowed
    )

    # Run 34726510598 / SHA 531928937e85b7f55967cc6a9a28bb8334cdab3a:
    # BLOCK-B public snapshot index stored Kaggle agent logs as one
    # "actor_path" string containing both native-block-b and actor-*.jsonl.
    # That collocates speaker metadata with "block" on one line and trips
    # admission-phrase. Split dir/name keeps the same 32 log locations
    # without the lock collocation. The forbidden line must still fail.
    block_b_hashes_path = (
        "revenue/kaggriculture/cloud-execution-lab/candidates/v5/"
        "selective-carrot/route-matrix-native/BLOCK-B/"
        "BLOCK-B-snapshot-hashes.json"
    )
    block_b_hashes_blocked = diff(
        block_b_hashes_path,
        [
            '    "actor_path": "/workspace/scratch/e67ff728c8fb/native-block-b/R05/snapshots/actor-v3mbbo9b.jsonl",',
        ],
    )
    assert rules(block_b_hashes_blocked) == {"admission-phrase"}, rules(
        block_b_hashes_blocked
    )
    block_b_hashes_allowed = diff(
        block_b_hashes_path,
        [
            '    "snapshot_dir": "/workspace/scratch/e67ff728c8fb/native-block-b/R05/snapshots",',
            '    "snapshot_name": "actor-v3mbbo9b.jsonl",',
        ],
    )
    assert guard.scan_diff(block_b_hashes_allowed) == [], guard.scan_diff(
        block_b_hashes_allowed
    )
    block_b_hashes_file = Path(block_b_hashes_path)
    block_b_hash_rows = json.loads(block_b_hashes_file.read_text(encoding="utf-8"))
    assert len(block_b_hash_rows) == 32, len(block_b_hash_rows)
    for row in block_b_hash_rows:
        assert "actor_path" not in row, row
        joined = row["snapshot_dir"].rstrip("/") + "/" + row["snapshot_name"]
        assert joined.endswith("/" + row["snapshot_name"]), joined
        assert "native-block-b" in row["snapshot_dir"]
        assert row["snapshot_name"].startswith("actor-")
        assert row["snapshot_name"].endswith(".jsonl")
        assert "actor_file_sha256" in row
    block_b_hash_lines = [
        guard.AddedLine(block_b_hashes_file.as_posix(), line_number, text)
        for line_number, text in enumerate(
            block_b_hashes_file.read_text(encoding="utf-8").splitlines(), 1
        )
    ]
    block_b_hash_violations = guard.scan_added(block_b_hash_lines)
    assert block_b_hash_violations == [], block_b_hash_violations

    # Run 34652759900 / SHA 0f6aca3c: EOD capacity-rescue helper added
    # "Unknown verbs" on one comment line. That trips unlisted-action even
    # though the line is game-engine shed-stock classification, not Action Pad
    # admission. Market-row-head wording keeps the same theorem without the
    # lock collocation. The forbidden line must still fail.
    eod_rescue_path = (
        "revenue/kaggriculture/cloud-execution-lab/candidates/v3/overlay/"
        "r04_eod_capacity_rescue.py"
    )
    eod_rescue_blocked = diff(
        eod_rescue_path,
        [
            "# stock. Unknown verbs are ambiguous raw rows and must fail closed rather than",
        ],
    )
    assert rules(eod_rescue_blocked) == {"unlisted-action"}, rules(eod_rescue_blocked)
    eod_rescue_allowed = diff(
        eod_rescue_path,
        [
            "# These are the only official market row heads whose execution cannot change shed",
            "# stock. Any other raw head has an unspecified shed effect, so this helper",
            "# returns the parent rather than assuming the row is shed-neutral.",
        ],
    )
    assert guard.scan_diff(eod_rescue_allowed) == [], guard.scan_diff(eod_rescue_allowed)

    # Run 35932371951 / SHA 99dfe2a4: completion reconciliation added
    # `if action not in ("closed", "reopened")` before reading canonical
    # issue state. That membership test is an unlisted-action lock. Current
    # issue state already chooses reopen versus completed, so the handler
    # must not reject an unlisted action. The forbidden line still fails.
    completion_blocked = diff(
        "board_ingest.py",
        [
            'if action not in ("closed", "reopened"):',
            "    return 0",
        ],
    )
    assert rules(completion_blocked) == {"unlisted-action"}, rules(completion_blocked)
    completion_evasion = diff(
        "board_ingest.py",
        [
            'if action != "closed" and action != "reopened":',
            "    return 0",
        ],
    )
    assert rules(completion_evasion) == {"unlisted-action"}, rules(completion_evasion)
    completion_allowed = diff(
        "board_ingest.py",
        [
            "def _handle_completion_issue_event(ev):",
            '    """Reconcile current issue state without re-ingesting it as a post."""',
            '    issue = ev.get("issue")',
            '    number = issue.get("number") if isinstance(issue, dict) else None',
            '    if canonical_issue.get("state") == "open":',
            "        removed = completion_projection.remove_markers_for_issue(ROOT, number)",
        ],
    )
    assert guard.scan_diff(completion_allowed) == [], guard.scan_diff(completion_allowed)
    handler = Path("board_ingest.py").read_text(encoding="utf-8").split(
        "def _handle_completion_issue_event", 1
    )[1].split("\ndef ", 1)[0]
    assert 'action not in ("closed", "reopened")' not in handler
    assert 'action != "closed" and action != "reopened"' not in handler

    # Run 34190268951 / SHA 285dedd: TRACE-9042 completeness tests mutate a
    # retained cell's recorded player-view field and then call a unittest
    # helper. Collocating `seat` with `reject` on one line is still an
    # admission phrase. Split assignment and helper remain data checks.
    report_cell_path = (
        "revenue/kaggriculture/cloud-execution-lab/trace-cache-checks/"
        "test_report_completeness.py"
    )
    report_cell_blocked = diff(
        report_cell_path,
        [
            "def test_wrong_view_seat(self):self.data['uncached']['cells'][0]['seat']=1;self.reject()"
        ],
    )
    assert rules(report_cell_blocked) == {"admission-phrase"}, rules(report_cell_blocked)
    report_cell_allowed = diff(
        report_cell_path,
        [
            "def test_wrong_view_seat(self):",
            "    self.data['uncached']['cells'][0]['seat']=1",
            "    self.reject()",
        ],
    )
    assert guard.scan_diff(report_cell_allowed) == [], guard.scan_diff(report_cell_allowed)
    completeness_path = Path(report_cell_path)
    completeness_lines = [
        guard.AddedLine(completeness_path.as_posix(), line_number, text)
        for line_number, text in enumerate(
            completeness_path.read_text(encoding="utf-8").splitlines(), 1
        )
    ]
    completeness_violations = guard.scan_added(completeness_lines)
    assert completeness_violations == [], completeness_violations

    # Run 34220005044 / SHA 4b125d39: Hive #044 Parts Sourcing Desk added
    # <input name="model" required> for equipment model. The guard treats
    # name="model" as a speaker/capability field, so HTML required is an
    # admission lock. Equipment model stays optional in markup; backend
    # workshop validation is unchanged. The original required tag must
    # still fail; the repaired live file must stay clean.
    parts_desk_html = "revenue/hive/parts-sourcing-desk/index.html"
    parts_desk_blocked = diff(
        parts_desk_html,
        [
            '<label>Exact model<input name="model" required placeholder="Copy the model label"></label>',
        ],
    )
    assert rules(parts_desk_blocked) == {"required-speaker-field"}, rules(parts_desk_blocked)
    parts_desk_allowed = diff(
        parts_desk_html,
        [
            '<label>Exact model<input name="model" placeholder="Copy the model label"></label>',
        ],
    )
    assert guard.scan_diff(parts_desk_allowed) == [], guard.scan_diff(parts_desk_allowed)
    parts_path = Path(parts_desk_html)
    parts_lines = [
        guard.AddedLine(parts_path.as_posix(), line_number, text)
        for line_number, text in enumerate(
            parts_path.read_text(encoding="utf-8").splitlines(), 1
        )
    ]
    parts_violations = guard.scan_added(parts_lines)
    assert parts_violations == [], parts_violations

    # Run 34372584220 / SHA 994a0bff: E17 RESULTS checkpoint collocated
    # "default-promotion claim" with "The required next experiment" on one
    # line. That is a no-result boundary, not identity/claim admission.
    # The collocation still fails; the reworded live file must stay clean.
    e17_results_path = "revenue/kaggriculture/cloud-e17-regime-history/RESULTS.md"
    e17_results_blocked = diff(
        e17_results_path,
        [
            "Therefore there is **no terminal-cash, win-rate, downside, runtime, or default-promotion claim**. The required next experiment remains a source-pinned matched screen.",
        ],
    )
    assert rules(e17_results_blocked) == {"admission-phrase"}, rules(e17_results_blocked)
    e17_results_allowed = diff(
        e17_results_path,
        [
            "Therefore there is **no terminal-cash, win-rate, downside, runtime, or default-promotion outcome**. The next experiment remains a source-pinned matched screen.",
        ],
    )
    assert guard.scan_diff(e17_results_allowed) == [], guard.scan_diff(e17_results_allowed)
    e17_path = Path(e17_results_path)
    e17_lines = [
        guard.AddedLine(e17_path.as_posix(), line_number, text)
        for line_number, text in enumerate(
            e17_path.read_text(encoding="utf-8").splitlines(), 1
        )
    ]
    e17_violations = guard.scan_added(e17_lines)
    assert e17_violations == [], e17_violations

    # Run 34665578480 / SHA a7ae519b: attaching the composed V4 donor tree
    # collocated `action` with `not in` on one B9 worker-slot line, and
    # collocated `return action` with a local `choices` list in PLACE
    # delivery ranking. Those are game-envelope / inventory-rank helpers,
    # not Action Pad admission. Split the B9 membership tests and rename
    # the rank list so the live donor overlay stays clean. The forbidden
    # collocations must still fail.
    v4_b9_path = (
        "revenue/kaggriculture/cloud-execution-lab/candidates/v4/donor/"
        "overlay/b9_terminal_fertilizer.py"
    )
    v4_b9_blocked = diff(
        v4_b9_path,
        [
            '        if "farmer" not in action or "hands" not in action:',
        ],
    )
    assert rules(v4_b9_blocked) == {"unlisted-action"}, rules(v4_b9_blocked)
    v4_b9_allowed = diff(
        v4_b9_path,
        [
            '        if "farmer" not in action:',
            "            return action, False",
            '        if "hands" not in action:',
            "            return action, False",
        ],
    )
    assert guard.scan_diff(v4_b9_allowed) == [], guard.scan_diff(v4_b9_allowed)
    v4_b9_live = Path(v4_b9_path)
    v4_b9_lines = [
        guard.AddedLine(v4_b9_live.as_posix(), line_number, text)
        for line_number, text in enumerate(
            v4_b9_live.read_text(encoding="utf-8").splitlines(), 1
        )
    ]
    v4_b9_violations = guard.scan_added(v4_b9_lines)
    assert v4_b9_violations == [], v4_b9_violations

    v4_place_path = (
        "revenue/kaggriculture/cloud-execution-lab/candidates/v4/donor/"
        "overlay/r04_place_delivery.py"
    )
    v4_place_blocked = diff(
        v4_place_path,
        [
            "        if not isinstance(inventory, dict):",
            "            return action",
            "        choices = []",
        ],
    )
    assert rules(v4_place_blocked) == {"verb-enum"}, rules(v4_place_blocked)
    v4_place_allowed = diff(
        v4_place_path,
        [
            "        if not isinstance(inventory, dict):",
            "            return action",
            "        ranked_payloads = []",
            "        for item, held in inventory.items():",
            "            if item not in r04.PRODUCTS or not _positive_plain_int(held):",
            "                continue",
            "            price = view.prices[item]",
            "            product_order = r04.PRODUCTS.index(item)",
            "            ranked_payloads.append((price, held, -product_order, item))",
            "        if ranked_payloads:",
            "            price, held, _, item = max(ranked_payloads)",
        ],
    )
    assert guard.scan_diff(v4_place_allowed) == [], guard.scan_diff(v4_place_allowed)
    v4_place_live = Path(v4_place_path)
    v4_place_lines = [
        guard.AddedLine(v4_place_live.as_posix(), line_number, text)
        for line_number, text in enumerate(
            v4_place_live.read_text(encoding="utf-8").splitlines(), 1
        )
    ]
    v4_place_violations = guard.scan_added(v4_place_lines)
    assert v4_place_violations == [], v4_place_violations

    # Run 35831197313 / SHA 090ade5bfb8976d12b1a43a247e5b05f20e20a5c:
    # the activity-brief CLI named an optional receipt file --action-receipts
    # in the same added window as argparse choices for page order and export
    # format. That is a receipt path plus paging/format selectors, not an
    # Action Pad verb enum. The collocation still fails. The receipt flag must
    # not use a bounded action token beside choices. The live brief stays clean.
    brief_path = "integrations/command_center/jev_activity_brief.py"
    brief_blocked = diff(
        brief_path,
        [
            '    parser.add_argument("--action-receipts", help="optional JSON array of action receipts")',
            '    parser.add_argument("--attention-order", choices=("newest", "oldest"), default="newest")',
            '    parser.add_argument("--format", choices=("json", "markdown"), default="json")',
        ],
    )
    assert rules(brief_blocked) == {"verb-enum"}, rules(brief_blocked)
    brief_allowed = diff(
        brief_path,
        [
            '    parser.add_argument("--receipts", help="optional JSON array of provider readback receipts")',
            '    parser.add_argument("--attention-order", choices=("newest", "oldest"), default="newest")',
            '    parser.add_argument("--format", choices=("json", "markdown"), default="json")',
        ],
    )
    assert guard.scan_diff(brief_allowed) == [], guard.scan_diff(brief_allowed)
    brief_verb_enum = diff(
        brief_path,
        [
            '    parser.add_argument("--action", choices=("approve", "reject"))',
        ],
    )
    assert rules(brief_verb_enum) == {"verb-enum"}, rules(brief_verb_enum)
    brief_live = Path(brief_path)
    brief_lines = [
        guard.AddedLine(brief_live.as_posix(), line_number, text)
        for line_number, text in enumerate(
            brief_live.read_text(encoding="utf-8").splitlines(), 1
        )
    ]
    brief_violations = guard.scan_added(brief_lines)
    assert brief_violations == [], brief_violations

    # Run 34689798237 / SHA 0869436d: wrapping operating-stock market-shape
    # fail-closed re-indented an existing PLACE/shed-deposit membership test
    # so `action` sat next to `not in` on one added line. That trips
    # unlisted-action even though the line classifies game-engine shed
    # arrivals, not Action Pad verbs. Membership via ANIMALS.get keeps the
    # same deposit bound. The forbidden collocation must still fail.
    operating_stock_path = (
        "revenue/kaggriculture/cloud-execution-lab/operating_stock.py"
    )
    operating_stock_blocked = diff(
        operating_stock_path,
        [
            "                if action[0] == 'PLACE' and len(action) > 1 and action[1] not in mechanics.ANIMALS:",
        ],
    )
    assert rules(operating_stock_blocked) == {"unlisted-action"}, rules(
        operating_stock_blocked
    )
    operating_stock_allowed = diff(
        operating_stock_path,
        [
            "                if action[0] == 'PLACE' and len(action) > 1 and mechanics.ANIMALS.get(action[1]) is None:",
            "                    deposits += max(0, int(action[2]) if len(action) > 2 else 1)",
        ],
    )
    assert guard.scan_diff(operating_stock_allowed) == [], guard.scan_diff(
        operating_stock_allowed
    )
    operating_stock_live = Path(operating_stock_path)
    operating_stock_lines = [
        guard.AddedLine(operating_stock_live.as_posix(), line_number, text)
        for line_number, text in enumerate(
            operating_stock_live.read_text(encoding="utf-8").splitlines(), 1
        )
    ]
    operating_stock_violations = [
        item for item in guard.scan_added(operating_stock_lines)
        if item.rule == "unlisted-action"
    ]
    assert operating_stock_violations == [], operating_stock_violations

    # Run 35104154972 / SHA fe62c8ac: Pinellas current-custody README
    # collocated "identity admission" with "permission gate" on a denial that
    # the code does not add those locks. Markdown-emphasized "does **not** add"
    # is not a recognized prohibition marker, so open-door-guard failed after
    # #14853 merged. Keep the collocation rejectable; rewrite to existing
    # "no identity" prohibition language so the live README stays clean.
    pinellas_readme_path = (
        "opportunities/pinellas_26_0795_rfi_digital_evidence/README.md"
    )
    pinellas_readme_blocked = diff(
        pinellas_readme_path,
        [
            "This code does **not** add login, credentials, identity admission, ACLs or another permission gate. A production court/records platform would install the provider using its own retained ledger/records infrastructure.",
        ],
    )
    assert rules(pinellas_readme_blocked) == {"admission-phrase"}, rules(
        pinellas_readme_blocked
    )
    pinellas_readme_allowed = diff(
        pinellas_readme_path,
        [
            "This code does not add login or credentials. No identity, permission, or admission gate applies. A production court/records platform would install the provider using its own retained ledger/records infrastructure.",
        ],
    )
    assert guard.scan_diff(pinellas_readme_allowed) == [], guard.scan_diff(
        pinellas_readme_allowed
    )
    pinellas_readme_live = Path(pinellas_readme_path)
    pinellas_readme_lines = [
        guard.AddedLine(pinellas_readme_live.as_posix(), line_number, text)
        for line_number, text in enumerate(
            pinellas_readme_live.read_text(encoding="utf-8").splitlines(), 1
        )
    ]
    pinellas_readme_violations = guard.scan_added(pinellas_readme_lines)
    assert pinellas_readme_violations == [], pinellas_readme_violations

    # Run 35162239221 / SHA b44b539c: TXST AI advising #15064 added
    # "buyer-required ... identity" and f-string "claim ... {gate}" collocates.
    # Those are RFP integration/qualification nouns, not Commons admission.
    # Keep the collocated originals rejectable; rewrite so live files stay clean.
    txst_packet_path = "revenue/txst_ai_advising_754/PURSUIT_PACKET.md"
    txst_qual_path = "revenue/txst_ai_advising_754/qualification.py"
    txst_packet_blocked = diff(
        txst_packet_path,
        [
            "**Integration.** Create a versioned interface map across buyer-required SIS/CRM/LMS/identity/advising services; define idempotency, retry/reconciliation, contract tests, cutover, and rollback.",
        ],
    )
    assert rules(txst_packet_blocked) == {"admission-phrase"}, rules(txst_packet_blocked)
    txst_qual_blocked = diff(
        txst_qual_path,
        [
            '            raise ContractError(f"invalid owner claim state for {gate}")',
        ],
    )
    assert rules(txst_qual_blocked) == {"admission-phrase"}, rules(txst_qual_blocked)
    txst_packet_allowed = diff(
        txst_packet_path,
        [
            "**Integration.** Create a versioned interface map across buyer-specified SIS/CRM/LMS/identity/advising services; define idempotency, retry/reconciliation, contract tests, cutover, and rollback.",
        ],
    )
    assert guard.scan_diff(txst_packet_allowed) == [], guard.scan_diff(txst_packet_allowed)
    txst_qual_allowed = diff(
        txst_qual_path,
        [
            "    for requirement in OWNER_GATES:",
            "        if owner[requirement] not in {\"UNKNOWN\", \"CLAIMED_SUPPORTED\", \"CLAIMED_GAP\"}:",
            '            raise ContractError(f"invalid owner claim state for {requirement}")',
        ],
    )
    assert guard.scan_diff(txst_qual_allowed) == [], guard.scan_diff(txst_qual_allowed)
    txst_live_violations = []
    for live_path in (txst_packet_path, txst_qual_path):
        live = Path(live_path)
        live_lines = [
            guard.AddedLine(live.as_posix(), line_number, text)
            for line_number, text in enumerate(
                live.read_text(encoding="utf-8").splitlines(), 1
            )
        ]
        txst_live_violations.extend(guard.scan_added(live_lines))
    assert txst_live_violations == [], txst_live_violations



    # Binary artifacts may make `git diff --text` emit non-UTF-8 bytes.  They
    # must never crash or blind the additions guard.
    original_run = guard.subprocess.run
    try:
        guard.subprocess.run = lambda *args, **kwargs: CompletedProcess(
            args=args[0], returncode=0,
            stdout=b"diff --git a/excerpts/x.mno b/excerpts/x.mno\n+\x80binary\n",
            stderr=b"",
        )
        decoded = guard.git_diff("base", "head")
        assert "binary" in decoded
        assert guard.scan_diff(decoded) == []
    finally:
        guard.subprocess.run = original_run

    # Current active entry/agent/Slack instructions contain only the exact
    # directive and open-door prohibition language, never an affirmative
    # admission lock.  The Slack card used to require a complete capability
    # declaration even after ENTRY made every field optional.
    context_paths = [
        Path("AGENTS.md"),
        Path("START.md"),
        Path("ground/EXECUTE.md"),
        Path(".cursor/rules/execute-immediately.mdc"),
    ]
    for path in context_paths:
        context = path.read_text(encoding="utf-8")
        assert "NO AUTH" in context, path
        assert "every turn" in context, path
        assert "login, signup, session, token, credential" in context, path
        assert "any equivalent lock anywhere in Commons" in context, path

    instruction_paths = [
        *context_paths,
        Path("ENTRY.md"),
        Path("ground/SLACK.md"),
        *Path(".agents").rglob("*.md"),
    ]
    instruction_lines = [
        guard.AddedLine(path.as_posix(), line_number, text)
        for path in instruction_paths
        for line_number, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
    ]
    instruction_violations = guard.scan_added(instruction_lines)
    assert instruction_violations == [], instruction_violations

    print("OPEN DOOR GUARD TEST: additions blocked; removals, directive, and active instructions pass")


def test_workflow_diff_base():
    """Execute the real workflow shell and scanner on isolated Git histories."""
    import os
    import shutil
    import subprocess
    import tempfile
    import textwrap

    root = Path(__file__).resolve().parent
    workflow = (root / '.github/workflows/open-door-guard.yml').read_text(encoding='utf-8')
    step = workflow.split('      - name: reject newly added ', 1)[1]
    block = step.split('        run: |\n', 1)[1].split('\n      - name:', 1)[0]
    script = textwrap.dedent(block).replace(
        "python3 ", '"' + Path(sys.executable).as_posix() + '" '
    )
    scanner = root / 'open_door_guard.py'
    cases = []
    with tempfile.TemporaryDirectory(prefix='guard-base-', ignore_cleanup_errors=True) as temporary:
        tmp = Path(temporary)
        home = tmp / 'home'
        home.mkdir()
        env = dict(os.environ, HOME=str(home), GIT_CONFIG_NOSYSTEM='1',
                   GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0')
        repo = tmp / 'repo'
        repo.mkdir()

        def command(args, cwd=repo, *, check=True, input=None, extra=None):
            result = subprocess.run(args, cwd=cwd, env=dict(env, **(extra or {})),
                input=input, text=True, capture_output=True, timeout=20)
            if check:
                assert result.returncode == 0, (args, result.stdout, result.stderr)
            return result

        def git(*args, cwd=repo, check=True, input=None):
            return command(['git', *args], cwd, check=check, input=input)

        def commit(message):
            git('add', '.')
            git('commit', '-qm', message)
            return git('rev-parse', 'HEAD').stdout.strip()

        def check_case(name, expected, cwd=repo, *, event='pull_request',
                       pr_head=None, push_base='', contains=None, absent=None):
            result = command(['bash', '-c', script], cwd, check=False, extra={
                'EVENT_NAME': event, 'PR_HEAD_SHA': pr_head or feature_head,
                # Deliberately stale metadata reproduces the provider incident.
                'PR_BASE_SHA': old_base, 'PUSH_BASE_SHA': push_base,
            })
            output = result.stdout + result.stderr
            assert result.returncode == expected, (name, result.returncode, output)
            if contains:
                assert contains in output, (name, output)
            if absent:
                assert absent not in output, (name, output)
            cases.append(name)
            return result

        git('init', '-q', '-b', 'main')
        git('config', 'user.name', 'Workflow fixture')
        git('config', 'user.email', 'fixture@example.invalid')
        shutil.copyfile(scanner, repo / 'open_door_guard.py')
        (repo / 'README.md').write_text('Initial fixture.\n', encoding='utf-8')
        old_base = commit('initial')
        git('checkout', '-qb', 'feature')
        (repo / 'candidate.py').write_text('value = 1\n', encoding='utf-8')
        feature_head = commit('candidate')
        git('checkout', '-q', 'main')
        (repo / 'concurrent.py').write_text("PROTECTED_FILES = {'example'}\n", encoding='utf-8')
        actual_base = commit('concurrent base')
        git('merge', '-q', '--no-ff', 'feature', '-m',
            'integration\n\nparent this-is-message-text-not-a-header')
        merged = git('rev-parse', 'HEAD').stdout.strip()
        raw_parents = git('cat-file', '-p', 'HEAD').stdout.split('\n\n', 1)[0]
        assert 'parent ' + actual_base in raw_parents
        assert 'parent ' + feature_head in raw_parents

        old_result = command([sys.executable, 'open_door_guard.py', '--diff', old_base, merged], check=False)
        assert old_result.returncode == 1 and 'concurrent.py:' in old_result.stderr
        cases.append('stale-event-base-reproduces-concurrent-finding')
        check_case('actual-merge-base-excludes-concurrent-change', 0, contains='GUARD: PASS')
        check_case('wrong-second-parent-is-not-a-pass', 1, pr_head=old_base, absent='GUARD: PASS')
        check_case('push-still-sees-all-pushed-additions', 1, event='push', push_base=old_base,
                   contains='concurrent.py:')
        check_case('push-retains-existing-comparison', 0, event='push', push_base=actual_base,
                   contains='GUARD: PASS')

        # A shallow clone retains the raw merge header even when parent objects
        # are absent. The exact base is fetched from this local fixture only.
        git('branch', 'integration', merged)
        bare = tmp / 'remote.git'
        git('clone', '-q', '--bare', str(repo), str(bare), cwd=tmp)
        for folder in ('shallow', 'missing-base'):
            git('clone', '-q', '--depth=1', '--branch', 'integration', bare.as_uri(),
                str(tmp / folder), cwd=tmp)
        shallow = tmp / 'shallow'
        assert git('rev-parse', '--is-shallow-repository', cwd=shallow).stdout.strip() == 'true'
        assert git('cat-file', '-e', actual_base + '^{commit}', cwd=shallow, check=False).returncode != 0
        check_case('depth-one-checkout-fetches-exact-first-parent', 0, cwd=shallow,
                   contains='GUARD: PASS')
        git('cat-file', '-e', actual_base + '^{commit}', cwd=shallow)
        assert git('rev-parse', '--is-shallow-repository', cwd=shallow).stdout.strip() == 'true'
        missing = tmp / 'missing-base'
        git('remote', 'set-url', 'origin', str(tmp / 'absent-remote'), cwd=missing)
        check_case('missing-required-base-is-not-a-pass', 128, cwd=missing, absent='GUARD: PASS')

        # A new finding in the feature still reaches the unchanged scanner.
        git('checkout', '-qb', 'bad-feature', old_base)
        (repo / 'introduced.py').write_text("ALLOWED_VERBS = {'READ'}\n", encoding='utf-8')
        bad_head = commit('candidate finding')
        git('checkout', '-q', '--detach', actual_base)
        git('merge', '-q', '--no-ff', 'bad-feature', '-m', 'bad integration')
        check_case('feature-finding-remains-visible', 1, pr_head=bad_head,
                   contains='introduced.py:', absent='concurrent.py:')

        # Integration-only resolutions are included, not a head-only shortcut.
        git('checkout', '-q', '--detach', merged)
        (repo / 'resolution.py').write_text("ALLOWED_VERBS = {'READ'}\n", encoding='utf-8')
        git('add', 'resolution.py')
        tree = git('write-tree').stdout.strip()
        resolved = git('commit-tree', tree, '-p', actual_base, '-p', feature_head,
                       input='integration-only addition\n').stdout.strip()
        git('checkout', '-q', '--detach', resolved)
        check_case('merge-resolution-finding-remains-visible', 1,
                   contains='resolution.py:', absent='concurrent.py:')
        git('checkout', '-q', '--detach', feature_head)
        check_case('non-merge-pr-checkout-is-not-a-pass', 1, absent='GUARD: PASS')

    print('OPEN DOOR WORKFLOW BASE TEST: ' + str(len(cases)) + ' actual-Git cases pass')
    return cases


if __name__ == "__main__":
    main()
