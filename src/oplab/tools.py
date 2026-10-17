"""External binaries this repository drives, and how they are found.

Two of the jobs here are better done by a solver or a cubing tool of their own
than by a Python binding, because the *interface* the binding offers is the one
that is missing — or, on Windows, because the binding itself is broken:

* :func:`kissat_command` — a real Kissat (rel-4.0.4).  The bundled ``pysat``
  wheel for that version is unusable on Windows: on a two-clause instance it
  either dies with an access violation or answers ``sat`` with a model that
  satisfies nothing (see the tests).  A binary built from upstream is the same
  engine with a working interface.
* :func:`march_cu_command` — Marijn Heule's ``march_cu``, the cube generator of
  the cube-and-conquer toolchain.  There is no Python package for it.

Discovery is deliberately boring, in this order:

1. the environment variable (:data:`KISSAT_ENV`, :data:`MARCH_CU_ENV`), which
   may be a whole command line, so a native build, a Docker wrapper or a WSL
   call can all be named;
2. the binary on ``PATH`` under its usual name;
3. a build from source in the documented WSL location, if ``wsl`` is available.

Nothing here decides anything: a command is only returned if it can be started,
and the caller still has to look at what the tool answered.  Building the two
tools is documented in ``docs/methodology.md``; the pinned revisions are in
``docs/tools.pin``.

A returned command whose first word is ``wsl`` runs under WSL, so any *file
path* handed to it has to be converted with :func:`wsl_path` — this is the same
convention ``scripts/drat_trim_check.py`` uses for the external proof checker.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess

#: A whole command line for the Kissat binary, e.g. ``wsl -e /home/me/kissat/build/kissat``
KISSAT_ENV = "OPLAB_KISSAT"

#: A whole command line for march_cu, e.g. ``/opt/march-cu/march_cu``
MARCH_CU_ENV = "OPLAB_MARCH_CU"

#: The binaries as they are normally called.
KISSAT_NAME = "kissat"
MARCH_CU_NAME = "march_cu"

#: Where a from-source build is looked for *inside* WSL, relative to ``$HOME``.
#: ``docs/methodology.md`` gives the exact commands that produce these paths.
WSL_KISSAT = "kissat/build/kissat"
WSL_MARCH_CU = "march-cu/march_cu"

#: How long a discovery command may take; a wedged ``wsl`` must not hang a call.
PROBE_SECONDS = 30.0

#: The expensive answer, and only that one: whether a from-source build exists
#: inside WSL costs a process, while reading an environment variable or scanning
#: ``PATH`` does not.  Caching the cheap ones too would let a variable that a
#: later caller sets be served stale.
_wsl_cache: dict[str, list[str] | None] = {}
_shell: tuple[str, ...] | None = None


def split_command(text: str | None) -> list[str]:
    """A command line as an argument vector; ``None`` or blank gives ``[]``.

    On Windows the split is done without POSIX rules, because those treat ``\\``
    as an escape: ``C:\\tools\\kissat.exe`` would lose its backslashes and stop
    being a path.  Surrounding quotes are removed from each word, which is what
    lets a path with a space in it be written as one argument.
    """
    if not text or not text.strip():
        return []
    if os.name != "nt":
        return shlex.split(text)
    words = shlex.split(text, posix=False)
    return [word[1:-1] if len(word) > 1 and word[0] == word[-1] and word[0] in "\"'"
            else word for word in words]


def is_wsl(command) -> bool:
    """Whether a command runs under WSL (so its file paths need converting).

    Only the *first* word decides: a wrapper that happens to mention ``wsl``
    later is a native command.  The separator is normalised first, because the
    command may have been written on Windows, where the separator is a backslash
    and `os.path.basename` on a POSIX host does not treat it as one.
    """
    if not command:
        return False
    first = str(command[0]).replace("\\", "/")
    return os.path.basename(first).lower() in ("wsl", "wsl.exe")


def wsl_path(path) -> str:
    """``D:\\gen\\x`` as ``/mnt/d/gen/x``: a path a WSL command can open.

    A relative path is resolved first, because the working directory a WSL command
    starts in is the ``/mnt/...`` spelling of this one rather than the ``D:\\...``
    one: handing over ``runs/k97.cnf`` unchanged has it look for that name under its
    own root, which is how a cube file that exists turns into "no such file".
    """
    text = str(path)
    if text.startswith("/"):
        return text  # a path a Linux command can already open, as it is
    drive, rest = os.path.splitdrive(text)
    if not drive:
        # a relative Windows path: make it absolute before deciding, because the
        # working directory a WSL command starts in is not this one
        text = os.path.abspath(text)
        drive, rest = os.path.splitdrive(text)
    if not drive:
        return text  # a Linux path, absolute now
    return "/mnt/" + drive.rstrip(":").lower() + rest.replace("\\", "/")


def wsl_shell(refresh: bool = False) -> tuple[str, ...] | None:
    """How to run a command inside WSL here, or ``None`` if there is no WSL."""
    global _shell
    if refresh:
        _shell = None
    if _shell is None:
        for name in ("wsl.exe", "wsl"):
            found = shutil.which(name)
            if found:
                _shell = (found,)
                break
        else:
            _shell = ()
    return _shell or None


def _runnable(program: str) -> bool:
    """Whether the first word of a command can be started at all."""
    return bool(program) and (shutil.which(program) is not None or os.path.exists(program))


def _in_wsl(relative: str, refresh: bool = False) -> list[str] | None:
    """A built tool at ``$HOME/<relative>`` inside WSL, as a command, or ``None``.

    ``test -x`` inside the distribution is the only honest check: a Windows-side
    existence test cannot see it, and assuming the path exists is how a
    "found" binary turns into an ``exit 127`` in the middle of a campaign.  This
    is the one probe that is remembered (until ``refresh``), because it costs a
    WSL start-up and its answer only changes when someone builds the tool.
    """
    if not refresh and relative in _wsl_cache:
        return _wsl_cache[relative]
    shell = wsl_shell(refresh=refresh)
    if shell is None:  # pragma: no cover - depends on the platform
        _wsl_cache[relative] = None
        return None
    script = f'test -x "$HOME/{relative}" && printf "%s" "$HOME/{relative}"'
    try:
        done = subprocess.run([*shell, "-e", "bash", "-lc", script],
                              capture_output=True, text=True, timeout=PROBE_SECONDS)
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - depends on the platform
        _wsl_cache[relative] = None
        return None
    found = done.stdout.strip()
    command = [*shell, "-e", found] if done.returncode == 0 and found else None
    _wsl_cache[relative] = command
    return command


def find_tool(env_var: str, name: str, wsl_relative: str, refresh: bool = False,
              ) -> list[str] | None:
    """The command for one external tool, or ``None`` if there is none here.

    An environment variable that names something unstartable is skipped rather
    than returned: "the tool is configured but missing" would otherwise surface
    as a tool that fails once per instance instead of as a tool that is absent.
    A variable set *later* is still seen, because neither the variable nor
    ``PATH`` is remembered — only the WSL probe is.
    """
    command = split_command(os.environ.get(env_var))
    if command and (is_wsl(command) or _runnable(command[0])):
        return command
    found = shutil.which(name)
    if found:
        return [found]
    return _in_wsl(wsl_relative, refresh=refresh)


def kissat_command(refresh: bool = False) -> list[str] | None:
    """A real Kissat, as a command line, or ``None``.

    Set :data:`KISSAT_ENV` (``OPLAB_KISSAT``) to point at one, or build it as
    ``~/kissat/build/kissat`` under WSL.  The version matters: the repository
    only ever names 4.0.4, the release the bundled wheel also claims to be.
    """
    return find_tool(KISSAT_ENV, KISSAT_NAME, WSL_KISSAT, refresh=refresh)


def march_cu_command(refresh: bool = False) -> list[str] | None:
    """``march_cu``, the cube generator, as a command line, or ``None``."""
    return find_tool(MARCH_CU_ENV, MARCH_CU_NAME, WSL_MARCH_CU, refresh=refresh)


def bounded_wsl(command, seconds: float | None) -> list[str] | None:
    """``command`` with a hard ceiling inside WSL, or ``None`` if it cannot carry one.

    A subprocess timeout on this side kills the launcher (``wsl.exe``), not the
    Linux process behind it: the orphan closes the pipes only when *it* finishes, so
    the caller waits for it anyway, and in the meantime it keeps a core busy.  For a
    sweep of thousands of cubes that is the difference between a partition and a
    thrash.  Coreutils ``timeout`` inside the distribution kills the real process,
    and it is only added to the ``wsl -e <binary>`` shape :func:`find_tool`
    produces; any other command is left alone, with the caller's own timeout as the
    only backstop.
    """
    if seconds is None or not is_wsl(command) or len(command) < 3 or command[1] != "-e":
        return None
    return [*command[:-1], "timeout", f"{float(seconds):g}", command[-1]]


def describe(command) -> str:
    """A command as a human would name it, for a report or an error message."""
    return " ".join(command) if command else "<none>"
