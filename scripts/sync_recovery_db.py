"""Run the daily Railway-to-PC database recovery copy."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.recovery_sync import main

if __name__ == "__main__":
    raise SystemExit(main())
