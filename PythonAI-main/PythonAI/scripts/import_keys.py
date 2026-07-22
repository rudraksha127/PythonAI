"""
Import API keys from .env.example into the project's key storage (~/.pythonai/apikeys.json)
and create a proper .env file.
"""

import re
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data.apikeys import ALL_PROVIDERS, PROVIDER_LABELS, set_key, export_dotenv

# Reverse mapping: env var name → provider name
ENV_TO_PROVIDER = {v: k for k, v in ALL_PROVIDERS.items()}

# Also handle manually mapped ones
EXTRA_MAPPING = {
    "XAI_API_KEY": None,  # Not in our provider list
    "ANTHROPIC_API_KEY": None,
    "OPENAI_API_KEY": None,
}

env_file = ROOT / ".env.example"
if not env_file.exists():
    print(f"[FAIL] {env_file} not found!")
    sys.exit(1)

content = env_file.read_text(encoding="utf-8")
lines = content.split("\n")

imported = 0
skipped = 0
unknown = []

for line in lines:
    line = line.strip()
    if not line or line.startswith("#") or line.startswith("[") or "=" not in line:
        continue

    # Parse KEY="VALUE" or KEY=VALUE
    match = re.match(r'^([A-Za-z_][A-Za-z_0-9]*)\s*=\s*"([^"]*)"\s*$', line)
    if not match:
        match = re.match(r"^([A-Za-z_][A-Za-z_0-9]*)\s*=\s*([^\s]+)\s*$", line)
    if not match:
        continue

    var_name, value = match.group(1), match.group(2)
    value = value.strip().strip('"').strip("'")
    if not value or len(value) < 8:
        continue

    # Check if this env var maps to a known provider
    provider = ENV_TO_PROVIDER.get(var_name)
    if provider:
        result = set_key(provider, value)
        if result["success"]:
            print(f"  [OK] {PROVIDER_LABELS.get(provider, provider):14s} -> stored")
            imported += 1
        else:
            print(f"  [FAIL] {PROVIDER_LABELS.get(provider, provider):14s} -> {result['error']}")
            skipped += 1
    else:
        unknown.append(f"  [?] {var_name:25s} = {value[:12]}... (not in provider list)")

print(f"\n{'=' * 50}")
print(f"Imported: {imported} keys")
print(f"Skipped: {skipped}")

if unknown:
    print(f"\nUnknown/variable env vars (not in provider list):")
    for u in unknown:
        print(u)

# Create .env file from stored keys
print(f"\nCreating .env file...")
result = export_dotenv()
if result["success"]:
    print(f"  [OK] .env created at: {result['path']} ({result['count']} keys)")
else:
    print(f"  [FAIL] {result['error']}")

# Show final status
print(f"\n{'=' * 50}")
print("To verify:  python -m src.cli apikeys list")
