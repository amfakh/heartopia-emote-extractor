# Heartopia Bird Emotes Extractor (心动小镇海鸥表情包)

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Extractor for the bird / seagull reaction sticker set from **Heartopia (心动小镇)**, pulled directly from the game's dynamic atlas.

This repository ships the extraction code only. Run it against your own local game install to generate the PNGs; no pre-extracted assets are included here.

---

## How to Extract from Game Files

If you have the game installed, you can extract the entire bundle (189 sprites + full 1024x2048 texture atlases) directly from your local client.

### Prerequisites

- Python 3.9+ with [`uv`](https://docs.astral.sh/uv/) installed.
- Heartopia client installed (PC / Steam / CrossOver / Wine).

### Quick Start

1. **Clone repository & sync dependencies:**
   ```bash
   git clone https://github.com/<your-username>/heartopia-emote-extractor.git
   cd heartopia-emote-extractor
   uv sync
   ```

2. **Extract emote bundle:**
   ```bash
   uv run python extract_ab.py
   ```
   Outputs all 189 sprite PNGs and texture sheets into `extracted_assets/159ab5c850dc_emoji_41/`.

3. **Preview assets without writing:**
   ```bash
   uv run python extract_ab.py --list
   ```

---

## Configuration (`.env`)

This tool has no built-in default path to your game install; point it at your local files via `.env` (or the equivalent `--bundle-dir`/`--metadata-path`/`--key` CLI flags):

```ini
# Required unless you pass --key: the AES decryption key.
# If omitted, the extractor brute-forces it from global-metadata.dat instead.
HEARTOPIA_DECRYPT_KEY=your_16_byte_key_here

# Required unless you pass --bundle-dir: path to the Heartopia StreamingAssets/AssetBundle folder.
HEARTOPIA_BUNDLE_DIR=/path/to/Heartopia/xdt_Data/StreamingAssets/AssetBundle

# Required (unless HEARTOPIA_DECRYPT_KEY is set) to brute-force the key: path to global-metadata.dat.
HEARTOPIA_METADATA_PATH=/path/to/Heartopia/xdt_Data/il2cpp_data/Metadata/global-metadata.dat

# (Optional) Output directory for extracted PNGs.
HEARTOPIA_OUTPUT_DIR=extracted_assets
```

---

## Reproducing After Game Updates

When the game updates with new content:

```bash
# Extract updated emote bundles
uv run python extract_ab.py "*emoji*.ab"

# If the AES key rotates, brute-force the new key from metadata automatically
uv run python extract_ab.py --auto-key
```

---

## Technical Background

Standard tools like AssetStudio and UnityPy fail on Heartopia's AssetBundles with `LZ4BlockError 115`. This tool patches UnityPy's decompression routine to handle Heartopia's customized archive scheme; see the `patch_heartopia_decryptor` docstring in `extract_ab.py` for the implementation details.

---

## Disclaimer

All character art, sprites, and trademarks belong to **XD Inc. (心动网络)**. This repository provides code for personal interoperability, research, and fan archival under fair use.
