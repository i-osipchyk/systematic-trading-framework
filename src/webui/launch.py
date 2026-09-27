"""Entry point for the ``trading-ui`` console script — runs the Streamlit app."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    app = Path(__file__).parent / "app.py"
    return subprocess.call(["streamlit", "run", str(app), *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
