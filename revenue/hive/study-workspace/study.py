"""Source-bound practice generation and durable review state; Python stdlib only."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path

MAX_UPLOAD = 8 * 1024 * 1024
MAX_TEXT = 2_000_000
MAX_CARDS = 80
STOP = set("about after again also before being between could from have into other should their there these those through using where which while would".split())


class Conflict(ValueError):
    """The same operation identifier was reused with different content."""


def normalized(value: str) -> str:
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", value).casefold()))


def text_value(value, name: str, limit: int = 4000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must contain 1 to {limit} characters.")
    return value.strip()


def extract_pages(raw: bytes, filename: str) -> tuple[str, list[str]]:
    """Keep extraction in this process's machine; PDF conversion makes no requests."""
    if not raw or len(raw) > MAX_UPLOAD:
        raise ValueError("Choose a nonempty file of at most 8 MiB.")
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        if not raw.startswith(b"%PDF-"):
            raise ValueError("The file does not have a PDF header.")
        executable = shutil.which("pdftotext")
        if not executable:
            raise ValueError("PDF import needs Poppler's pdftotext. Text and Markdown import work without it.")
        with tempfile.TemporaryDirectory(prefix="hive-study-") as directory:
            source = Path(directory) / "input.pdf"
            source.write_bytes(raw)
            try:
                result = subprocess.run(
                    [executable, "-layout", "-enc", "UTF-8", str(source), "-"],
                    capture_output=True, timeout=20, check=False,
                )
            except (subprocess.TimeoutExpired, OSError) as exc:
                raise ValueError("PDF text extraction did not complete; try a smaller text-PDF or paste its text.") from exc
            if result.returncode:
                raise ValueError("PDF text extraction did not succeed; use a readable text-PDF or paste its text.")
            text = result.stdout.decode("utf-8", errors="replace")
        kind = "pdf"
    elif suffix in {".txt", ".md", ".markdown"}:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Save notes as UTF-8 text before importing.") from exc
        kind = "text"
    else:
        raise ValueError("Choose a .txt, .md, .markdown, or text-PDF file.")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if len(text) > MAX_TEXT:
        raise ValueError("The extracted text exceeds 2 million characters; split the chapter.")
    if not text.strip() or "\x00" in text:
        raise ValueError("No readable text was found. Scanned images need a separate transcription; no OCR is performed.")
    pages = text.split("\f")
    while pages and not pages[-1].strip():
        pages.pop()
    return kind, pages


