"""Run Qt checks without requiring a display or opening user windows."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
