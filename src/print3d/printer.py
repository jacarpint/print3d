"""The printer a job is prepared for: bed, nozzles and the pinned profiles.

The numbers come from the flattened `machine.json`, `process.json` and
`filament.json` that ship with print3d, so a profile change is the only place a
bed size or a nozzle count has to be edited. The presets below are fallbacks for
a checkout whose profiles have not been generated yet.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from print3d.paths import default_profiles_dir, normalise_printer

PRESETS: dict[str, dict[str, Any]] = {
    "a1": {
        "model": "Bambu Lab A1",
        "machine": "Bambu Lab A1 0.4 nozzle",
        "process": "0.20mm Standard @BBL A1",
        "filament": "Bambu PLA Basic @BBL A1",
        "bed_mm": (256.0, 256.0, 256.0),
        "nozzles": 1,
        "nozzle_mm": 0.4,
        "layer_mm": 0.20,
        "bed_type": "Textured PEI Plate",
        "filament_type": "PLA",
    },
    "x2d": {
        "model": "Bambu Lab X2D",
        "machine": "Bambu Lab X2D 0.4 nozzle",
        "process": "0.20mm Standard @BBL X2D",
        "filament": "Bambu PLA Basic @BBL X2D 0.4 nozzle",
        "bed_mm": (256.0, 256.0, 261.0),
        "nozzles": 2,
        "nozzle_mm": 0.4,
        "layer_mm": 0.20,
        "bed_type": "Textured PEI Plate",
        "filament_type": "PLA",
    },
}

NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


@dataclass(frozen=True)
class Printer:
    key: str
    name: str
    model: str
    bed_mm: tuple[float, float, float]
    nozzles: int
    nozzle_mm: float
    layer_mm: float
    bed_type: str
    supports: bool
    filament: str
    filament_type: str
    profiles_dir: Path
    machine_profile: str
    process_profile: str
    filament_profile: str

    @property
    def volume(self) -> str:
        return " × ".join(f"{v:g}" for v in self.bed_mm) + " mm"

    @property
    def bed_label(self) -> str:
        bed = self.bed_type.strip().lower()
        if not bed:
            return "textured PEI plate"
        for known, label in (
            ("textured pei", "textured PEI plate"),
            ("smooth pei", "smooth PEI plate"),
            ("high temp", "high-temperature plate"),
            ("cool plate", "cool plate"),
            ("engineering", "engineering plate"),
        ):
            if known in bed:
                return label
        return bed if bed.endswith("plate") else bed + " plate"

    @property
    def summary(self) -> str:
        supports = "on" if self.supports else "off"
        return (
            f"{self.model}, {self.nozzle_mm:g} mm nozzle, {self.layer_mm:g} mm layers, "
            f"{self.filament}, {self.bed_label}, supports {supports}"
        )

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["bed_mm"] = list(self.bed_mm)
        data["profiles_dir"] = str(self.profiles_dir)
        data["summary"] = self.summary
        return data


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _first(value: Any) -> Any:
    return value[0] if isinstance(value, list) and value else value


def _float(value: Any, fallback: float) -> float:
    try:
        return float(_first(value))
    except (TypeError, ValueError):
        return fallback


def _int(value: Any, fallback: int) -> int:
    try:
        return int(float(_first(value)))
    except (TypeError, ValueError):
        return fallback


def _bed_from_area(area: Any) -> tuple[float, float] | None:
    """Width and depth of the polygon in `printable_area` ("0x0", "256x0", ...)."""
    if not isinstance(area, list) or len(area) < 3:
        return None
    xs: list[float] = []
    ys: list[float] = []
    for point in area:
        numbers = [float(v) for v in NUMBER_RE.findall(str(point))]
        if len(numbers) < 2:
            return None
        xs.append(numbers[0])
        ys.append(numbers[1])
    width, depth = max(xs) - min(xs), max(ys) - min(ys)
    if width <= 0 or depth <= 0:
        return None
    return width, depth


def _filament_label(filament: dict[str, Any], fallback: str) -> str:
    raw = _first(filament.get("filament_settings_id")) or fallback
    return str(raw).split(" @", 1)[0].strip() or fallback


def load_printer(printer: str | None = None, profiles_dir: str | Path | None = None) -> Printer:
    """Read the pinned profiles, falling back to the preset when they are absent."""
    key = normalise_printer(printer)
    profiles = Path(profiles_dir).expanduser() if profiles_dir else default_profiles_dir(printer)
    machine = _read_json(profiles / "machine.json")
    process = _read_json(profiles / "process.json")
    filament = _read_json(profiles / "filament.json")
    if printer is None:
        # A custom profile directory is the strongest evidence of its printer.
        model = machine.get("printer_model")
        for candidate, values in PRESETS.items():
            if model == values["model"]:
                key = candidate
                break
    preset = PRESETS[key]

    width_depth = _bed_from_area(machine.get("printable_area")) or (
        preset["bed_mm"][0],
        preset["bed_mm"][1],
    )
    bed_mm = (
        width_depth[0],
        width_depth[1],
        _float(machine.get("printable_height"), preset["bed_mm"][2]),
    )
    nozzle_diameter = machine.get("nozzle_diameter")
    nozzles = len(nozzle_diameter) if isinstance(nozzle_diameter, list) and nozzle_diameter else preset["nozzles"]
    nozzle_mm = _float(nozzle_diameter, preset["nozzle_mm"])
    supports = str(_first(process.get("enable_support", "0"))).strip().lower() not in ("0", "", "false", "none")
    layer_mm = _float(process.get("layer_height"), preset["layer_mm"])
    bed_type = str(process.get("curr_bed_type") or preset["bed_type"])
    filament_type = str(_first(filament.get("filament_type")) or preset["filament_type"])
    filament_label = _filament_label(filament, str(preset["filament"]).split(" @", 1)[0])

    return Printer(
        key=key,
        name=str(machine.get("printer_model") or preset["model"]),
        model=str(machine.get("printer_model") or preset["model"]),
        bed_mm=(round(bed_mm[0], 1), round(bed_mm[1], 1), round(bed_mm[2], 1)),
        nozzles=nozzles,
        nozzle_mm=nozzle_mm,
        layer_mm=layer_mm,
        bed_type=bed_type,
        supports=supports,
        filament=filament_label,
        filament_type=filament_type,
        profiles_dir=profiles,
        machine_profile=str(preset["machine"]),
        process_profile=str(preset["process"]),
        filament_profile=str(preset["filament"]),
    )
