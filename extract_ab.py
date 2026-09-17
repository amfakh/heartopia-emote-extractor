"""Extract assets from Heartopia Unity AssetBundles with reproducible settings."""

import argparse
import os
from pathlib import Path
from typing import Any, Optional, Union

import lz4.block
import UnityPy
from dotenv import load_dotenv
from UnityPy.files.BundleFile import ArchiveFlags, ArchiveFlagsOld, BundleFile

from find_key import DEFAULT_METADATA_PATH, resolve_heartopia_key

# Load configuration from .env if present
load_dotenv()

DEFAULT_BUNDLE_DIR: Optional[Path] = (
    Path(os.environ["HEARTOPIA_BUNDLE_DIR"]) if os.getenv("HEARTOPIA_BUNDLE_DIR") else None
)
DEFAULT_OUTPUT_DIR: Path = Path(os.getenv("HEARTOPIA_OUTPUT_DIR", "extracted_assets"))
ENV_DECRYPT_KEY: Optional[str] = os.getenv("HEARTOPIA_DECRYPT_KEY")

ENCRYPTION_BLOCK_LIMIT: int = 0x6F


def patch_heartopia_decryptor() -> None:
    """Monkey-patch BundleFile.decompress_data for Heartopia LZ4 block cutoff.

    Heartopia customizes the UnityCN block decryptor to clamp decryption to the
    first 0x6F (111) bytes of each compressed LZ4 block. Tokens beyond this boundary
    retain raw literal bytes and match offsets.
    """
    orig_decompress = BundleFile.decompress_data

    def patched_decompress(
        self: BundleFile,
        compressed_data: bytes,
        uncompressed_size: int,
        flags: Union[int, ArchiveFlags, ArchiveFlagsOld],
        index: int = 0,
    ) -> bytes:
        """Decompress block with Heartopia custom 0x6F byte encryption cutoff.

        Args:
            self: The BundleFile instance.
            compressed_data: Raw compressed block bytes.
            uncompressed_size: Expected uncompressed size.
            flags: Compression and encryption flags.
            index: Block sequence index used in UnityCN block decryptor.

        Returns:
            Decompressed bytes.
        """
        comp_flag = int(flags) & 0x3F
        if self.decryptor is not None and int(flags) & 0x100 and comp_flag != 0:
            data = bytearray(compressed_data)
            off = 0
            idx = index
            while off < ENCRYPTION_BLOCK_LIMIT:
                cur_byte, off, idx_seq = self.decryptor.decrypt_byte(data, off, idx)
                byte_high = cur_byte >> 4
                byte_low = cur_byte & 0xF

                if byte_high == 0xF:
                    b = 0xFF
                    while b == 0xFF:
                        b, off, idx_seq = self.decryptor.decrypt_byte(data, off, idx_seq)
                        byte_high += b

                off += byte_high
                if off < ENCRYPTION_BLOCK_LIMIT:
                    _, off, idx_seq = self.decryptor.decrypt_byte(data, off, idx_seq)
                    _, off, idx_seq = self.decryptor.decrypt_byte(data, off, idx_seq)
                    if byte_low == 0xF:
                        b = 0xFF
                        while b == 0xFF:
                            b, off, idx_seq = self.decryptor.decrypt_byte(data, off, idx_seq)
                else:
                    off += 2
                idx += 1

            return lz4.block.decompress(bytes(data), uncompressed_size)

        return orig_decompress(self, compressed_data, uncompressed_size, flags, index)

    BundleFile.decompress_data = patched_decompress


def build_container_map(env: UnityPy.Environment) -> dict[int, str]:
    """Map object PathID to internal asset filepath from AssetBundle container metadata.

    Args:
        env: Loaded UnityPy Environment.

    Returns:
        Mapping from PathID (int) to asset stem name (str).
    """
    path_map: dict[int, str] = {}
    for obj in env.objects:
        if obj.type.name == "AssetBundle":
            tree: dict[str, Any] = obj.read_typetree()
            for path, info in tree.get("m_Container", []):
                pid = info.get("asset", {}).get("m_PathID")
                if pid is not None:
                    path_map[int(pid)] = Path(str(path)).stem
    return path_map


