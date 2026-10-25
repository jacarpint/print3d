import json
import subprocess
import sys
from pathlib import Path

import pytest

from print3d import setup
from print3d.paths import skill_dir


def _apply(home, agents, which=lambda _: None, run=None):
    for change in setup.plan(agents, home=home, which=which, run=run or subprocess.run):
        change.apply()


def test_only_agents_present_are_planned(tmp_path):
    (tmp_path / ".cursor").mkdir()
    which = {"codex": "/bin/codex"}.get
    assert setup.detect(tmp_path, which) == ["codex", "cursor"]


def test_codex_section_is_added_once_and_keeps_the_rest(tmp_path):
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir()
    config.write_text('model = "o5"\n\n[mcp_servers.other]\ncommand = "x"\n')
    _apply(tmp_path, ["codex"])
    _apply(tmp_path, ["codex"])
    text = config.read_text()
    assert text.count("[mcp_servers.print3d]") == 1
    assert 'model = "o5"' in text and "[mcp_servers.other]" in text
    assert json.dumps(sys.executable) in text
    assert list(config.parent.glob("config.toml.print3d-backup-*"))


def test_json_configs_keep_other_servers(tmp_path):
    settings = tmp_path / ".gemini" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps({"theme": "dark", "mcpServers": {"other": {"command": "x"}}}))
    _apply(tmp_path, ["gemini"])
    config = json.loads(settings.read_text())
    assert config["theme"] == "dark"
    assert set(config["mcpServers"]) == {"other", "print3d"}
    assert config["mcpServers"]["print3d"]["args"] == ["-m", "print3d", "mcp"]


def test_broken_json_is_left_alone(tmp_path):
    mcp = tmp_path / ".cursor" / "mcp.json"
    mcp.parent.mkdir()
    mcp.write_text("{not json")
    with pytest.raises(setup.SetupError):
        _apply(tmp_path, ["cursor"])
    assert mcp.read_text() == "{not json"


def test_claude_gets_the_skill_linked_and_the_server_added(tmp_path):
    old = tmp_path / ".claude" / "skills" / "print3d"
    old.mkdir(parents=True)
    calls = []

    def run(cmd, **_):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    _apply(tmp_path, ["claude"], which={"claude": "/bin/claude"}.get, run=run)
    assert old.resolve() == skill_dir()
    assert list(old.parent.glob("print3d.print3d-backup-*"))
    assert calls[-1][:6] == ["/bin/claude", "mcp", "add", "--scope", "user", "print3d"]
    assert calls[-1][-3:] == ["-m", "print3d", "mcp"]


def test_hermes_gets_the_skill_linked_and_the_server_added_once(tmp_path):
    hermes = tmp_path / ".hermes"
    (hermes / "skills" / "print3d").mkdir(parents=True)
    (hermes / "skills" / "print3d" / "old.md").write_text("old\n", encoding="utf-8")
    config = hermes / "config.yaml"
    config.write_text(
        "model: x\n"
        "mcp_servers:\n"
        "  other:\n"
        "    command: npx\n"
        "\n"
        "  print3d:\n"
        "    command: /old/python\n"
        "    args: [-m, print3d, mcp]\n"
        "skills:\n"
        "  disabled: []\n"
    )
    _apply(tmp_path, ["hermes"])
    _apply(tmp_path, ["hermes"])
    text = config.read_text()
    assert (hermes / "skills" / "print3d").resolve() == skill_dir()
    assert text.count("  print3d:") == 1 and "/old/python" not in text
    assert json.dumps(sys.executable) in text
    assert "  other:\n    command: npx\n" in text
    assert text.startswith("model: x\n") and text.endswith("skills:\n  disabled: []\n")


def test_hermes_config_without_servers_gets_the_section(tmp_path):
    config = tmp_path / ".hermes" / "config.yaml"
    config.parent.mkdir()
    config.write_text("model: x\nmcp_servers: {}\n")
    _apply(tmp_path, ["hermes"])
    assert config.read_text().startswith("model: x\nmcp_servers:\n  print3d:\n")


def test_opencode_gets_the_skill_and_a_jsonc_server(tmp_path):
    config = tmp_path / ".config" / "opencode" / "opencode.jsonc"
    config.parent.mkdir(parents=True)
    config.write_text(
        '{\n'
        '  // keep this comment\n'
        '  "theme": "dark",\n'
        '  "mcp": {\n'
        '    "other": { "type": "local", "command": ["x"] }\n'
        '  }\n'
        '}\n',
        encoding="utf-8",
    )
    _apply(tmp_path, ["opencode"])
    _apply(tmp_path, ["opencode"])
    text = config.read_text()
    assert "// keep this comment" in text
    assert text.count('"print3d":') == 1
    parsed = json.loads(setup._strip_jsonc(text))
    assert parsed["theme"] == "dark"
    assert parsed["mcp"]["other"]["command"] == ["x"]
    assert parsed["mcp"]["print3d"]["command"][-3:] == ["-m", "print3d", "mcp"]
    assert (tmp_path / ".config" / "opencode" / "skills" / "print3d").resolve() == skill_dir()
    assert list(config.parent.glob("opencode.jsonc.print3d-backup-*"))


def test_opencode_config_without_mcp_gets_the_section(tmp_path):
    config = tmp_path / ".config" / "opencode" / "opencode.jsonc"
    config.parent.mkdir(parents=True)
    config.write_text('{\n  "theme": "dark"\n}\n', encoding="utf-8")
    _apply(tmp_path, ["opencode"])
    parsed = json.loads(setup._strip_jsonc(config.read_text()))
    assert parsed["theme"] == "dark"
    assert parsed["mcp"]["print3d"]["enabled"] is True


def test_opencode_is_detected_from_its_config_folder(tmp_path):
    (tmp_path / ".config" / "opencode").mkdir(parents=True)
    assert "opencode" in setup.detect(tmp_path, lambda _: None)


def test_skill_is_copied_when_links_are_not_available(tmp_path, monkeypatch):
    def no_symlink(*_args, **_kwargs):
        raise OSError("no symlink privilege")

    def no_junction(*args, **_kwargs):
        return subprocess.CompletedProcess(args[0] if args else [], 1, "", "denied")

    monkeypatch.setattr(Path, "symlink_to", no_symlink)
    monkeypatch.setattr(setup.subprocess, "run", no_junction)
    link = tmp_path / "skills" / "print3d"
    setup._link(link, skill_dir())
    assert link.is_dir() and not link.is_symlink()
    assert (link / "SKILL.md").read_text(encoding="utf-8") == (
        skill_dir() / "SKILL.md"
    ).read_text(encoding="utf-8")
