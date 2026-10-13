#!/usr/bin/env python3
"""Stop a private repo's CI workflows from auto-running on billed GitHub runners.

Two edits to every check workflow (only push, pull_request, workflow_dispatch
or merge_group triggers):

1. Drop duplicate `python -O` reruns. A step that only reruns the suite under
   -O is deleted; -O command lines inside a larger step are removed.
2. Add this condition to every job of every check workflow (a workflow whose only
triggers are push, pull_request, workflow_dispatch or merge_group):

    if: ${{ (vars.HOSTED_CI == 'on' || github.event_name == 'workflow_dispatch') && (<existing if>) }}

Skipped jobs use no Actions minutes. The "Run workflow" button still runs the
job, and setting the repo variable HOSTED_CI=on turns automatic runs back on.
Workflows with other triggers (schedule, issues, issue_comment, ...) are left
alone. Sessions already run their changes in their own VMs.

    python3 hosted_ci_gate.py [REPO_ROOT]           # apply
    python3 hosted_ci_gate.py --check [REPO_ROOT]   # exit 1 if any check job is ungated

Idempotent. Each edited file is re-parsed and must equal the original with
exactly those two edits applied to its parsed form.
"""

import os
import re
import sys

import yaml

GATE = "vars.HOSTED_CI == 'on' || github.event_name == 'workflow_dispatch'"
CHECK_ONLY = {"push", "pull_request", "workflow_dispatch", "merge_group"}
JOB = re.compile(r"^  (?![\s#])([^:]+):\s*(#.*)?$")
IF_LINE = re.compile(r"^    if:\s*(.*?)\s*$")


def triggers(doc):
    on = doc.get(True, doc.get("on")) or {}
    if isinstance(on, str):
        return {on}
    return set(on)


def unwrap(expr):
    expr = expr.strip()
    if len(expr) >= 2 and expr[0] == expr[-1] and expr[0] in "'\"":
        expr = expr[1:-1]
    m = re.fullmatch(r"\$\{\{\s*(.*?)\s*\}\}", expr, re.S)
    return m.group(1) if m else expr


def _boolean_parts(expr, operator):
    """Split a top-level boolean operator without reading quoted text as code."""
    parts, start, depth, quoted, i = [], 0, 0, False, 0
    while i < len(expr):
        char = expr[i]
        if char == "'":
            if quoted and i + 1 < len(expr) and expr[i + 1] == "'":
                i += 2
                continue
            quoted = not quoted
        elif not quoted:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth < 0:
                    return None
            elif depth == 0 and expr.startswith(operator, i):
                parts.append(expr[start:i].strip())
                i += len(operator)
                start = i
                continue
        i += 1
    if depth or quoted:
        return None
    parts.append(expr[start:].strip())
    return parts if all(parts) else None


def has_ci_gate(value):
    """Prove every passing branch requires explicit opt-in or a manual run.

    A substring is insufficient: `HOSTED_CI != 'on'`, a quoted mention or an
    unrelated OR branch must not certify automatically billed jobs as gated.
    Unknown expressions are conservatively wrapped with the standard gate.
    """
    expr = unwrap(str(value)).strip()
    while expr.startswith("(") and expr.endswith(")"):
        inner = expr[1:-1].strip()
        if _boolean_parts(inner, "||") is None:
            break
        expr = inner
    alternatives = _boolean_parts(expr, "||")
    if alternatives is None:
        return False
    if len(alternatives) > 1:
        return all(has_ci_gate(part) for part in alternatives)
    requirements = _boolean_parts(expr, "&&")
    if requirements is None:
        return False
    if len(requirements) > 1:
        return any(has_ci_gate(part) for part in requirements)
    return bool(re.fullmatch(
        r"(?:vars\.HOSTED_CI\s*==\s*'on'|github\.event_name\s*==\s*'workflow_dispatch')",
        expr,
    ))


RERUN_LINE = re.compile(r"^(?:\w+=\S*\s+)*python[\w.]*\s.*?(?<!\S)-O+(?!\S)")
STEP = re.compile(r"^(\s*)- ")
RUN = re.compile(r"^(\s*)(?:- )?run:\s*(.*?)\s*$")


def drop_rerun_lines(lines, strip=lambda l: l.strip()):
    out, cont = [], False
    for line in lines:
        if cont:
            cont = line.rstrip().endswith("\\")
            continue
        if RERUN_LINE.match(strip(line)):
            cont = line.rstrip().endswith("\\")
            continue
        out.append(line)
    return out


def drop_reruns_text(text):
    lines = text.split("\n")
    out, i = [], 0
    while i < len(lines):
        m = STEP.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        indent = len(m.group(1))
        end = i + 1
        while end < len(lines) and (not lines[end].strip()
                                    or len(lines[end]) - len(lines[end].lstrip()) > indent):
            end += 1
        while end > i + 1 and not lines[end - 1].strip():
            end -= 1
        out.extend(edit_step(lines[i:end]))
        i = end
    return "\n".join(out)


def edit_step(block):
    for n, line in enumerate(block):
        m = RUN.match(line)
        if not m:
            continue
        value = m.group(2)
        if value in ("|", "|-", "|+"):
            key_indent = len(m.group(1)) + (2 if line.lstrip().startswith("- ") else 0)
            end = n + 1
            while end < len(block) and (not block[end].strip()
                                        or len(block[end]) - len(block[end].lstrip()) > key_indent):
                end += 1
            body = drop_rerun_lines(block[n + 1:end])
            if not any(l.strip() for l in body):
                return []
            return block[:n + 1] + body + block[end:]
        if value in (">", ">-", ">+"):
            folded = " ".join(l.strip() for l in block[n + 1:] if l.strip()
                              and len(l) - len(l.lstrip()) > len(m.group(1)))
            return [] if RERUN_LINE.match(folded) else block
        if value and RERUN_LINE.match(value.strip("'\"")):
            return []
        return block
    return block


