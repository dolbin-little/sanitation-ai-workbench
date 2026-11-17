
from pathlib import Path
import sys

# Dependencies are isolated inside this project, never installed system-wide.
_vendor = str(Path(__file__).resolve().parents[1] / '.vendor')
if _vendor not in sys.path:
    sys.path.insert(0, _vendor)
