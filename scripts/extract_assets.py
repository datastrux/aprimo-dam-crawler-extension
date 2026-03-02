#!/usr/bin/env python3
"""Extract assets array from wrapped JSON"""
import json
from pathlib import Path

input_file = Path(__file__).parent.parent / "assets" / "audit" / "dam_assets.json"
output_file = Path(__file__).parent.parent / "assets" / "audit" / "dam_assets_array.json"

print(f"Reading: {input_file}")
with open(input_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Extract assets array
assets = data.get('assets', [])
print(f"Found {len(assets)} assets")

print(f"Writing: {output_file}")
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(assets, f, indent=2, ensure_ascii=False)

print("✓ Done! Now renaming files...")

# Backup original
backup_file = input_file.with_suffix('.json.bak')
input_file.rename(backup_file)
print(f"  ✓ Backed up original to: {backup_file.name}")

# Rename extracted to standard name
output_file.rename(input_file)
print(f"  ✓ Renamed extracted file to: {input_file.name}")

print(f"\n✓ Complete! dam_assets.json now contains {len(assets):,} assets as array")
