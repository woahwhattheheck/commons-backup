from pathlib import Path
import tempfile

from civic_ledger.core import DocumentSnapshot, Ledger, compile_ledger, verify_bundle, write_bundle

ROOT = Path(__file__).resolve().parent
ledger = Ledger("riverton-2026-09-12")
for doc_id, kind, observed, name in [
    ("agenda-v1", "agenda", "2026-09-09T14:00:00Z", "sample_agenda.txt"),
    ("addendum-v1", "addendum", "2026-09-10T14:00:00Z", "sample_addendum.txt"),
    ("minutes-v1", "minutes", "2026-09-12T20:00:00Z", "sample_minutes.txt"),
]:
    ledger.add(DocumentSnapshot.create(
        meeting_id=ledger.meeting_id, doc_id=doc_id, kind=kind,
        source_url=f"https://civic.example/{doc_id}", observed_at=observed,
        text=(ROOT / "fixtures" / name).read_text("utf-8"),
    ))
compiled = compile_ledger(ledger, as_of="2026-09-13T16:30:00Z")
with tempfile.TemporaryDirectory() as td:
    manifest = write_bundle(compiled, td)
    verified = verify_bundle(td)
    print(f"meeting={compiled['meeting_id']} freshness={compiled['freshness']} items={len(compiled['items'])}")
    for item in compiled["items"]:
        print(f"{item['item_id']}: {item['state']} owner={item['owner']!r} deadline={item['deadline']!r}")
    print(f"bundle={verified['ok']} compile_sha256={manifest['compile_sha256']}")
