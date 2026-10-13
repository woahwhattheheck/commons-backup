#!/usr/bin/env python3
"""muhl_collect_training_data.py — Collect ALL text files from the machine into training_data.bin.

Scans the project directories in priority order:
1. GROUNDING_CORPUS.md (core knowledge — FIRST)
2. CLAUDE.md files (spec rules)
3. Memory files from .claude/
4. .py files from LocalDeviceAgent/host/
5. Engine .py files from Titan/engines/
6. .py files from C:/llm/muhl_builds/
7. .md files from Desktop and subdirectories
8. All other text files under C:/Users/lucys/

Output: raw concatenated text with file separators.
"""
import os, sys, time

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "training_data.bin")

SKIP_DIRS = {'.git', 'node_modules', '__pycache__', '.claude/worktrees',
             'sdc_fold', 'sdc_bitmap_swarm', 'models'}
SKIP_EXTS = {'.gguf', '.bin', '.exe', '.dll', '.obj', '.o', '.so', '.pyd',
             '.pyc', '.pyo', '.whl', '.tar', '.gz', '.zip', '.7z', '.rar',
             '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.svg',
             '.mp3', '.mp4', '.wav', '.avi', '.mkv', '.mov',
             '.pdf', '.doc', '.docx', '.xls', '.xlsx',
             '.crdownload', '.tmp', '.log'}
TEXT_EXTS = {'.md', '.py', '.json', '.txt', '.html', '.css', '.js', '.ts',
             '.yaml', '.yml', '.toml', '.cfg', '.ini', '.bat', '.sh',
             '.kt', '.java', '.c', '.h', '.cpp', '.hpp', '.rs',
             '.jsonl', '.csv', '.xml', '.sql'}

SEP = b"\n\n===== FILE: %s =====\n\n"

def should_skip_dir(dirpath):
    parts = dirpath.replace("\\", "/").split("/")
    for skip in SKIP_DIRS:
        if skip in parts:
            return True
    return False

def collect_files(root, exts=None, max_size=1_000_000):
    """Walk root, yield (path, size) for text files matching exts."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        if should_skip_dir(dirpath):
            dirnames.clear()
            continue
        # Skip very deep paths
        dirnames[:] = [d for d in dirnames if not d.startswith('.git')]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in SKIP_EXTS:
                continue
            if exts and ext not in exts:
                continue
            fp = os.path.join(dirpath, fn)
            try:
                sz = os.path.getsize(fp)
                if sz > max_size or sz == 0:
                    continue
                found.append((fp, sz))
            except OSError:
                continue
    return found

def read_file_bytes(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return None

def main():
    t0 = time.time()
    total_bytes = 0
    total_files = 0

    with open(OUT, "wb") as out:
        def write_file(path, label=None):
            nonlocal total_bytes, total_files
            data = read_file_bytes(path)
            if data is None:
                return
            tag = label or path
            out.write(SEP % tag.encode("utf-8", errors="replace"))
            out.write(data)
            total_bytes += len(data)
            total_files += 1

        # Phase 1: GROUNDING_CORPUS.md (most important)
        gc = os.path.join(os.path.dirname(os.path.abspath(__file__)), "GROUNDING_CORPUS.md")
        if os.path.exists(gc):
            write_file(gc, "GROUNDING_CORPUS.md [PRIORITY: CORE KNOWLEDGE]")
            print(f"  [1] GROUNDING_CORPUS.md: {total_bytes:,} bytes")

        # Phase 2: CLAUDE.md files
        claude_md_paths = []
        for root in [r"C:\Users\lucys\.claude", r"C:\Users\lucys\OneDrive\Desktop"]:
            if os.path.isdir(root):
                for dp, dns, fns in os.walk(root):
                    if should_skip_dir(dp):
                        dns.clear()
                        continue
                    for fn in fns:
                        if fn.upper() == "CLAUDE.MD":
                            claude_md_paths.append(os.path.join(dp, fn))
        for p in claude_md_paths:
            write_file(p, f"CLAUDE.MD [{p}]")
        print(f"  [2] CLAUDE.md files: {len(claude_md_paths)} files, {total_bytes:,} bytes cumulative")

        # Phase 3: Memory files from .claude/
        mem_root = r"C:\Users\lucys\.claude"
        if os.path.isdir(mem_root):
            mem_files = collect_files(mem_root, TEXT_EXTS)
            for p, sz in mem_files:
                if "CLAUDE.MD" not in p.upper():  # already collected
                    write_file(p, f"MEMORY [{p}]")
            print(f"  [3] .claude memory: {len(mem_files)} files, {total_bytes:,} bytes cumulative")

        # Phase 4: .py from LocalDeviceAgent/host/
        lda_host = r"C:\Users\lucys\OneDrive\Desktop\LocalDeviceAgent\host"
        if os.path.isdir(lda_host):
            py_files = collect_files(lda_host, {'.py'})
            for p, sz in py_files:
                write_file(p, f"LDA_HOST [{os.path.basename(p)}]")
            print(f"  [4] LDA host .py: {len(py_files)} files, {total_bytes:,} bytes cumulative")

        # Phase 5: Engine .py from Titan/engines/
        engines = r"C:\Users\lucys\OneDrive\Desktop\Titan\engines"
        if os.path.isdir(engines):
            eng_files = collect_files(engines, {'.py'})
            for p, sz in eng_files:
                write_file(p, f"ENGINE [{os.path.basename(p)}]")
            print(f"  [5] Titan engines: {len(eng_files)} files, {total_bytes:,} bytes cumulative")

        # Phase 6: .py from C:/llm/muhl_builds/
        mb = r"C:\llm\muhl_builds"
        if os.path.isdir(mb):
            mb_files = collect_files(mb, {'.py'})
            for p, sz in mb_files:
                write_file(p, f"MUHL_BUILD [{os.path.basename(p)}]")
            print(f"  [6] muhl_builds .py: {len(mb_files)} files, {total_bytes:,} bytes cumulative")

        # Phase 7: .md from Desktop and subdirectories
        desktop = r"C:\Users\lucys\OneDrive\Desktop"
        if os.path.isdir(desktop):
            md_files = collect_files(desktop, {'.md'})
            for p, sz in md_files:
                if "GROUNDING_CORPUS" not in p and "CLAUDE.MD" not in p.upper():
                    write_file(p, f"DOC [{p}]")
            print(f"  [7] Desktop .md: {len(md_files)} files, {total_bytes:,} bytes cumulative")

        # Phase 8: All other text files under C:/Users/lucys/ (skip what we already have)
        seen = set()
        # Quick scan of remaining text
        for root_dir in [r"C:\Users\lucys\OneDrive\Desktop", r"C:\llm\sdc_sandbox",
                         r"C:\llm\sdc_out", r"C:\Users\lucys\OneDrive\Desktop\MUHLNICKEL_BUILD_LAB_20260801_025117"]:
            if os.path.isdir(root_dir):
                extra = collect_files(root_dir, TEXT_EXTS)
                for p, sz in extra:
                    if p not in seen:
                        seen.add(p)
                        write_file(p)
        print(f"  [8] Additional text: {total_bytes:,} bytes cumulative")

    dt = time.time() - t0
    final_size = os.path.getsize(OUT)
    print(f"\n  DONE: {total_files:,} files -> training_data.bin ({final_size:,} bytes / {final_size/1048576:.1f} MB)")
    print(f"  Collection time: {dt:.1f}s (host transcription time)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
