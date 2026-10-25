import json
from pathlib import Path

from print3d.flatten import build_name_index, detect_profiles_root, flatten_by_name, flatten_profiles, normalize_for_cli


def test_inherits_and_include(tmp_path: Path):
    vendor = tmp_path / "BBL" / "machine"
    vendor.mkdir(parents=True)
    (vendor / "base.json").write_text(
        '{"type":"machine","name":"base","from":"system","a":1,"b":1}\n',
        encoding="utf-8",
    )
    (vendor / "inc.json").write_text(
        '{"name":"inc","machine_start_gcode":"G28"}\n',
        encoding="utf-8",
    )
    (vendor / "leaf.json").write_text(
        '{"type":"machine","name":"leaf","inherits":"base","include":["inc"],"b":2}\n',
        encoding="utf-8",
    )
    index = build_name_index(tmp_path)
    flat = flatten_by_name("leaf", index)
    assert flat["a"] == 1
    assert flat["b"] == 2
    assert flat["machine_start_gcode"] == "G28"
    normalize_for_cli(flat, "machine", "leaf")
    assert flat["from"] == "User"
    assert flat["inherits"] == "leaf"
    assert flat["printer_settings_id"] == "leaf"
    assert "include" not in flat


def _fake_profiles(root: Path, model: str, process: str, filament: str) -> None:
    for kind in ("machine", "process", "filament"):
        (root / "BBL" / kind).mkdir(parents=True)
    (root / "BBL" / "machine" / "a.json").write_text(
        json.dumps({"type": "machine", "name": model, "printer_model": "Bambu Lab A1"}),
        encoding="utf-8",
    )
    (root / "BBL" / "process" / "a.json").write_text(
        json.dumps({"type": "process", "name": process, "layer_height": "0.2"}),
        encoding="utf-8",
    )
    (root / "BBL" / "filament" / "a.json").write_text(
        json.dumps({"type": "filament", "name": filament, "filament_type": ["PLA"]}),
        encoding="utf-8",
    )


def test_flatten_uses_the_a1_preset_by_default(tmp_path: Path):
    root = tmp_path / "profiles"
    _fake_profiles(
        root,
        "Bambu Lab A1 0.4 nozzle",
        "0.20mm Standard @BBL A1",
        "Bambu PLA Basic @BBL A1",
    )
    result = flatten_profiles(printer="a1", profiles_root=root, output_dir=tmp_path / "out")
    assert result["printer"] == "a1"
    assert result["provenance"]["printer"] == "a1"
    machine = json.loads((tmp_path / "out" / "machine.json").read_text())
    process = json.loads((tmp_path / "out" / "process.json").read_text())
    assert machine["printer_settings_id"] == "Bambu Lab A1 0.4 nozzle"
    assert process["curr_bed_type"] == "Textured PEI Plate"


def test_windows_slicer_path_finds_the_bundled_profiles(tmp_path: Path):
    install = tmp_path / "Bambu Studio"
    root = install / "resources" / "profiles"
    (root / "BBL" / "machine").mkdir(parents=True)
    executable = install / "bambu-studio.exe"
    executable.write_bytes(b"")
    assert detect_profiles_root(str(executable)) == root
