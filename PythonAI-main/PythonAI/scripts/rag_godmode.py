"""
Thin wrapper - delegates to src/rag/rag_engine.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    from src.rag.rag_engine import main

    main()
