"""Extract decryption key from Heartopia global-metadata.dat."""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from UnityPy.helpers.ArchiveStorageManager import brute_force_key

# Load configuration from .env if present
load_dotenv()

DEFAULT_METADATA_PATH: Optional[Path] = (
    Path(os.environ["HEARTOPIA_METADATA_PATH"]) if os.getenv("HEARTOPIA_METADATA_PATH") else None
)
KEY_SIGNATURE: bytes = b'(#miNL!G C{Fv"=_'
DATA_SIGNATURE: bytes = b"\xf5\xaa(\xdb\x116v\xba\xc5\x96dd\xbc\xaf\xc2v"


def resolve_heartopia_key(metadata_path: Optional[Path] = None) -> bytes:
    """Brute-force and extract the AssetBundle decryption key from global-metadata.dat.

    Args:
        metadata_path: Path to global-metadata.dat. Defaults to HEARTOPIA_METADATA_PATH from .env.

    Returns:
        The extracted 16-byte decryption key.

    Raises:
        ValueError: If no metadata path is configured, or if key extraction fails.
        FileNotFoundError: If the metadata file does not exist.
    """
    path = metadata_path or DEFAULT_METADATA_PATH
    if path is None:
        raise ValueError(
            "No metadata path configured. Set HEARTOPIA_METADATA_PATH in .env or pass "
            "--metadata-path."
        )
    if not path.exists():
        raise FileNotFoundError(f"Metadata file not found at: {path}")

    key: Optional[bytes] = brute_force_key(path, KEY_SIGNATURE, DATA_SIGNATURE)
    if not key:
        raise ValueError(f"Failed to find valid decryption key from {path}")
    return key


if __name__ == "__main__":
    found_key = resolve_heartopia_key()
    print(f"Decryption key: {found_key}")
