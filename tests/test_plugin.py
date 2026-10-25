import json
import tomllib
from pathlib import Path

from print3d.paths import skill_dir

ROOT = Path(__file__).resolve().parents[1]


def _files(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_hermes_plugin_matches_the_package():
    manifest = json.loads((ROOT / "plugin.json").read_text())
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert manifest["version"] == project["version"]
    server = json.loads((ROOT / "mcp.json").read_text())["mcpServers"]["print3d"]
    assert server["args"][-2:] == ["print3d", "mcp"]
    hermes = manifest["extensions"]["com.nousresearch.hermes"]
    assert hermes["servers"]["print3d"]["trust"] == "untrusted"


def test_plugin_skill_is_a_real_copy_of_the_package():
    """A Windows checkout without Developer Mode cannot make the old symlink."""
    plugin_skill = ROOT / "skills" / "print3d"
    assert plugin_skill.is_dir() and not plugin_skill.is_symlink()
    assert _files(plugin_skill) == _files(skill_dir())