def drop_reruns_doc(doc):
    for job in (doc.get("jobs") or {}).values():
        steps = (job or {}).get("steps")
        if not isinstance(steps, list):
            continue
        kept = []
        for step in steps:
            run = step.get("run") if isinstance(step, dict) else None
            if isinstance(run, str):
                trail = run.endswith("\n")
                body = drop_rerun_lines(run.rstrip("\n").split("\n"))
                if not any(l.strip() for l in body):
                    continue
                step = dict(step, run="\n".join(body) + ("\n" if trail else ""))
            kept.append(step)
        job["steps"] = kept
    return doc


def gate_text(text):
    lines = text.split("\n")
    try:
        start = next(i for i, l in enumerate(lines) if re.match(r"^jobs:\s*(#.*)?$", l))
    except StopIteration:
        return text
    out, i = lines[:start + 1], start + 1
    while i < len(lines):
        line = lines[i]
        if line and not line[0].isspace() and not line.startswith("#"):
            out.extend(lines[i:])
            break
        out.append(line)
        i += 1
        if not JOB.match(line):
            continue
        body = []
        while i < len(lines):
            nxt = lines[i]
            if JOB.match(nxt) or (nxt and not nxt[0].isspace() and not nxt.startswith("#")):
                break
            body.append(nxt)
            i += 1
        out.extend(gate_job(body))
    return "\n".join(out)


def condition_text(value):
    """Decode one YAML condition scalar into GitHub expression text.

    Strings keep their decoded characters. Booleans and null stay the expression
    literals `true`, `false` and `null` so an always-on job remains runnable
    after the standard gate is added.
    """
    loaded = yaml.safe_load(value)
    if isinstance(loaded, str):
        return loaded
    if isinstance(loaded, bool):
        return "true" if loaded else "false"
    if loaded is None:
        return "null" if str(value).strip() else ""
    return str(loaded)


def gate_job(body):
    for n, line in enumerate(body):
        m = IF_LINE.match(line)
        if not m:
            continue
        value, end = m.group(1), n + 1
        if value in ("", ">", ">-", "|", "|-"):
            while end < len(body) and (body[end].startswith("      ") or not body[end].strip()):
                end += 1
            value = " ".join(l.strip() for l in body[n + 1:end] if l.strip())
        # Read the scalar as YAML so inline comments and YAML quoting never
        # become part of the expression inserted inside the new condition.
        # Keep GitHub literals: PyYAML spells booleans and null as True/False/None.
        existing = unwrap(condition_text(value))
        if has_ci_gate(existing):
            return body
        merged = f"    if: ${{{{ ({GATE}) && ({existing}) }}}}"
        return body[:n] + [merged] + body[end:]
    return [f"    if: ${{{{ {GATE} }}}}"] + body


def step_ids(doc):
    return {step["id"] for job in (doc.get("jobs") or {}).values()
            for step in (job or {}).get("steps") or [] if isinstance(step, dict) and "id" in step}


def strip_ifs(doc):
    for job in (doc.get("jobs") or {}).values():
        if isinstance(job, dict):
            job.pop("if", None)
    return doc


def ungated_jobs(doc):
    return [name for name, job in (doc.get("jobs") or {}).items()
            if not has_ci_gate((job or {}).get("if", ""))]


def edit(text, drop):
    """Apply the edits; None if the result does not re-parse to the expected document."""
    new = gate_text(drop_reruns_text(text) if drop else text)
    new_doc = yaml.safe_load(new)
    original = yaml.safe_load(text)
    expected = drop_reruns_doc(yaml.safe_load(text)) if drop else original
    dropped_ids = step_ids(original) - step_ids(new_doc)
    if any(f"steps.{sid}." in new for sid in dropped_ids) or ungated_jobs(new_doc) \
            or strip_ifs(new_doc) != strip_ifs(expected) \
            or any(not (job or {}).get("steps") for job in (new_doc.get("jobs") or {}).values()
                   if "uses" not in (job or {})):
        return None
    return new


def main(argv):
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    wf_dir = os.path.join(args[0] if args else ".", ".github", "workflows")
    changed, missing, skipped, kept_reruns = 0, [], [], []
    for name in sorted(os.listdir(wf_dir)):
        if not name.endswith((".yml", ".yaml")):
            continue
        path = os.path.join(wf_dir, name)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        doc = yaml.safe_load(text) or {}
        if not triggers(doc) or not triggers(doc) <= CHECK_ONLY:
            continue
        if check:
            missing += [f"{name}:{job}" for job in ungated_jobs(doc)]
            continue
        new = edit(text, drop=True)
        if new is None:
            new = edit(text, drop=False)
            kept_reruns.append(name)
        if new is None:
            skipped.append(name)
            continue
        if new == text:
            continue
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new)
        changed += 1
    if check:
        for item in missing:
            print(f"ungated: {item}")
        return 1 if missing else 0
    print(f"hosted_ci_gate: edited {changed} workflow file(s) in {wf_dir}")
    for name in kept_reruns:
        print(f"  gated, -O rerun kept (a later step reads its result): {name}")
    for name in skipped:
        print(f"  not edited (edit did not round-trip, fix by hand): {name}")
    if skipped:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
