"""
FABRICATION-TIME ONLY. Not a runtime component. The host's two runtime verbs are unaffected.
"""
import os
import json
import hashlib
import ast


def journal_and_write(path, off, blob, genome_path, action="fab"):
    """
    Write blob to path at offset off with journaling.

    1. Read original bytes from path at offset off
    2. Journal the original to genome_path as JSON
    3. Write blob to path
    4. Verify the write by reading back
    """
    # Step 1: Read original
    with open(path, "rb") as f:
        f.seek(off)
        orig = f.read(len(blob))

    # Step 2: Journal the write (BEFORE touching the target)
    journal_entry = {
        "action": action,
        "off": off,
        "len": len(blob),
        "orig": orig.hex()
    }
    with open(genome_path, "a") as f:
        f.write(json.dumps(journal_entry) + "\n")
        f.flush()
        os.fsync(f.fileno())

    # Step 3: Write to the target file
    with open(path, "r+b") as f:
        f.seek(off)
        f.write(blob)
        f.flush()
        os.fsync(f.fileno())

    # Step 4: Verify from storage
    with open(path, "rb") as f:
        f.seek(off)
        read_back = f.read(len(blob))

    if read_back != blob:
        # Find first differing byte
        for i in range(len(blob)):
            if i >= len(read_back) or read_back[i] != blob[i]:
                raise RuntimeError(f"Verification failed at offset {off}, first diff at byte {i}")
        raise RuntimeError(f"Verification failed at offset {off}")

    # Step 5: Return result
    return {
        "off": off,
        "len": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "verified": True
    }


def revert_journal(path, genome_path):
    """
    Revert all writes in genome_path in REVERSE order.
    """
    if not os.path.exists(genome_path):
        return 0

    # Read all journal entries
    entries = []
    with open(genome_path, "r") as f:
        for line in f:
            entries.append(json.loads(line.strip()))

    # Apply in REVERSE order
    for entry in reversed(entries):
        off = entry["off"]
        orig_blob = bytes.fromhex(entry["orig"])

        with open(path, "r+b") as f:
            f.seek(off)
            f.write(orig_blob)
            f.flush()
            os.fsync(f.fileno())

    # Verify all reverted regions
    for entry in entries:
        off = entry["off"]
        orig_blob = bytes.fromhex(entry["orig"])

        with open(path, "rb") as f:
            f.seek(off)
            read_back = f.read(len(orig_blob))

        if read_back != orig_blob:
            raise RuntimeError(f"Revert verification failed at offset {off}")

    return len(entries)


def scan_unsynced(root):
    """
    Scan Python files in root for functions with write() calls but no os.fsync() calls.
    """
    findings = []

    for dirpath, dirnames, filenames in os.walk(root):
        for filename in filenames:
            if not filename.endswith(".py"):
                continue

            filepath = os.path.join(dirpath, filename)
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    code = f.read()
                tree = ast.parse(code)
            except Exception:
                continue

            # Find all function definitions
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    has_write = False
                    has_fsync = False

                    # Check all calls within this function
                    for subnode in ast.walk(node):
                        if isinstance(subnode, ast.Call):
                            # Check for write() call
                            if isinstance(subnode.func, ast.Name):
                                if subnode.func.id == "write":
                                    has_write = True
                            elif isinstance(subnode.func, ast.Attribute):
                                if subnode.func.attr == "write":
                                    has_write = True
                                # Check for os.fsync()
                                if subnode.func.attr == "fsync":
                                    if isinstance(subnode.func.value, ast.Name) and subnode.func.value.id == "os":
                                        has_fsync = True

                    if has_write and not has_fsync:
                        findings.append({
                            "file": filepath,
                            "func": node.name,
                            "line": node.lineno
                        })

    return findings


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "scan":
        root_path = r"C:\Users\lucys\Desktop\LocalDeviceAgent\host"
        results = scan_unsynced(root_path)

        for finding in results:
            print(f"{finding['file']}:{finding['line']} {finding['func']}")

        print(f"UNSYNCED_FUNCTIONS: {len(results)}")
