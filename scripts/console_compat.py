"""
Cross-platform console helpers for the Wiz Health Assessment tooling.

The scripts in this repo print status symbols (checkmarks, bullets, severity
dots). On Linux and macOS those encode fine because the default stdout encoding
is UTF-8. On Windows the console defaults to a legacy code page (cp1252 /
cp437), where printing any of those characters raises UnicodeEncodeError and
kills the run mid-way.

Entry-point scripts call enable_unicode_output() once at startup so the same
output works everywhere.
"""

import os
import sys

_configured = False


def enable_unicode_output():
    """Make stdout/stderr able to carry non-ASCII text on any platform.

    Safe to call more than once and never raises: if a step is unavailable we
    fall back to replacement characters rather than letting an encoding error
    abort the caller.
    """
    global _configured
    if _configured:
        return
    _configured = True

    if os.name == "nt":
        # Ask the Windows console for UTF-8 so symbols render as themselves
        # rather than as mojibake. Only the output code page is changed;
        # leaving the input code page alone keeps input() behaving normally.
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        except Exception:
            pass

    # errors="replace" is the actual crash guard: even when the stream cannot
    # be switched to UTF-8 (a pipe or a file opened under a legacy code page),
    # unencodable characters degrade to "?" instead of raising.
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def python_command():
    """The interpreter name to show users when telling them to re-run a script.

    Windows installs expose "python"; Linux and macOS conventionally expose
    "python3" (where bare "python" may be missing or may be Python 2).
    """
    return "python" if os.name == "nt" else "python3"


def prompt(message, default=""):
    """input() that survives a closed or piped stdin.

    Returns the default when there is no interactive terminal, so unattended
    runs finish instead of crashing with EOFError.
    """
    try:
        return input(message).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default


def find_env_file(plugin_root=None):
    """Locate the Wiz-credentials .env, working in BOTH clone mode and plugin mode.

    When this tool is installed as a Claude Code plugin, the code lives in a
    Claude-managed directory the user can't edit, so the .env must come from the
    user's own working directory instead. Search order (first hit wins):

      1. $ENV_FILE                     - explicit override
      2. $CLAUDE_PROJECT_DIR/.env      - plugin mode: the user's project dir
      3. ./.env                        - current working directory
      4. <plugin_root>/.env            - clone mode: the repo root

    Returns a pathlib.Path or None. Env vars (WIZ_CLIENT_ID, ...) still work on
    their own; this only locates a file to layer on top of them.
    """
    from pathlib import Path
    candidates = []
    if os.environ.get("ENV_FILE"):
        candidates.append(Path(os.environ["ENV_FILE"]))
    if os.environ.get("CLAUDE_PROJECT_DIR"):
        candidates.append(Path(os.environ["CLAUDE_PROJECT_DIR"]) / ".env")
    candidates.append(Path.cwd() / ".env")
    if plugin_root:
        candidates.append(Path(plugin_root) / ".env")
    for c in candidates:
        try:
            if c and c.is_file():
                return c
        except OSError:
            continue
    return None


def default_env_write_path(plugin_root=None):
    """Where setup_credentials should WRITE a new .env.

    Prefer the user's project dir ($CLAUDE_PROJECT_DIR) then the current working
    directory, so a plugin install writes somewhere the user actually owns.
    Falls back to the repo root only in clone mode.
    """
    from pathlib import Path
    if os.environ.get("CLAUDE_PROJECT_DIR"):
        return Path(os.environ["CLAUDE_PROJECT_DIR"]) / ".env"
    if plugin_root and not os.environ.get("CLAUDE_PLUGIN_ROOT"):
        # clone mode: repo root is user-editable
        return Path(plugin_root) / ".env"
    return Path.cwd() / ".env"
