"""Path setup of the evaluation unit tests.

The generator lives in ``data/generator/``, which is not an installed package.
Adding it to ``sys.path`` here — before the test modules are imported — lets
them write a plain ``from generator.build import generate`` at the top, with no
import-order trickery.
"""

from __future__ import annotations

import sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[3] / "data"
if str(DATA) not in sys.path:
    sys.path.insert(0, str(DATA))
