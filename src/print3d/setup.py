"""Register print3d with the coding agents on this machine.

Each agent gets the MCP server, launched with the Python print3d is installed
in. OpenCode, Claude Code and Hermes also get the skill, linked (or, where the
OS refuses a link, copied) so it follows the installed package. Nothing is
changed until the plan has been shown; every file edited is backed up beside
itself first.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from print3d.paths import skill_dir

AGENTS = ("opencode", "claude", "codex", "cursor", "gemini", "hermes")
NAME = "print3d"


class SetupError(RuntimeError):
    """Raised when an agent's config cannot be changed safely."""


@dataclass(frozen=True)
class Change:
    agent: str
    target: str
    action: str
    apply: Callable[[], None]

    def describe(self) -> str:
        return f"{self.agent:7} {self.action}  ({self.target})"


def server_command() -> list[str]:
    return [sys.executable, "-m", "print3d", "mcp"]


def _backup_path(path: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    candidate = path.with_name(f"{path.name}.print3d-backup-{stamp}")
    counter = 1
    while candidate.exists() or candidate.is_symlink():
        candidate = path.with_name(f"{path.name}.print3d-backup-{stamp}-{counter}")
        counter += 1
    return candidate


def _backup(path: Path) -> None:
    if path.exists() or path.is_symlink():
        path.rename(_backup_path(path))


def _is_junction(path: Path) -> bool:
    checker = getattr(path, "is_junction", None)
    return bool(checker and checker())


def _remove_path(path: Path) -> None:
    """Remove a link or junction; rename anything real out of the way."""
    if path.is_symlink():
        path.unlink()
    elif _is_junction(path):
        path.rmdir()
    else:
        _backup(path)


def _link(link: Path, target: Path) -> None:
    """A link when the OS allows it, a junction on Windows, a copy as a last resort."""
    _remove_path(link)
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError:
        pass
    if os.name == "nt":
        created = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target.resolve())],
            capture_output=True,
            text=True,
            check=False,
        )
        if created.returncode == 0:
            return
    shutil.copytree(target, link)


def _write_with_backup(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, _backup_path(path))
    path.write_text(text, encoding="utf-8")


def _merge_mcp_json(path: Path) -> None:
    """Add the server under `mcpServers`, the shape Cursor and Gemini CLI share."""
    try:
        config = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except json.JSONDecodeError as exc:
        raise SetupError(f"{path} is not valid JSON ({exc}); fix it and run setup again.") from exc
    command, *args = server_command()
    config.setdefault("mcpServers", {})[NAME] = {"command": command, "args": args}
    _write_with_backup(path, json.dumps(config, indent=2) + "\n")


CODEX_SECTION = re.compile(rf"^\[mcp_servers\.{NAME}\]\n(?:(?!\[).*\n?)*", re.MULTILINE)


def _merge_codex_toml(path: Path) -> None:
    command, *args = server_command()
    block = (
        f"[mcp_servers.{NAME}]\n"
        f"command = {json.dumps(command)}\n"
        f"args = {json.dumps(args)}\n"
    )
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if CODEX_SECTION.search(text):
        # A function replacement keeps backslashes in Windows paths literal.
        text = CODEX_SECTION.sub(lambda _match: block + "\n", text, count=1)
    else:
        text = (text.rstrip("\n") + "\n\n" if text.strip() else "") + block
    _write_with_backup(path, text)


HERMES_SERVERS = re.compile(r"^mcp_servers:[ \t]*(\{\})?[ \t]*\n?", re.MULTILINE)
HERMES_ENTRY = re.compile(rf"^  {NAME}:.*\n(?:(?:    .*)?\n)*", re.MULTILINE)


def _merge_hermes_yaml(path: Path) -> None:
    """Add the server under the top-level `mcp_servers:` of Hermes's config.yaml."""
    command, *args = server_command()
    entry = (
        f"  {NAME}:\n"
        f"    command: {json.dumps(command)}\n"
        f"    args: {json.dumps(args)}\n"
        f"    enabled: true\n"
    )
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    servers = HERMES_SERVERS.search(text)
    if servers is None:
        if re.search(r"^mcp_servers:", text, re.MULTILINE):
            raise SetupError(f"{path} has mcp_servers in a form setup cannot edit; add print3d by hand.")
        text = (text.rstrip("\n") + "\n" if text.strip() else "") + "mcp_servers:\n" + entry
    else:
        head, tail = text[:servers.start()], text[servers.end():]
        block_end = re.search(r"^\S", tail, re.MULTILINE)
        block, rest = (tail[:block_end.start()], tail[block_end.start():]) if block_end else (tail, "")
        text = head + "mcp_servers:\n" + entry + HERMES_ENTRY.sub("", block) + rest
    _write_with_backup(path, text)


