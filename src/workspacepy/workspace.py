"""`Workspace`: the layer that joins a namespace (the notebook's) with the inspectors.

It knows nothing about HTTP: it receives parsed requests and returns JSON-serializable dicts.
That way it can be tested without a server and reused from other interfaces.
"""

from __future__ import annotations

import threading
import types
from collections import deque
from typing import Any, Callable, Dict, List, Mapping, MutableMapping, Optional, Sequence

from . import inspectors
from .inspectors.base import inspector_for, parse_literal
from .stats import STAT_NAMES, compute_stats
from .util import jsonable, format_scalar

#: Names injected by IPython/Jupyter that are not "user variables".
_IPYTHON_NAMES = {"In", "Out", "get_ipython", "exit", "quit", "open"}

#: Maximum number of elements for which statistics are computed in the main table (the detail view has no practical cap).
TABLE_STATS_LIMIT = 500_000


class WorkspaceError(Exception):
    """Expected error (missing name, invalid value...). The server returns it as a 4xx."""


class Workspace:
    def __init__(self, namespace: MutableMapping[str, Any], *, exclude: Sequence[str] = ()):
        self.ns = namespace
        self.exclude = set(exclude)
        self._version = 0
        self._lock = threading.RLock()
        # Requests to open an object in the viewer (the workspace panel and the viewer panel are
        # separate pages in the VS Code extension, so they talk through the kernel).
        self._open_seq = 0
        self._open_requests: deque = deque(maxlen=50)

    # ------------------------------------------------------------------ version (for auto-refresh)
    @property
    def version(self) -> int:
        return self._version

    def bump(self) -> None:
        """Mark that the namespace may have changed (called by the post_run_cell hook)."""
        self._version += 1

    # ------------------------------------------------------------------ open requests
    @property
    def open_seq(self) -> int:
        return self._open_seq

    def request_open(self, path: Sequence[str]) -> dict:
        """Ask every viewer page to open `path` (validated first, so stale clicks fail loudly)."""
        with self._lock:
            self._resolve(path)
            self._open_seq += 1
            self._open_requests.append((self._open_seq, list(path)))
            return {"ok": True, "seq": self._open_seq}

    def close_request(self, path: Sequence[str]) -> dict:
        """Forget an open request (the viewer tab was closed), so a reloaded viewer does not reopen it."""
        with self._lock:
            keep = [(s, p) for s, p in self._open_requests if p != list(path)]
            self._open_requests.clear()
            self._open_requests.extend(keep)
            return {"ok": True}

    def open_requests(self, after: int = 0) -> dict:
        with self._lock:
            return {"seq": self._open_seq, "requests": [{"seq": s, "path": p} for s, p in self._open_requests if s > int(after)]}

    # ------------------------------------------------------------------ visible names
    def _visible(self, name: str) -> bool:
        return not name.startswith("_") and name not in _IPYTHON_NAMES and name not in self.exclude

    def _resolve(self, path: Sequence[str]):
        if not path:
            raise WorkspaceError("empty path")
        name, rest = path[0], path[1:]
        if name not in self.ns:
            raise WorkspaceError(f"variable {name!r} no longer exists")
        obj = self.ns[name]
        for label in rest:
            try:
                obj = inspector_for(obj).child(label)
            except Exception:
                raise WorkspaceError(f"{label!r} not found inside {name!r}") from None
        return obj

    # ------------------------------------------------------------------ variables table
    def row(self, label: str, obj: Any, *, with_stats: bool = True) -> dict:
        insp = inspector_for(obj)
        row = {
            "name": label,
            "class": insp.class_name(),
            "kind": insp.kind,
            "size": insp.size_label(),
            "bytes": insp.nbytes(),
            "value": insp.preview(),
            "hidden": insp.hidden,
            "expandable": insp.n_children() is not None or insp.kind in ("array", "table", "sympy"),
        }
        if with_stats:
            arr = insp.numeric()
            stats = compute_stats(arr) if arr is not None and arr.size <= TABLE_STATS_LIMIT else {}
            row["stats"] = {k: jsonable(stats.get(k)) for k in STAT_NAMES} if stats else {}
        return row

    def list_variables(self, show_hidden: bool = False, with_stats: bool = True) -> dict:
        with self._lock:
            rows = []
            for name in sorted(list(self.ns), key=str.lower):
                if not self._visible(name):
                    continue
                try:
                    r = self.row(name, self.ns[name], with_stats=with_stats)
                except Exception as exc:  # a weird object must not break the whole table
                    r = {"name": name, "class": type(self.ns[name]).__name__, "kind": "object", "size": "?",
                         "bytes": 0, "value": f"<error: {exc}>", "hidden": False, "expandable": False, "stats": {}}
                if r["hidden"] and not show_hidden:
                    continue
                rows.append(r)
            return {"version": self._version, "variables": rows, "stat_names": list(STAT_NAMES)}

    # ------------------------------------------------------------------ object detail
    def describe(self, path: Sequence[str]) -> dict:
        with self._lock:
            obj = self._resolve(path)
            insp = inspector_for(obj)
            arr = insp.numeric()
            stats = compute_stats(arr) if arr is not None else {}
            return {
                "path": list(path),
                "title": " › ".join(path),
                "class": insp.class_name(),
                "kind": insp.kind,
                "size": insp.size_label(),
                "bytes": insp.nbytes(),
                "properties": insp.properties(),
                "stats": {k: jsonable(stats.get(k)) for k in STAT_NAMES} if stats else {},
                "plots": insp.plot_kinds(),
                "has_table": insp.window(0, 1, 0, 1, (), 6) is not None,
                "n_children": insp.n_children(),
                "detail": jsonable(insp.detail()),
            }

    def window(self, path, r0=0, r1=100, c0=0, c1=30, index=(), digits=6) -> dict:
        with self._lock:
            insp = inspector_for(self._resolve(path))
            win = insp.window(int(r0), int(r1), int(c0), int(c1), list(index), int(digits))
            if win is None:
                raise WorkspaceError("este objeto no tiene vista de tabla")
            return win

    def children(self, path, offset=0, limit=200) -> dict:
        with self._lock:
            insp = inspector_for(self._resolve(path))
            total, items = insp.children_page(int(offset), int(limit))
            return {"total": total, "offset": int(offset),
                    "items": [self.row(label, val, with_stats=False) for label, val in items]}

    def plot(self, path, kind, index=(), params: Optional[dict] = None) -> dict:
        with self._lock:
            insp = inspector_for(self._resolve(path))
            try:
                return insp.plot(kind, list(index), params or {})
            except ValueError as exc:
                raise WorkspaceError(str(exc)) from None

    # ------------------------------------------------------------------ editing
    def set_item(self, path, row, col, text, index=()) -> dict:
        with self._lock:
            insp = inspector_for(self._resolve(path))
            try:
                shown = insp.set_item(list(index), int(row), int(col), str(text))
            except ValueError as exc:
                raise WorkspaceError(str(exc)) from None
            self.bump()
            return {"ok": True, "value": shown}

    def set_value(self, path, text) -> dict:
        """Reassign a top-level variable, or a child of a container, from a literal."""
        with self._lock:
            try:
                value = parse_literal(str(text))
            except ValueError as exc:
                raise WorkspaceError(str(exc)) from None
            if len(path) == 1:
                if path[0] not in self.ns:
                    raise WorkspaceError(f"variable {path[0]!r} no longer exists")
                self.ns[path[0]] = value
            else:
                parent = inspector_for(self._resolve(path[:-1]))
                try:
                    parent.set_child(path[-1], str(text))
                except (ValueError, KeyError, IndexError) as exc:
                    raise WorkspaceError(str(exc)) from None
            self.bump()
            return {"ok": True}

    def delete(self, name: str) -> dict:
        with self._lock:
            if name not in self.ns or not self._visible(name):
                raise WorkspaceError(f"variable {name!r} does not exist")
            del self.ns[name]
            self.bump()
            return {"ok": True}
