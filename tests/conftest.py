"""Put code/ on sys.path so tests import modules the same way the entry point
(`python code/main.py`) does: bare top-level packages (domain, agent, images,
dataio, evaluation) with code/ as the import root."""

import pathlib
import sys

_CODE_DIR = pathlib.Path(__file__).resolve().parents[1] / "code"
if str(_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_CODE_DIR))
