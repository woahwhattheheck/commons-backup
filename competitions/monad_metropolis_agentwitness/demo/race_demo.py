from __future__ import annotations

import json
from pathlib import Path
import sys
from threading import Barrier, Thread

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentwitness import AlreadyClaimed, InMemoryRegistry, Outcome, event_key, intent_hash, make_receipt, outcome_hash, receipt_digest


def main() -> int:
    event = {
        "version": "agentwitness-event-v1",
        "network": "monad",
        "namespace": "demo/outbound",
        "provider": "gmail",
        "event_id": "synthetic-human-reply-0001",
    }
    key = event_key(event)
    registry = InMemoryRegistry()
    racers = 64
    barrier = Barrier(racers)
    winners: list[tuple[str, str]] = []
    losers: list[str] = []

    def worker(i: int) -> None:
        claimant = "0x" + f"{i + 1:040x}"
        draft = f"private draft {i}".encode()
        barrier.wait()
        try:
            registry.claim(key, claimant, intent_hash(draft))
            winners.append((claimant, draft.decode()))
        except AlreadyClaimed:
            losers.append(claimant)

    threads = [Thread(target=worker, args=(i,)) for i in range(racers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(winners) == 1
    winner, _ = winners[0]
    registry.finalize(key, winner, Outcome.COMPLETED, outcome_hash(b"synthetic provider SENT id=demo-1"))
    claim = registry.read(key)
    assert claim is not None
    receipt = make_receipt(key, claim)
    print(json.dumps({
        "event_key": key,
        "workers": racers,
        "claim_winners": len(winners),
        "claim_losers": len(losers),
        "winner": winner,
        "effective_outcome": registry.effective_outcome(key),
        "receipt_digest": receipt_digest(receipt),
        "receipt": receipt,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