def _skip_trivia(text: str, index: int, end: int | None = None) -> int:
    """Skip whitespace and JSONC comments, but not commas."""
    end = len(text) if end is None else end
    while index < end:
        char = text[index]
        if char in " \t\r\n":
            index += 1
        elif text.startswith("//", index):
            newline = text.find("\n", index + 2, end)
            index = end if newline < 0 else newline + 1
        elif text.startswith("/*", index):
            close = text.find("*/", index + 2, end)
            index = end if close < 0 else close + 2
        else:
            break
    return index


def _string_end(text: str, index: int) -> int:
    index += 1
    while index < len(text):
        if text[index] == "\\":
            index += 2
        elif text[index] == '"':
            return index + 1
        else:
            index += 1
    raise SetupError("Unterminated string in OpenCode config; fix it and run setup again.")


def _matching_end(text: str, index: int) -> int:
    pairs = {"{": "}", "[": "]"}
    stack = [pairs[text[index]]]
    index += 1
    while index < len(text) and stack:
        if text[index] == '"':
            index = _string_end(text, index)
            continue
        if text.startswith("//", index):
            newline = text.find("\n", index + 2)
            index = len(text) if newline < 0 else newline + 1
            continue
        if text.startswith("/*", index):
            close = text.find("*/", index + 2)
            index = len(text) if close < 0 else close + 2
            continue
        if text[index] in pairs:
            stack.append(pairs[text[index]])
        elif text[index] == stack[-1]:
            stack.pop()
        index += 1
    if stack:
        raise SetupError("Unbalanced brackets in OpenCode config; fix it and run setup again.")
    return index


def _value_end(text: str, index: int) -> int:
    index = _skip_trivia(text, index)
    if index >= len(text):
        return index
    if text[index] in "{[":
        return _matching_end(text, index)
    if text[index] == '"':
        return _string_end(text, index)
    while index < len(text):
        if text[index] in ",}]" or text.startswith("//", index) or text.startswith("/*", index):
            break
        index += 1
    return index


def _find_field(text: str, open_pos: int, close_pos: int, key: str) -> tuple[int, int, int] | None:
    """(value start, value end, key start) for a field of one object."""
    index = open_pos + 1
    while index < close_pos:
        index = _skip_trivia(text, index, close_pos)
        if index >= close_pos:
            break
        if text[index] == ",":
            index += 1
            continue
        if text[index] != '"':
            raise SetupError("OpenCode config is not the JSON object setup can edit.")
        key_start = index
        key_end = _string_end(text, index)
        try:
            name = json.loads(text[key_start:key_end])
        except json.JSONDecodeError as exc:
            raise SetupError(f"OpenCode config has a broken key: {exc}") from exc
        index = _skip_trivia(text, key_end, close_pos)
        if index >= close_pos or text[index] != ":":
            raise SetupError("OpenCode config has a key without a value; fix it and run setup again.")
        value_start = _skip_trivia(text, index + 1, close_pos)
        value_end = _value_end(text, value_start)
        if name == key:
            return value_start, value_end, key_start
        index = value_end
    return None


def _line_indent(text: str, position: int) -> str:
    start = text.rfind("\n", 0, position) + 1
    prefix = text[start:position]
    return prefix if prefix.strip() == "" else ""


def _insert_field(text: str, open_pos: int, close_pos: int, key: str, value: Any) -> str:
    """Insert a field first in an object without touching comments or layout."""
    close_indent = _line_indent(text, close_pos)
    child_indent = close_indent + "  "
    value_json = json.dumps(value, indent=2).replace("\n", "\n" + child_indent)
    entry = f'"{key}": {value_json}'
    inner = text[open_pos + 1:close_pos]
    first = _skip_trivia(text, open_pos + 1, close_pos)
    if not inner.strip():
        new_inner = f"\n{child_indent}{entry}\n{close_indent}"
    elif first >= close_pos:
        # Only comments inside: still an empty object, and a comma would break it.
        new_inner = f"\n{child_indent}{entry}{inner}"
    else:
        new_inner = f"\n{child_indent}{entry},{inner}"
    return text[: open_pos + 1] + new_inner + text[close_pos:]


