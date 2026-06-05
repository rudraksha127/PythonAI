"""
Thin wrapper — delegates to tests/test_swarm.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    from tests.test_swarm import main  # type: ignore[import-unverified]
    main()
