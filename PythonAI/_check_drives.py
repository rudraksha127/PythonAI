#!/usr/bin/env python3
"""Check available drives and find a suitable data directory."""
import os
import subprocess
import sys
from pathlib import Path

# Check available drives on Windows
if os.name == 'nt':
    import string
    from ctypes import windll
    drives = []
    bitmask = windll.kernel32.GetLogicalDrives()
    for letter in string.ascii_uppercase:
        if bitmask & 1:
            drives.append(f"{letter}:\\")
        bitmask >>= 1
    print("Available drives:", drives)
else:
    print("Not Windows")

# Check home directory
home = Path.home()
print(f"HOME: {home}")

# Create data dir in home
data_dir = home / ".forgeai" / "training_data"
data_dir.mkdir(parents=True, exist_ok=True)
print(f"Data dir: {data_dir}")
print(f"Writable: {os.access(str(data_dir), os.W_OK)}")

# Set env var
os.environ["DATA_DIR"] = str(data_dir)
print(f"Set DATA_DIR={data_dir}")

# Now try loading the configs
sys.path.insert(0, str(Path.cwd()))
from src.data.massive_config import generate_all_configs, BASE_DATA_DIR
print(f"\nBASE_DATA_DIR is now: {BASE_DATA_DIR}")
configs = generate_all_configs()
print(f"Total configs: {len(configs)}")
for c in configs[:3]:
    print(f"  - {c['name']} ({c['type']})")
