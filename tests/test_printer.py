from pathlib import Path

import pytest

from print3d.paths import default_profiles_dir, normalise_printer
from print3d.printer import load_printer


def test_a1_profile_comes_from_the_pinned_machine():
    target = load_printer("a1")
    assert target.key == "a1"
    assert target.model == "Bambu Lab A1"
    assert target.bed_mm == (256.0, 256.0, 256.0)
    assert target.nozzles == 1
    assert target.nozzle_mm == 0.4
    assert target.layer_mm == 0.2
    assert target.bed_type == "Textured PEI Plate"
    assert not target.supports
    assert "Bambu Lab A1" in target.summary


def test_x2d_profile_still_loads():
    target = load_printer("x2d")
    assert target.bed_mm == (256.0, 256.0, 261.0)
    assert target.nozzles == 2
    assert "Bambu Lab X2D" in target.summary


def test_the_environment_selects_the_printer(monkeypatch):
    monkeypatch.setenv("PRINT3D_PRINTER", "x2d")
    assert load_printer().key == "x2d"
    assert normalise_printer() == "x2d"
    assert default_profiles_dir().name == "x2d-0.4"


def test_a1_is_the_default(monkeypatch):
    monkeypatch.delenv("PRINT3D_PRINTER", raising=False)
    monkeypatch.delenv("PRINT3D_PROFILES", raising=False)
    assert normalise_printer() == "a1"
    assert default_profiles_dir().name == "a1-0.4"


def test_custom_profiles_dir(monkeypatch, tmp_path: Path):
    profiles = tmp_path / "custom"
    profiles.mkdir()
    (profiles / "machine.json").write_text(
        '{"printer_model": "Bambu Lab A1", "nozzle_diameter": ["0.4"], '
        '"printable_area": ["0x0", "220x0", "220x210", "0x210"], "printable_height": "210"}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("PRINT3D_PROFILES", str(profiles))
    target = load_printer()
    assert target.bed_mm == (220.0, 210.0, 210.0)
    assert target.profiles_dir == profiles


def test_unknown_printer_says_what_to_choose():
    with pytest.raises(ValueError, match="a1, x2d"):
        normalise_printer("prusa")
