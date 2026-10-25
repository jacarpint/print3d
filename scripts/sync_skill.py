#!/usr/bin/env python3
"""Copy the packaged skill into the plugin's `skills/print3d` folder.

The plugin needs a real directory, not a symlink: a Windows checkout without
Developer Mode gets the symlink as a 20-byte text file. `src/print3d/skill` is
the source of truth; this copies it and `tests/test_plugin.py` fails when the
two drift apart.
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "print3d" / "skill"
TARGET = ROOT / "skills" / "print3d"


def main() -> int:
    if TARGET.exists() or TARGET.is_symlink():
        if TARGET.is_symlink():
            TARGET.unlink()
        else:
            shutil.rmtree(TARGET)
    shutil.copytree(SOURCE, TARGET)
    print(f"copied {SOURCE} -> {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
