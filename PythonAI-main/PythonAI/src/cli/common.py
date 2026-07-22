from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from src.utils.models import ROOT, project_python

VERSION = "2.1.0"


def run(command: list[str]) -> int:
    print(" ".join(command))
    return subprocess.call(command, cwd=ROOT)
