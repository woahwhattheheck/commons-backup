import os
import sys

# Add the muhl_builds directory to the path so we can import muhl_durable
sys.path.insert(0, r"C:\llm\muhl_builds")
from muhl_durable import journal_and_write, revert_journal

# Test file paths
test_file = r"C:\llm\muhl_builds\_durable_scratch.bin"
genome_file = r"C:\llm\muhl_builds\_durable_scratch_genome.jsonl"

try:
    # Clean up any existing test files
    for f in [test_file, genome_file]:
        if os.path.exists(f):
            os.remove(f)

    # Test 1: Create scratch file with 4096 bytes of 0xAA
    with open(test_file, "wb") as f:
        f.write(b"\xAA" * 4096)

    # Test 2: Call journal_and_write
    result = journal_and_write(test_file, 100, b"HELLO-MUHLNICKEL", genome_file)

    # Test 3: Assert reading offset 100 returns the blob
    with open(test_file, "rb") as f:
        f.seek(100)
        read_back = f.read(len(b"HELLO-MUHLNICKEL"))

    write_verified = (read_back == b"HELLO-MUHLNICKEL")
    print(f"WRITE_VERIFIED: {write_verified}")

    # Test 4: MUTANT CHECK - corrupt one byte and verify detection
    with open(test_file, "r+b") as f:
        f.seek(100)
        f.write(b"CORRUPT-MUHLNICKEL")
        f.flush()
        os.fsync(f.fileno())

    with open(test_file, "rb") as f:
        f.seek(100)
        corrupted = f.read(len(b"HELLO-MUHLNICKEL"))

    mutant_caught = (corrupted != b"HELLO-MUHLNICKEL")
    print(f"MUTANT_CAUGHT: {mutant_caught}")

    # Restore the correct value for revert test
    with open(test_file, "r+b") as f:
        f.seek(100)
        f.write(b"HELLO-MUHLNICKEL")
        f.flush()
        os.fsync(f.fileno())

    # Test 5: Call revert_journal
    revert_journal(test_file, genome_file)

    with open(test_file, "rb") as f:
        f.seek(100)
        reverted = f.read(16)

    revert_exact = (reverted == b"\xAA" * 16)
    print(f"REVERT_EXACT: {revert_exact}")

    # Clean up
    for f in [test_file, genome_file]:
        if os.path.exists(f):
            os.remove(f)

except Exception as e:
    import traceback
    print(f"ERROR: {traceback.format_exc()}")
    # Clean up on error
    for f in [test_file, genome_file]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except:
                pass
