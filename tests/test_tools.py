"""Tests for the external-tool discovery layer.

Everything here is about *finding* a command, not about running one: the tools
themselves are external, so every test uses a stub command (the Python
interpreter as a stand-in binary, or a patched ``shutil.which``) and none of them
assumes a solver or a cubing tool is installed on the machine running the suite.
"""

from __future__ import annotations

import os
import subprocess
import sys

from oplab import tools


def test_a_command_line_is_split_and_a_wsl_command_is_recognised():
    """The three things a caller has to know about a command before using it."""
    assert tools.split_command(None) == []
    assert tools.split_command("   ") == []
    assert tools.split_command("wsl -e /home/me/kissat/build/kissat") == [
        "wsl", "-e", "/home/me/kissat/build/kissat"]
    # a wrapper path is still WSL, and only the first word decides
    assert tools.is_wsl([r"C:\Windows\System32\wsl.exe", "-e", "/x"])
    assert tools.is_wsl(["wsl.exe"])
    assert not tools.is_wsl(["/usr/bin/kissat"])
    assert not tools.is_wsl(["/usr/bin/wrapper", "wsl"])
    assert not tools.is_wsl([])
    assert tools.describe(None) == "<none>"
    assert tools.describe(["kissat", "x.cnf"]) == "kissat x.cnf"


def test_a_windows_path_becomes_one_a_wsl_command_can_open():
    """A WSL command is a Linux process, so it cannot be shown ``D:\\...``."""
    if os.name == "nt":
        assert tools.wsl_path(r"D:\gen\physics\k97.cnf") == "/mnt/d/gen/physics/k97.cnf"
        assert tools.wsl_path(r"D:\a b\c d.cnf") == "/mnt/d/a b/c d.cnf"
    # a path that a Linux command can already open is left exactly as it is
    assert tools.wsl_path("/home/me/k97.cnf") == "/home/me/k97.cnf"


def test_a_relative_path_is_resolved_before_it_is_handed_over():
    """A WSL command's working directory is the ``/mnt`` spelling of this one.

    Handing ``runs/k97.cnf`` over unchanged has it look for that name under its own
    root, which is how a working cube file turns into "no such file" halfway through
    a campaign — the cube file was written by a WSL tool, so the path in the other
    direction has to work too.
    """
    resolved = tools.wsl_path("runs/k97.cnf")
    assert resolved.endswith("runs/k97.cnf")
    if os.name == "nt":
        assert resolved.startswith("/mnt/") and ":" not in resolved
    else:
        assert os.path.isabs(resolved)


def test_the_environment_variable_wins_over_the_path(monkeypatch):
    """An explicit command is used as given, and an unstartable one is skipped.

    Skipping matters: "configured but missing" would otherwise surface as a tool
    that fails once per instance, in the middle of a campaign, instead of as a
    tool that is not here.
    """
    monkeypatch.setattr(tools.shutil, "which",
                        lambda name: None if "definitely-not" in name else f"/usr/bin/{name}")
    monkeypatch.setenv("OPLAB_TEST_TOOL", "wsl -e /home/me/tool")
    assert tools.find_tool("OPLAB_TEST_TOOL", "tool", "tool/build/tool", refresh=True) == [
        "wsl", "-e", "/home/me/tool"]

    monkeypatch.setenv("OPLAB_TEST_TOOL", "definitely-not-a-program-xyz --fast")
    assert tools.find_tool("OPLAB_TEST_TOOL", "tool", "tool/build/tool", refresh=True) == [
        "/usr/bin/tool"]

    monkeypatch.delenv("OPLAB_TEST_TOOL", raising=False)
    assert tools.find_tool("OPLAB_TEST_TOOL", "tool", "tool/build/tool", refresh=True) == [
        "/usr/bin/tool"]


