# SPDX-License-Identifier: Apache-2.0
"""Bounded exact worker-cost lookup; the fallback preserves range(n) semantics.

Returns staged source only; no live runtime, feature data, archive or service
is modified. Target methods are pinned independently of peer source changes.
"""
from __future__ import annotations
import argparse, ast, hashlib
from pathlib import Path

BEFORE = 'f3fa79d1ecb3db4b076e1555ead22ebdd3044aa97acfcfd3fe2d980e14f2205a'
AFTER = '7c41e8a0b3e20a0762613a5fc2aa5f5a2cbe4115515883275942540029b487c5'
TABLE = (1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987, 1597, 2584, 4181, 6765, 10946, 17711, 28657, 46368, 75025, 121393, 196418, 317811, 514229, 832040, 1346269, 2178309, 3524578, 5702887, 9227465, 14930352, 24157817, 39088169, 63245986, 102334155, 165580141, 267914296, 433494437, 701408733, 1134903170, 1836311903, 2971215073, 4807526976, 7778742049, 12586269025, 20365011074, 32951280099, 53316291173, 86267571272, 139583862445, 225851433717, 365435296162, 591286729879, 956722026041, 1548008755920, 2504730781961, 4052739537881, 6557470319842, 10610209857723)
DECLARATION = "_TITAN_HIRE_FIB64 = " + repr(TABLE) + "\n\n"


class SourceDriftError(ValueError):
    """The target is not a tested preimage/postimage or has a conflicting table."""


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compose_source(source: str) -> str:
    """Preserve every non-target method, including peer quote/geometry changes.

    Only exact built-in ints 0..63 use the immutable table. Negative ints, larger
    ints, bools, int subclasses, __index__ objects and errors follow the original
    code. This is not an unbounded memo cache and does not retain game state.
    """
    if not isinstance(source,str):raise TypeError("source must be decoded text")
    if "\r" in source:raise SourceDriftError("expected LF source")
    try:tree=ast.parse(source)
    except SyntaxError as error:raise SourceDriftError("invalid Python source") from error
    targets=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name=="_fib"]
    if len(targets)!=1 or targets[0].decorator_list:
        raise SourceDriftError("expected one undecorated _fib")
    node=targets[0];lines=source.splitlines(keepends=True)
    original="".join(lines[node.lineno-1:node.end_lineno]);sha=digest(original)
    for item in ast.walk(tree):
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and item.name == "_TITAN_HIRE_FIB64":
            raise SourceDriftError("table definition collision")
        if isinstance(item, ast.Name) and item.id == "_TITAN_HIRE_FIB64" and isinstance(item.ctx, ast.Del):
            raise SourceDriftError("table deletion collision")
    assignments=[n for n in ast.walk(tree) if isinstance(n,ast.Name) and n.id=="_TITAN_HIRE_FIB64" and isinstance(n.ctx,ast.Store)]
    if sha==AFTER:
        if len(assignments)!=1 or source.count(DECLARATION)!=1:
            raise SourceDriftError("postimage has missing/conflicting table")
        # The one declaration must precede the function. A downstream mutation,
        # annotated rebind, import alias or augmented assignment is not accepted.
        assignment=assignments[0]
        if assignment.lineno>=node.lineno:raise SourceDriftError("late table declaration")
        for n in ast.walk(tree):
            if isinstance(n,ast.alias) and (n.asname or n.name)=="_TITAN_HIRE_FIB64":
                raise SourceDriftError("table import alias collision")
        return source
    if sha!=BEFORE:raise SourceDriftError("_fib method drift: "+sha)
    if any(isinstance(n,ast.Name) and n.id=="_TITAN_HIRE_FIB64" for n in ast.walk(tree)):
        raise SourceDriftError("table identifier already used")
    for n in ast.walk(tree):
        if isinstance(n,ast.alias) and (n.asname or n.name)=="_TITAN_HIRE_FIB64":
            raise SourceDriftError("table import alias collision")
    replacement=original.replace("    a, b = 1, 1", "    if type(n) is int and 0 <= n < 64:\n        return _TITAN_HIRE_FIB64[n]\n    a, b = 1, 1",1)
    if digest(replacement)!=AFTER:raise SourceDriftError("postimage mismatch")
    lines[node.lineno-1:node.end_lineno]=[DECLARATION+replacement]
    result="".join(lines).replace(
        "# Mechanically extracted, unmodified definitions from Kaggle/kaggle-environments",
        "# Originally extracted (before staged transforms) from Kaggle/kaggle-environments",1)
    compile(result,"<hire-cost-composed>","exec")
    return result


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path);parser.add_argument("output",type=Path)
    args=parser.parse_args()
    if args.source.resolve()==args.output.resolve():parser.error("use a separate staged output")
    result=compose_source(args.source.read_bytes().decode("utf-8"))
    with args.output.open("x",encoding="utf-8",newline="\n") as f:f.write(result)
    print(digest(result))

if __name__=="__main__":main()
