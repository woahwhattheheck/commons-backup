"""Deterministic, original knight puzzles for the existing community trivia app.

No server, account, network, database, or third-party dependency. The output is
ordinary multiple-choice question data, so the host keeps its existing schedule,
answer-once, reconnect, points, and leaderboard behavior.
"""
from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable

SQUARES = tuple(f"{file}{rank}" for file in "abcdefgh" for rank in range(1, 9))
DELTAS = ((1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2))


class PuzzleError(ValueError):
    """Invalid puzzle input, rather than a consumed player answer."""


def square(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[a-h][1-8]", value) is None:
        raise PuzzleError("Use a square from a1 through h8, in lowercase.")
    return value


def legal_moves(origin: str) -> tuple[str, ...]:
    origin = square(origin)
    x, y = ord(origin[0]) - 97, int(origin[1]) - 1
    return tuple(sorted(chr(97 + x + dx) + str(y + dy + 1)
                        for dx, dy in DELTAS if 0 <= x + dx < 8 and 0 <= y + dy < 8))


def shortest_route(origin: str, target: str) -> tuple[str, ...]:
    """Lexicographically deterministic BFS on the empty 8×8 board."""
    origin, target = square(origin), square(target)
    queue = deque([origin])
    previous: dict[str, str | None] = {origin: None}
    while queue:
        current = queue.popleft()
        if current == target:
            route = [current]
            while previous[current] is not None:
                current = previous[current]  # type: ignore[assignment]
                route.append(current)
            return tuple(reversed(route))
        for neighbor in legal_moves(current):
            if neighbor not in previous:
                previous[neighbor] = current
                queue.append(neighbor)
    raise PuzzleError("No knight route exists.")


def distance(origin: str, target: str) -> int:
    return len(shortest_route(origin, target)) - 1


def validate_route(route: object, origin: str, target: str) -> tuple[str, ...]:
    origin, target = square(origin), square(target)
    if not isinstance(route, (tuple, list)) or not 1 <= len(route) <= 65:
        raise PuzzleError("A route must contain 1–65 squares, including its endpoints.")
    result = tuple(square(value) for value in route)
    if result[0] != origin or result[-1] != target:
        raise PuzzleError("The route has the wrong start or destination.")
    if any(right not in legal_moves(left) for left, right in zip(result, result[1:])):
        raise PuzzleError("Every step must be a legal knight move.")
    return result


def ordered(values: Iterable[str], salt: str) -> list[str]:
    """Hash ordering avoids depending on a runtime's PRNG shuffle implementation."""
    return sorted(values, key=lambda item: (hashlib.sha256((salt + "\0" + item).encode()).digest(), item))


@dataclass(frozen=True)
class Question:
    prompt: str
    choices: tuple[str, ...]
    answer: int
    explanation: str
    kind: str
    origin: str
    target: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Canonical generator form; `adapt` maps only the consumer field names."""
        return {"prompt": self.prompt, "choices": list(self.choices), "answer": self.answer,
                "explanation": self.explanation}


def move_question(origin: str, salt: str) -> Question:
    origin = square(origin)
    legal = legal_moves(origin)
    correct = ordered(legal, salt + ":correct")[0]
    distractors = ordered((value for value in SQUARES if value != origin and value not in legal),
                          salt + ":distractors")[:3]
    choices = tuple(ordered([correct, *distractors], salt + ":choices"))
    return Question(
        f"Knight move • A knight stands on {origin} on an empty chessboard. "
        "Which square can it reach in exactly one move?",
        choices, choices.index(correct),
        f"{origin} → {correct} changes one coordinate by 2 and the other by 1. "
        "That is a knight move; none of the other choices has that displacement.",
        "move", origin, correct,
    )


def distance_question(origin: str, target: str, salt: str) -> Question:
    origin, target = square(origin), square(target)
    if origin == target:
        raise PuzzleError("A distance puzzle needs two different squares.")
    route = shortest_route(origin, target)
    correct = str(len(route) - 1)
    alternatives = [str(number) for number in range(1, 9) if str(number) != correct]
    choices = tuple(ordered([correct, *ordered(alternatives, salt + ":distractors")[:3]], salt + ":choices"))
    return Question(
        f"Knight route • On an empty chessboard, what is the minimum number of knight moves "
        f"from {origin} to {target}? Count moves, not visited squares.",
        choices, choices.index(correct),
        f"A shortest route is {' → '.join(route)}: {correct} moves. "
        "The generator checks every reachable square at each shorter distance before accepting this length.",
        "distance", origin, target,
    )


def generate(seed: str = "community-knight-week-1", count: int = 12) -> list[Question]:
    if not isinstance(seed, str) or not seed.strip() or len(seed) > 200:
        raise PuzzleError("The seed must be nonempty text up to 200 characters.")
    if type(count) is not int or not 1 <= count <= 64:
        raise PuzzleError("Choose 1–64 questions.")
    origins = ordered(SQUARES, seed + ":origins")
    questions = []
    # Balance correct-choice positions without a visible 0,1,2,3 cycle.
    position_order = [int(value) % 4 for value in ordered((str(i) for i in range(count)), seed + ":positions")]
    for index in range(count):
        origin = origins[index]
        salt = f"{seed}:question:{index}"
        if index % 2 == 0:
            questions.append(move_question(origin, salt))
        else:
            target = ordered((value for value in SQUARES if value != origin), salt + ":target")[0]
            questions.append(distance_question(origin, target, salt))
        question = questions[-1]
        correct = question.choices[question.answer]
        reordered = [value for value in question.choices if value != correct]
        reordered.insert(position_order[index], correct)
        questions[-1] = replace(question, choices=tuple(reordered), answer=position_order[index])
    return questions


def adapt(questions: Iterable[Question], *, prompt_key: str = "prompt",
          choices_key: str = "choices", answer_key: str = "answer",
          explanation_key: str | None = "explanation", answer_base: int = 0) -> list[dict[str, object]]:
    """Adapt to a verified editable question-set schema; does not submit anything.

    Set explanation_key=None when the consumer rejects extra fields. Correct
    answers remain positional indices, explicitly zero- or one-based.
    """
    keys = [prompt_key, choices_key, answer_key]
    if explanation_key is not None:
        keys.append(explanation_key)
    if any(not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", key) for key in keys):
        raise PuzzleError("Consumer field names must be simple nonempty identifiers.")
    if len(set(keys)) != len(keys):
        raise PuzzleError("Consumer field names must be distinct.")
    if type(answer_base) is not int or answer_base not in (0, 1):
        raise PuzzleError("answer_base must be 0 or 1.")
    output = []
    for item in questions:
        row = {prompt_key: item.prompt, choices_key: list(item.choices), answer_key: item.answer + answer_base}
        if explanation_key is not None:
            row[explanation_key] = item.explanation
        output.append(row)
    return output


def dumps(questions: list[dict[str, object]]) -> str:
    return json.dumps(questions, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", default="community-knight-week-1")
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--output", type=Path, help="Write a new file; existing files are preserved")
    parser.add_argument("--prompt-key", default="prompt")
    parser.add_argument("--choices-key", default="choices")
    parser.add_argument("--answer-key", default="answer")
    parser.add_argument("--explanation-key", default="explanation")
    parser.add_argument("--omit-explanation", action="store_true")
    parser.add_argument("--answer-base", type=int, choices=(0, 1), default=0)
    args = parser.parse_args(argv)
    try:
        rows = adapt(generate(args.seed, args.count), prompt_key=args.prompt_key,
                     choices_key=args.choices_key, answer_key=args.answer_key,
                     explanation_key=None if args.omit_explanation else args.explanation_key,
                     answer_base=args.answer_base)
        output = dumps(rows)
        if args.output is not None:
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(output)
        else:
            print(output, end="")
    except (PuzzleError, OSError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