def test_a_built_tool_under_wsl_is_the_last_resort_and_needs_wsl(monkeypatch):
    """The documented ``$HOME`` build is found — but only through a working WSL."""
    monkeypatch.delenv("OPLAB_TEST_TOOL", raising=False)
    monkeypatch.setattr(tools.shutil, "which", lambda name: None)
    assert tools.find_tool("OPLAB_TEST_TOOL", "tool", "tool/build/tool", refresh=True) is None

    monkeypatch.setattr(tools.shutil, "which",
                        lambda name: "/usr/bin/wsl" if name in ("wsl", "wsl.exe") else None)
    seen: list[list[str]] = []

    def fake_run(command, **kwargs):
        seen.append(list(command))
        return subprocess.CompletedProcess(command, 0, "/home/me/tool/build/tool\n", "")

    monkeypatch.setattr(tools.subprocess, "run", fake_run)
    assert tools.find_tool("OPLAB_TEST_TOOL", "tool", "tool/build/tool", refresh=True) == [
        "/usr/bin/wsl", "-e", "/home/me/tool/build/tool"]
    # existence was decided inside the distribution, by an executable test there
    assert "test -x" in seen[0][-1] and "$HOME/tool/build/tool" in seen[0][-1]


def test_a_wsl_probe_that_fails_or_says_nothing_is_not_a_tool(monkeypatch):
    """A non-zero probe, or an empty answer, means the tool is simply not here."""
    monkeypatch.delenv("OPLAB_TEST_TOOL", raising=False)
    monkeypatch.setattr(tools.shutil, "which",
                        lambda name: "/usr/bin/wsl" if name in ("wsl", "wsl.exe") else None)
    for code, out in ((1, ""), (0, ""), (1, "/home/me/tool/build/tool\n")):
        monkeypatch.setattr(tools.subprocess, "run",
                            lambda command, _code=code, _out=out, **kwargs:
                            subprocess.CompletedProcess(command, _code, _out, ""))
        assert tools.find_tool("OPLAB_TEST_TOOL", "tool", "tool/build/tool", refresh=True) is None


def test_only_the_wsl_probe_is_remembered(monkeypatch):
    """The probe costs a process; a variable or ``PATH`` set later must still be seen.

    Caching the cheap lookups as well would be the wrong saving: a caller that
    exports ``OPLAB_KISSAT`` after the first probe would keep getting the
    remembered answer, which is how a campaign runs a different engine than the
    one it was told to use.
    """
    monkeypatch.delenv("OPLAB_TEST_TOOL", raising=False)
    monkeypatch.setattr(tools.shutil, "which",
                        lambda name: "/usr/bin/wsl" if name in ("wsl", "wsl.exe") else None)
    probes: list[list[str]] = []

    def fake_run(command, **kwargs):
        probes.append(list(command))
        return subprocess.CompletedProcess(command, 0, "/home/me/tool/build/tool\n", "")

    monkeypatch.setattr(tools.subprocess, "run", fake_run)
    found = tools.find_tool("OPLAB_TEST_TOOL", "tool", "tool/build/tool", refresh=True)
    assert found == ["/usr/bin/wsl", "-e", "/home/me/tool/build/tool"]
    assert len(probes) == 1
    assert tools.find_tool("OPLAB_TEST_TOOL", "tool", "tool/build/tool") == found
    assert len(probes) == 1, "the probe is paid for once"
    assert tools.find_tool("OPLAB_TEST_TOOL", "tool", "tool/build/tool", refresh=True) == found
    assert len(probes) == 2, "a refresh pays for it again"

    monkeypatch.setenv("OPLAB_TEST_TOOL", "wsl -e /somewhere/else")
    assert tools.find_tool("OPLAB_TEST_TOOL", "tool", "tool/build/tool") == [
        "wsl", "-e", "/somewhere/else"]
    assert len(probes) == 2, "a configured command is never served from the cache"


def test_the_two_named_tools_use_their_own_variables(monkeypatch, tmp_path):
    """``OPLAB_KISSAT`` and ``OPLAB_MARCH_CU`` are separate, as they must be.

    A tool exists only if its own command names something startable, so the two
    cannot be confused for one another and neither can be filled in from a
    variable meant for the other.
    """
    binary = tmp_path / "march_cu"
    binary.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.setattr(tools.shutil, "which", lambda name: None)
    # quoted, because an interpreter path with a space in it is one word
    monkeypatch.setenv(tools.KISSAT_ENV, f'"{sys.executable}" -q')
    monkeypatch.delenv(tools.MARCH_CU_ENV, raising=False)
    assert tools.kissat_command(refresh=True) == [sys.executable, "-q"]
    assert tools.march_cu_command(refresh=True) is None
    monkeypatch.setenv(tools.MARCH_CU_ENV, str(binary))
    assert tools.march_cu_command(refresh=True) == [str(binary)]
    assert tools.kissat_command(refresh=True) == [sys.executable, "-q"]