def _strip_jsonc(text: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(text):
        if text[index] == '"':
            end = _string_end(text, index)
            out.append(text[index:end])
            index = end
        elif text.startswith("//", index):
            newline = text.find("\n", index + 2)
            index = len(text) if newline < 0 else newline
        elif text.startswith("/*", index):
            close = text.find("*/", index + 2)
            index = len(text) if close < 0 else close + 2
        else:
            out.append(text[index])
            index += 1
    no_comments = "".join(out)
    return re.sub(r",(\s*[}\]])", r"\1", no_comments)


def _merge_opencode_jsonc(path: Path) -> None:
    """Add mcp.print3d to OpenCode's JSONC config, keeping its comments."""
    text = path.read_text(encoding="utf-8") if path.is_file() else "{}\n"
    entry = {"type": "local", "enabled": True, "command": server_command()}
    root_open = _skip_trivia(text, 0)
    if root_open >= len(text) or text[root_open] != "{":
        raise SetupError(f"{path} is not a JSON object; fix it and run setup again.")
    root_close = _matching_end(text, root_open) - 1
    mcp = _find_field(text, root_open, root_close, "mcp")
    if mcp is None:
        text = _insert_field(text, root_open, root_close, "mcp", {NAME: entry})
    else:
        mcp_open = _skip_trivia(text, mcp[0], mcp[1])
        if text[mcp_open] != "{":
            raise SetupError(f"{path}: mcp is not an object; fix it and run setup again.")
        mcp_close = _matching_end(text, mcp_open) - 1
        field = _find_field(text, mcp_open, mcp_close, NAME)
        if field is None:
            text = _insert_field(text, mcp_open, mcp_close, NAME, entry)
        else:
            value_start, value_end, key_start = field
            key_indent = _line_indent(text, key_start)
            value_json = json.dumps(entry, indent=2).replace("\n", "\n" + key_indent)
            text = text[:value_start] + value_json + text[value_end:]
    try:
        json.loads(_strip_jsonc(text))
    except json.JSONDecodeError as exc:
        raise SetupError(f"{path} would not be valid JSON after setup ({exc}); left unchanged.") from exc
    _write_with_backup(path, text)


def _claude_mcp(claude: str, run: Callable[..., subprocess.CompletedProcess]) -> None:
    run([claude, "mcp", "remove", "--scope", "user", NAME], capture_output=True, text=True, check=False)
    added = run(
        [claude, "mcp", "add", "--scope", "user", NAME, "--", *server_command()],
        capture_output=True, text=True, check=False,
    )
    if added.returncode != 0:
        raise SetupError(f"claude mcp add failed: {(added.stderr or added.stdout).strip()}")


def _opencode_home(home: Path) -> Path:
    return home / ".config" / "opencode"


def detect(home: Path, which: Callable[[str], str | None] = shutil.which) -> list[str]:
    found: list[str] = []
    for agent in AGENTS:
        config = _opencode_home(home) if agent == "opencode" else home / f".{agent}"
        if which(agent) or config.is_dir():
            found.append(agent)
    return found


def plan(
    agents: list[str] | None = None,
    *,
    home: Path | None = None,
    which: Callable[[str], str | None] = shutil.which,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> list[Change]:
    home = home or Path.home()
    changes: list[Change] = []
    for agent in agents or detect(home, which):
        if agent == "opencode":
            config_dir = _opencode_home(home)
            link = config_dir / "skills" / NAME
            changes.append(
                Change(
                    agent,
                    str(link),
                    "install the print3d skill",
                    lambda link=link: _link(link, skill_dir()),
                )
            )
            path = config_dir / "opencode.jsonc"
            changes.append(
                Change(
                    agent,
                    str(path),
                    "add mcp.print3d",
                    lambda path=path: _merge_opencode_jsonc(path),
                )
            )
        elif agent == "claude":
            link = home / ".claude" / "skills" / NAME
            changes.append(Change(agent, str(link), f"link the skill to {skill_dir()}",
                                  lambda link=link: _link(link, skill_dir())))
            if claude := which("claude"):
                changes.append(Change(agent, "user scope", "claude mcp add print3d",
                                      lambda claude=claude: _claude_mcp(claude, run)))
        elif agent == "codex":
            path = home / ".codex" / "config.toml"
            changes.append(Change(agent, str(path), "add [mcp_servers.print3d]",
                                  lambda path=path: _merge_codex_toml(path)))
        elif agent == "hermes":
            link = home / ".hermes" / "skills" / NAME
            changes.append(Change(agent, str(link), f"link the skill to {skill_dir()}",
                                  lambda link=link: _link(link, skill_dir())))
            path = home / ".hermes" / "config.yaml"
            changes.append(Change(agent, str(path), "add mcp_servers.print3d",
                                  lambda path=path: _merge_hermes_yaml(path)))
        elif agent in ("cursor", "gemini"):
            path = home / f".{agent}" / ("mcp.json" if agent == "cursor" else "settings.json")
            changes.append(Change(agent, str(path), "add mcpServers.print3d",
                                  lambda path=path: _merge_mcp_json(path)))
        else:
            raise SetupError(f"Unknown agent {agent!r}; choose from {', '.join(AGENTS)}.")
    return changes
