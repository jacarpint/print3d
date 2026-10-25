"""Where the pinned profiles, the skill and the jobs live."""

from __future__ import annotations

import os
import re
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
JOBS_ENV = "PRINT3D_JOBS"
PROFILES_ENV = "PRINT3D_PROFILES"
PRINTER_ENV = "PRINT3D_PRINTER"
DEFAULT_PRINTER = "a1"
PRINTERS = ("a1", "x2d")
NAME_RE = re.compile(r"[a-z0-9_-]{1,64}")


def repo_root() -> Path:
    return PACKAGE.parents[1]


def normalise_printer(printer: str | None = None) -> str:
    """The printer key from the argument, `$PRINT3D_PRINTER`, or the default (A1)."""
    key = (printer or os.environ.get(PRINTER_ENV) or DEFAULT_PRINTER).strip().lower()
    key = key.replace("_", "-").replace(" ", "-")
    aliases = {"bambu-a1": "a1", "bambu-lab-a1": "a1", "bambu-x2d": "x2d", "bambu-lab-x2d": "x2d"}
    key = aliases.get(key, key)
    if key not in PRINTERS:
        raise ValueError(
            f"Unknown printer {printer or key!r}; choose one of: {', '.join(PRINTERS)} "
            f"(or set {PRINTER_ENV})."
        )
    return key


def default_profiles_dir(printer: str | None = None) -> Path:
    """Pinned profiles for this printer, or `$PRINT3D_PROFILES` for a custom set."""
    if printer is None and (env := os.environ.get(PROFILES_ENV, "").strip()):
        return Path(env).expanduser()
    return PACKAGE / "profiles" / f"{normalise_printer(printer)}-0.4"


def coupon_script() -> Path:
    return PACKAGE / "coupons" / "fit_coupon.py"


def skill_dir() -> Path:
    return PACKAGE / "skill"


def default_jobs_dir() -> Path:
    """`$PRINT3D_JOBS`, else `jobs/` in a source checkout, else `~/print3d/jobs`."""
    if env := os.environ.get(JOBS_ENV, "").strip():
        return Path(env).expanduser()
    if (repo_root() / "pyproject.toml").is_file():
        return repo_root() / "jobs"
    return Path.home() / "print3d" / "jobs"


def safe_name(name: str, what: str = "name") -> str:
    """A job slug or view name, kept to the alphabet slugify writes so it can't leave the jobs folder."""
    if not NAME_RE.fullmatch(name):
        raise ValueError(f"{what} {name!r}: use 1 to 64 of a-z, 0-9, _ and -")
    return name


def job_path(slug: str) -> Path:
    """jobs/<slug>, refused if it would land outside the jobs folder."""
    root = default_jobs_dir().resolve()
    path = (root / safe_name(slug, "slug")).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"slug {slug!r} leaves the jobs folder")
    return path