def extract_bundle(
    bundle_path: Path,
    output_dir: Path,
    list_only: bool = False,
) -> int:
    """Extract sprites, textures, and assets from a single Heartopia AssetBundle.

    Args:
        bundle_path: Path to the target .ab file.
        output_dir: Destination folder for extracted files.
        list_only: If True, only log assets without saving to disk.

    Returns:
        Count of processed assets.
    """
    if not bundle_path.exists():
        raise FileNotFoundError(f"Bundle file not found: {bundle_path}")

    env = UnityPy.load(str(bundle_path))
    container_map = build_container_map(env)

    bundle_stem = bundle_path.stem
    target_dir = output_dir / bundle_stem
    if not list_only:
        target_dir.mkdir(parents=True, exist_ok=True)

    extracted_count = 0
    for obj in env.objects:
        tname = obj.type.name
        if tname not in ["Sprite", "Texture2D", "TextAsset"]:
            continue

        name = container_map.get(obj.path_id)
        try:
            data = obj.read()
            if not name:
                name = getattr(data, "name", "") or str(obj.path_id)

            if tname == "Sprite":
                if hasattr(data, "image"):
                    if list_only:
                        print(f"  [Sprite] {name} ({data.image.size})")
                    else:
                        dest = target_dir / f"{name}.png"
                        data.image.save(dest)
                    extracted_count += 1
            elif tname == "Texture2D":
                if hasattr(data, "image"):
                    if list_only:
                        print(f"  [Texture2D] {name} ({data.image.size})")
                    else:
                        dest = target_dir / f"{name}_atlas.png"
                        data.image.save(dest)
                    extracted_count += 1
            elif tname == "TextAsset":
                if hasattr(data, "script"):
                    if list_only:
                        print(f"  [TextAsset] {name}")
                    else:
                        dest = target_dir / f"{name}.txt"
                        dest.write_bytes(bytes(data.script))
                    extracted_count += 1
        except Exception as err:
            print(f"  [Warning] Failed reading {tname} (ID: {obj.path_id}): {err}")

    if not list_only:
        print(f"Extracted {extracted_count} assets from '{bundle_path.name}' -> {target_dir}")
    return extracted_count


def locate_bundles(pattern: str, bundle_dir: Path) -> list[Path]:
    """Find AssetBundle files matching a given filename or glob pattern.

    Args:
        pattern: Specific filename, full path, or glob pattern (e.g. '*emoji_41*.ab').
        bundle_dir: Base directory containing AssetBundles.

    Returns:
        List of matching Path objects.
    """
    direct_path = Path(pattern)
    if direct_path.is_absolute() and direct_path.exists():
        return [direct_path]

    relative_path = bundle_dir / pattern
    if relative_path.exists():
        return [relative_path]

    p = pattern.strip()
    if not p.endswith(".ab"):
        p = f"{p}.ab" if "*" in p else f"*{p}*.ab"
    elif not p.startswith("*") and not (bundle_dir / p).exists():
        p = f"*{p}"

    return sorted(bundle_dir.glob(p))


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for AssetBundle extractor.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Heartopia AssetBundle extractor with reproducible decryption."
    )
    parser.add_argument(
        "target",
        nargs="?",
        default="*emoji_41*.ab",
        help="Target bundle filename, glob pattern, or full path (default: '*emoji_41*.ab').",
    )
    parser.add_argument(
        "--bundle-dir",
        type=Path,
        default=DEFAULT_BUNDLE_DIR,
        help="Directory containing original game AssetBundles.",
    )
    parser.add_argument(
        "--metadata-path",
        type=Path,
        default=DEFAULT_METADATA_PATH,
        help="Path to global-metadata.dat for key brute-forcing.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory for extracted assets.",
    )
    parser.add_argument(
        "--key",
        type=str,
        default=None,
        help="Hex or ascii string AES decryption key (overrides .env / auto-detection).",
    )
    parser.add_argument(
        "--auto-key",
        action="store_true",
        help="Force extracting decryption key from global-metadata.dat.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List assets without saving them to disk.",
    )
    return parser.parse_args()


def get_decryption_key(args: argparse.Namespace) -> bytes:
    """Resolve AES decryption key from CLI argument, environment variable, or metadata.

    Args:
        args: Parsed command-line arguments.

    Returns:
        16-byte decryption key.
    """
    if args.key:
        return args.key.encode("utf-8")

    if not args.auto_key and ENV_DECRYPT_KEY:
        return ENV_DECRYPT_KEY.encode("utf-8")

    print(f"Resolving key from metadata: {args.metadata_path}...")
    return resolve_heartopia_key(args.metadata_path)


def main() -> None:
    """Main CLI entrypoint."""
    args = parse_args()

    if args.bundle_dir is None:
        print(
            "No AssetBundle directory configured. Set HEARTOPIA_BUNDLE_DIR in .env or pass "
            "--bundle-dir."
        )
        return

    key = get_decryption_key(args)
    print(f"Using decryption key: {key}")

    patch_heartopia_decryptor()
    UnityPy.set_assetbundle_decrypt_key(key)

    matching_bundles = locate_bundles(args.target, args.bundle_dir)
    if not matching_bundles:
        print(f"No AssetBundles found matching '{args.target}' in {args.bundle_dir}")
        return

    print(f"Found {len(matching_bundles)} bundle(s) matching '{args.target}':")
    for b in matching_bundles:
        print(f" - {b.name} ({b.stat().st_size:,} bytes)")

    total_assets = 0
    for b in matching_bundles:
        total_assets += extract_bundle(b, args.output_dir, list_only=args.list)

    if not args.list:
        print(f"\nDone! Total {total_assets} asset(s) extracted.")


if __name__ == "__main__":
    main()
