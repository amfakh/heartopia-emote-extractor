"""Extract decryption key dynamically from Heartopia AssetBundle and metadata."""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from UnityPy.helpers.ArchiveStorageManager import brute_force_key, read_vector
from UnityPy.streams import EndianBinaryReader

# Load configuration from .env if present
load_dotenv()

DEFAULT_METADATA_PATH: Optional[Path] = (
    Path(os.environ["HEARTOPIA_METADATA_PATH"]) if os.getenv("HEARTOPIA_METADATA_PATH") else None
)
DEFAULT_BUNDLE_DIR: Optional[Path] = (
    Path(os.environ["HEARTOPIA_BUNDLE_DIR"]) if os.getenv("HEARTOPIA_BUNDLE_DIR") else None
)


def extract_bundle_signatures(bundle_path: Path) -> tuple[bytes, bytes]:
    """Extract UnityCN encryption key_sig and data_sig dynamically from bundle header.

    Args:
        bundle_path: Path to any encrypted .ab bundle file.

    Returns:
        Tuple of (key_sig, data_sig).

    Raises:
        ValueError: If bundle is unreadable or not encrypted with UnityCN.
    """
    with bundle_path.open("rb") as f:
        reader = EndianBinaryReader(f.read(1024))

    signature = reader.read_string_to_null()
    if signature != "UnityFS":
        raise ValueError(f"Not a valid UnityFS bundle: {bundle_path}")

    _version = reader.read_u_int()
    _player_ver = reader.read_string_to_null()
    _engine_ver = reader.read_string_to_null()
    _size = reader.read_long()
    _compressed_size = reader.read_u_int()
    _uncompressed_size = reader.read_u_int()
    dataflags = reader.read_u_int()

    if not (dataflags & 0x200):
        raise ValueError(f"Bundle is not encrypted: {bundle_path}")

    _unknown = reader.read_u_int()
    _data, _key = read_vector(reader)
    data_sig, key_sig = read_vector(reader)
    return key_sig, data_sig


def resolve_heartopia_key(
    metadata_path: Optional[Path] = None,
    bundle_path: Optional[Path] = None,
    bundle_dir: Optional[Path] = None,
) -> bytes:
    """Extract decryption key dynamically by scanning bundle header and metadata.

    Args:
        metadata_path: Path to global-metadata.dat. Defaults to HEARTOPIA_METADATA_PATH.
        bundle_path: Optional specific encrypted .ab file to inspect signatures from.
        bundle_dir: Optional bundle folder to search for sample encrypted bundle.

    Returns:
        The extracted 16-byte decryption key.

    Raises:
        ValueError: If required paths are missing or key extraction fails.
        FileNotFoundError: If configured metadata file does not exist.
    """
    meta_path = metadata_path or DEFAULT_METADATA_PATH
    if meta_path is None:
        raise ValueError(
            "No metadata path configured. Set HEARTOPIA_METADATA_PATH in .env or pass "
            "--metadata-path."
        )
    if not meta_path.exists():
        raise FileNotFoundError(f"Metadata file not found at: {meta_path}")

    # Determine bundle file to extract signatures from
    target_bundle = bundle_path
    if target_bundle is None:
        search_dir = bundle_dir or DEFAULT_BUNDLE_DIR
        if search_dir is not None and search_dir.exists():
            for candidate in search_dir.glob("*.ab"):
                try:
                    extract_bundle_signatures(candidate)
                    target_bundle = candidate
                    break
                except Exception:
                    continue

    if target_bundle is None or not target_bundle.exists():
        raise ValueError(
            "Could not locate an encrypted AssetBundle to extract signatures. "
            "Set HEARTOPIA_BUNDLE_DIR in .env or pass a bundle path."
        )

    key_sig, data_sig = extract_bundle_signatures(target_bundle)
    key: Optional[bytes] = brute_force_key(meta_path, key_sig, data_sig)
    if not key:
        raise ValueError(f"Failed to find valid decryption key from {meta_path}")
    return key


if __name__ == "__main__":
    found_key = resolve_heartopia_key()
    print(f"Decryption key: {found_key}")
