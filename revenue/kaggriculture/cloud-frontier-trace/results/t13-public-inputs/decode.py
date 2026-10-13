"""Restore exact PUBLIC replay HTTP bodies from the adjacent transport files."""
import base64, gzip, hashlib, json
from pathlib import Path

def restore(directory):
    directory = Path(directory)
    receipt = json.loads((directory / "receipt.json").read_text())
    outputs = []
    for row in receipt["episodes"]:
        eid = row["episode_id"]
        packed = base64.b64decode((directory / f"{eid}.raw.gz.b64").read_text().strip(), validate=True)
        assert hashlib.sha256(packed).hexdigest() == row["gzip_sha256"]
        data = gzip.decompress(packed)
        assert len(data) == row["raw_bytes"]
        assert hashlib.sha256(data).hexdigest() == row["raw_sha256"]
        replay = json.loads(data)
        assert replay["info"]["EpisodeId"] == eid
        terminal = replay["steps"][-1]
        assert terminal[row["own_seat"]]["reward"] == row["own_cash"]
        assert terminal[row["rival_seat"]]["reward"] == row["rival_cash"]
        path = directory / f"{eid}.raw"
        path.write_bytes(data)
        outputs.append(path)
    return outputs

if __name__ == "__main__":
    for path in restore(Path(__file__).parent):
        print(path.name)
