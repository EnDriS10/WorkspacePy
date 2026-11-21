"""Public API: start / open / show / stop, IPython hook and registry for the VS Code extension."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .server import WorkspaceServer
from .workspace import Workspace

#: Active servers, one per namespace (keyed by the dict id).
_ACTIVE: Dict[int, "Handle"] = {}

#: The VS Code extension reads this file to know which URL to connect to.
REGISTRY_DIR = Path(os.environ.get("WORKSPACEPY_HOME", Path.home() / ".workspacepy"))
REGISTRY_FILE = REGISTRY_DIR / "active.json"


class Handle:
    """What `start()` returns: groups workspace + server and offers open/show/stop."""

    def __init__(self, ws: Workspace, server: WorkspaceServer, ip=None):
        self.workspace = ws
        self.server = server
        self._ip = ip
        self._hook = None

    @property
    def url(self) -> str:
        return self.server.url

    def open(self, browser: bool = True) -> str:
        """Open the UI in the system browser (if `browser`) and return the URL."""
        if browser:
            import webbrowser

            webbrowser.open(self.url)
        return self.url

    def show(self, height: int = 600, width: str = "100%"):
        """Embed the UI in the cell output (JupyterLab / classic Jupyter)."""
        from IPython.display import IFrame

        return IFrame(self.url, width=width, height=height)

    def instructions(self) -> str:
        """The same short instructions that `start()` prints."""
        return instructions(self.url)

    def refresh(self) -> None:
        self.workspace.bump()

    def stop(self) -> None:
        if self._ip is not None and self._hook is not None:
            try:
                self._ip.events.unregister("post_run_cell", self._hook)
            except Exception:
                pass
        self.server.stop()
        _unregister(self.server.port)
        _ACTIVE.pop(id(self.workspace.ns), None)

    def __repr__(self) -> str:
        state = "running" if self.server.running else "stopped"
        return f"<WorkspacePy {state}: {self.url}>"

    _repr_pretty_ = lambda self, p, cycle: p.text(repr(self))  # noqa: E731


# ------------------------------------------------------------------------- registry for VS Code
def _read_registry() -> dict:
    try:
        return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_registry(data: dict) -> None:
    try:
        REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
        tmp = REGISTRY_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, REGISTRY_FILE)
        try:
            os.chmod(REGISTRY_FILE, 0o600)  # contains the token
        except OSError:
            pass
    except OSError:
        pass  # the registry is optional: without it only the VS Code auto-open stops working


def _register(server: WorkspaceServer) -> None:
    data = _read_registry()
    data = {k: v for k, v in data.items() if _pid_alive(v.get("pid", -1))}
    data[str(server.port)] = {"url": server.url, "pid": os.getpid(), "time": time.time()}
    _write_registry(data)


def _unregister(port: int) -> None:
    data = _read_registry()
    if data.pop(str(port), None) is not None:
        _write_registry(data)


def _pid_alive(pid) -> bool:
    """True if a process with this pid is running. Never signals the process on Windows.

    Note: `os.kill(pid, 0)` is a harmless existence check on POSIX, but on Windows it calls
    TerminateProcess and would kill the process, so Windows uses the Win32 API instead.
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


# ------------------------------------------------------------------------- user instructions
def instructions(url: str) -> str:
    """Short, copy-friendly instructions printed by `start()`."""
    mod = "Cmd" if sys.platform == "darwin" else "Ctrl"
    return (
        "WorkspacePy is running.\n"
        f"  VS Code : {mod}+Shift+P  ->  Simple Browser: Show  ->  paste the URL below\n"
        "            (with the WorkspacePy extension installed, the panels open by themselves)\n"
        "  Browser : ws.open()\n"
        f"  URL     : {url}"
    )


# ------------------------------------------------------------------------- API
def _current_ipython():
    try:
        from IPython import get_ipython

        return get_ipython()
    except ImportError:
        return None


def start(namespace: Optional[dict] = None, *, port: int = 0, open_browser: bool = False,
          register: bool = True, quiet: bool = False) -> Handle:
    """Start the workspace on `namespace` (by default, the current notebook's).

    In a script without IPython pass `namespace=globals()`. Calling it twice returns the same handle.
    """
    ip = _current_ipython()
    if namespace is None:
        if ip is None:
            raise RuntimeError("outside IPython/Jupyter pass the namespace: workspacepy.start(globals())")
        namespace = ip.user_ns
    existing = _ACTIVE.get(id(namespace))
    if existing is not None and existing.server.running:
        if open_browser:
            existing.open()
        return existing

    ws = Workspace(namespace, exclude=("workspace", "ws"))
    server = WorkspaceServer(ws, port=port).start()
    handle = Handle(ws, server, ip)
    if ip is not None:
        def _on_cell_done(*_args, **_kwargs):
            ws.bump()

        ip.events.register("post_run_cell", _on_cell_done)
        handle._hook = _on_cell_done
    _ACTIVE[id(namespace)] = handle
    if register:
        _register(server)
    if open_browser:
        handle.open()
    if not quiet:
        print(instructions(handle.url))
    return handle


def stop() -> None:
    """Stop all servers of this process."""
    for handle in list(_ACTIVE.values()):
        handle.stop()


def active() -> Optional[Handle]:
    """Handle of the active workspace (if any)."""
    for handle in _ACTIVE.values():
        if handle.server.running:
            return handle
    return None


# ------------------------------------------------------------------------- IPython magic
def load_ipython_extension(ipython) -> None:
    """`%load_ext workspacepy` registers `%workspace [open|show|stop|url]` and starts it."""
    from IPython.core.magic import register_line_magic

    @register_line_magic("workspace")
    def _workspace(line: str = ""):
        arg = (line or "").strip().lower()
        if arg == "stop":
            stop()
            return None
        handle = start(ipython.user_ns, quiet=True)
        if arg == "open":
            handle.open()
        if arg == "show":
            return handle.show()
        print(instructions(handle.url))
        return None

    start(ipython.user_ns)


def unload_ipython_extension(ipython) -> None:
    stop()
