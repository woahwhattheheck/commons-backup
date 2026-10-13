from .cli import main
from .model import BundleError, REQUIRED_PATHWAYS, SCHEMA_VERSION, load_json_bytes
from .validate import validate_bundle

__all__ = [
    "BundleError", "REQUIRED_PATHWAYS", "SCHEMA_VERSION",
    "load_json_bytes", "main", "validate_bundle",
]

if __name__ == "__main__":
    raise SystemExit(main())