def generate_cards(pages: list[str]) -> list[dict]:
    """Create inspectable definition/cloze prompts, never invented explanations."""
    definitions, clozes, seen = [], [], set()
    definition = re.compile(r"^(.{2,75}?)(?::\s+|\s+[–—]\s+|\s+(?:is|are|means|refers to)\s+)(.{10,600})$", re.I)
    for page, body in enumerate(pages, 1):
        lines = body.splitlines()
        for line_number, original in enumerate(lines, 1):
            line = re.sub(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", "", original).strip()
            if line.startswith("#") or len(line) < 20:
                continue
            match = definition.match(line)
            if match:
                answer, description = match.groups()
                answer = answer.strip(" *_.:;\t")
                if not normalized(answer) or len(answer.split()) > 10:
                    continue
                prompt = "Which term matches this definition?\n\n" + description
                card_type = "definition"
            else:
                # Generic prose gets a literal cloze, not a guessed fact or question.
                words = re.findall(r"\b[^\W\d_]{5,}\b", line, re.UNICODE)
                choices = [word for word in words if word.casefold() not in STOP]
                if not choices or len(line) < 40 or len(line) > 650:
                    continue
                answer = max(choices, key=len)
                prompt = "Complete the source sentence.\n\n" + re.sub(r"\b" + re.escape(answer) + r"\b", "[ … ]", line, flags=re.I)
                card_type = "cloze"
            signature = normalized(prompt)
            if signature in seen:
                continue
            seen.add(signature)
            card = dict(prompt=prompt, answer=answer, aliases=[], kind=card_type,
                        page=page, line_start=line_number, line_end=line_number,
                        quote=original, explanation="Compare your answer with the quoted source and the editable answer key.")
            (definitions if card_type == "definition" else clozes).append(card)
    return (definitions + clozes)[:MAX_CARDS]


class Workspace:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, filename TEXT NOT NULL,
                    kind TEXT NOT NULL, pages TEXT NOT NULL, original BLOB NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS cards (
                    id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    prompt TEXT NOT NULL, answer TEXT NOT NULL, aliases TEXT NOT NULL,
                    kind TEXT NOT NULL, page INTEGER NOT NULL, line_start INTEGER NOT NULL,
                    line_end INTEGER NOT NULL, quote TEXT NOT NULL, explanation TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 1, due_at REAL NOT NULL DEFAULT 0,
                    interval_days REAL NOT NULL DEFAULT 0, repetitions INTEGER NOT NULL DEFAULT 0,
                    lapses INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    request_id TEXT PRIMARY KEY, card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
                    submitted TEXT NOT NULL, revision INTEGER NOT NULL, result TEXT NOT NULL, created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS cards_document_due ON cards(document_id, due_at);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def import_document(self, raw: bytes, filename: str, title: str = "") -> dict:
        filename = text_value(filename, "Filename", 200)
        title = text_value(title or Path(filename).stem, "Title", 160)
        document_id = hashlib.sha256(raw).hexdigest()
        # A repeat import preserves tutor edits and review progress.
        with self.connection() as db:
            old = db.execute("SELECT id FROM documents WHERE id=?", (document_id,)).fetchone()
            if old:
                return {"id": document_id, "duplicate": True, "cards": db.execute("SELECT COUNT(*) FROM cards WHERE document_id=?", (document_id,)).fetchone()[0]}
        kind, pages = extract_pages(raw, filename)
        cards = generate_cards(pages)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            inserted = db.execute("INSERT OR IGNORE INTO documents VALUES(?,?,?,?,?,?,?)", (document_id, title, filename, kind, json.dumps(pages, ensure_ascii=False), raw, time.time())).rowcount
            if inserted:
                for ordinal, card in enumerate(cards):
                    card_id = hashlib.sha256(f"{document_id}:{ordinal}".encode()).hexdigest()[:24]
                    db.execute("""INSERT INTO cards(id,document_id,prompt,answer,aliases,kind,page,line_start,line_end,quote,explanation)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (card_id, document_id, card["prompt"], card["answer"], "[]", card["kind"], card["page"], card["line_start"], card["line_end"], card["quote"], card["explanation"]))
            total = db.execute("SELECT COUNT(*) FROM cards WHERE document_id=?", (document_id,)).fetchone()[0]
        return {"id": document_id, "duplicate": not bool(inserted), "cards": total,
                "notice": "No practice cards could be derived. The source is saved; import explicit term: definition notes to generate a set." if total == 0 else "Review the generated prompts and keys before studying."}

    def documents(self, now: float | None = None) -> list[dict]:
        now = time.time() if now is None else now
        with self.connection() as db:
            return [dict(row) for row in db.execute("""SELECT d.id,d.title,d.filename,d.kind,d.created_at,
                COUNT(c.id) AS cards, COALESCE(SUM(c.due_at<=?),0) AS due,
                COALESCE(SUM(c.attempts),0) AS attempts
                FROM documents d LEFT JOIN cards c ON d.id=c.document_id
                GROUP BY d.id ORDER BY d.created_at DESC,d.id""", (now,))]

    def document(self, document_id: str, original: bool = False) -> dict:
        with self.connection() as db:
            row = db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
            if row is None:
                raise KeyError("Document not found.")
            result = dict(row)
            result["pages"] = json.loads(result["pages"])
            if not original:
                result.pop("original")
            return result

    @staticmethod
    def _card(row) -> dict:
        card = dict(row)
        card["aliases"] = json.loads(card["aliases"])
        card["source_url"] = f'/source/{card["document_id"]}#p{card["page"]}-l{card["line_start"]}'
        return card

    def cards(self, document_id: str, due: bool = False, now: float | None = None) -> list[dict]:
        self.document(document_id)
        now = time.time() if now is None else now
        with self.connection() as db:
            query = "SELECT * FROM cards WHERE document_id=?"
            params = [document_id]
            if due:
                query += " AND due_at<=?"
                params.append(now)
            return [self._card(row) for row in db.execute(query + " ORDER BY due_at,id", params)]

    def edit_card(self, card_id: str, values: dict) -> dict:
        prompt = text_value(values.get("prompt"), "Prompt", 2000)
        answer = text_value(values.get("answer"), "Answer", 500)
        explanation = text_value(values.get("explanation"), "Explanation", 2000)
        aliases = values.get("aliases", [])
        revision = values.get("revision")
        if type(revision) is not int or revision < 1:
            raise ValueError("Supply the displayed card revision.")
        if not isinstance(aliases, list) or len(aliases) > 20:
            raise ValueError("Use at most 20 answer variants.")
        aliases = [text_value(alias, "Answer variant", 500) for alias in aliases]
        if not normalized(answer) or any(not normalized(alias) for alias in aliases):
            raise ValueError("Answers need at least one letter or number.")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
            if old is None:
                raise KeyError("Card not found.")
            if old["revision"] != revision:
                raise Conflict("The card changed in another tab. Reload its current key before editing.")
            db.execute("""UPDATE cards SET prompt=?,answer=?,aliases=?,explanation=?,revision=revision+1,
                due_at=0,interval_days=0,repetitions=0 WHERE id=?""", (prompt, answer, json.dumps(aliases, ensure_ascii=False), explanation, card_id))
            return self._card(db.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone())

    def review(self, card_id: str, submitted: str, request_id: str, revision: int, now: float | None = None) -> dict:
        if not isinstance(submitted, str) or len(submitted) > 2000:
            raise ValueError("Answer must be text of at most 2000 characters.")
        request_id = text_value(request_id, "Review identifier", 100)
        if type(revision) is not int or revision < 1:
            raise ValueError("Supply the displayed card revision.")
        now = time.time() if now is None else now
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT * FROM reviews WHERE request_id=?", (request_id,)).fetchone()
            if previous:
                if previous["card_id"] != card_id or previous["submitted"] != submitted or previous["revision"] != revision:
                    raise Conflict("Review identifier already describes another answer.")
                return json.loads(previous["result"])
            row = db.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
            if row is None:
                raise KeyError("Card not found.")
            card = self._card(row)
            if card["revision"] != revision:
                raise Conflict("The answer key changed. Reload this card before checking your answer.")
            correct = normalized(submitted) in {normalized(value) for value in [card["answer"], *card["aliases"]]}
            repetitions = card["repetitions"] + 1 if correct else 0
            interval = (1 if repetitions == 1 else 3 if repetitions == 2 else min(180, card["interval_days"] * 2)) if correct else 0
            due_at = now + (interval * 86400 if correct else 600)
            result = dict(card_id=card_id, correct=correct, answer=card["answer"], submitted=submitted,
                          explanation=card["explanation"], quote=card["quote"], source_url=card["source_url"],
                          page=card["page"], line_start=card["line_start"], revision=revision, due_at=due_at,
                          interval_days=interval, request_id=request_id,
                          feedback="Matches the editable answer key." if correct else "Does not match the editable key. Compare the source; a valid wording variant can be added by the tutor.")
            db.execute("UPDATE cards SET due_at=?,interval_days=?,repetitions=?,lapses=lapses+?,attempts=attempts+1 WHERE id=?", (due_at, interval, repetitions, int(not correct), card_id))
            db.execute("INSERT INTO reviews VALUES(?,?,?,?,?,?)", (request_id, card_id, submitted, revision, json.dumps(result, ensure_ascii=False), now))
            return result

    def export(self, document_id: str) -> dict:
        # One WAL read snapshot keeps history and counters consistent with each
        # other even when another browser commits an answer during the export.
        with self.connection() as db:
            db.execute("BEGIN")
            row = db.execute("SELECT id,title,filename,kind,pages,created_at FROM documents WHERE id=?", (document_id,)).fetchone()
            if row is None:
                raise KeyError("Document not found.")
            document = dict(row)
            reviews = [dict(row) for row in db.execute("SELECT r.* FROM reviews r JOIN cards c ON r.card_id=c.id WHERE c.document_id=? ORDER BY r.created_at,r.request_id", (document_id,))]
            cards = [self._card(row) for row in db.execute("SELECT * FROM cards WHERE document_id=? ORDER BY due_at,id", (document_id,))]
        document["pages"] = json.loads(document["pages"])
        for review in reviews:
            review["result"] = json.loads(review["result"])
        return {"format": "hive-study-export-v1", "document": document, "cards": cards, "reviews": reviews}

    def delete_document(self, document_id: str) -> None:
        with self.connection() as db:
            db.execute("DELETE FROM documents WHERE id=?", (document_id,))
