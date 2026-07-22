import sys
from pathlib import Path

# Ensure project root is in path when running from tests/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data import massive_config

try:
    configs = massive_config.generate_all_configs()
    print(f"Total configs: {len(configs)}")
    print(f"Types: {set(c['type'] for c in configs)}")
except Exception as e:
    print(f"Error: {e}")
