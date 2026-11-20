"""`Workspace`: la capa que une un espacio de nombres (el del notebook) con los inspectores.

No sabe nada de HTTP: recibe peticiones ya parseadas y devuelve diccionarios JSON-serializables.
Así se puede probar sin servidor y reutilizar desde otras interfaces.
"""

from __future__ import annotations

import threading
import types
from typing import Any, Callable, Dict, List, Mapping, MutableMapping, Optional, Sequence

from . import inspectors
from .inspectors.base import inspector_for, parse_literal
from .stats import STAT_NAMES, compute_stats
from .util import jsonable, format_scalar

#: Nombres que IPython/Jupyter inyectan y que no son "variables del usuario".
_IPYTHON_NAMES = {"In", "Out", "get_ipython", "exit", "quit", "open"}

#: Máximo de elementos para calcular estadísticas en la tabla principal (en el detalle no hay tope práctico).
TABLE_STATS_LIMIT = 500_000


class WorkspaceError(Exception):
    """Error esperable (nombre inexistente, valor inválido...). El servidor lo devuelve como 4xx."""


class Workspace:
    def __init__(self, namespace: MutableMapping[str, Any], *, exclude: Sequence[str] = ()):
        self.ns = namespace
        self.exclude = set(exclude)
        self._version = 0
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ versión (para auto-refresco)
    @property
    def version(self) -> int:
        return self._version

    def bump(self) -> None:
        """Marca que el espacio de nombres pudo cambiar (lo llama el hook post_run_cell)."""
        self._version += 1

    # ------------------------------------------------------------------ nombres visibles
    def _visible(self, name: str) -> bool:
        return not name.startswith("_") and name not in _IPYTHON_NAMES and name not in self.exclude

    def _resolve(self, path: Sequence[str]):
        if not path:
            raise WorkspaceError("ruta vacía")
        name, rest = path[0], path[1:]
        if name not in self.ns:
            raise WorkspaceError(f"la variable {name!r} ya no existe")
        obj = self.ns[name]
        for label in rest:
            try:
                obj = inspector_for(obj).child(label)
            except Exception:
                raise WorkspaceError(f"no se encuentra {label!r} dentro de {name!r}") from None
        return obj

    # ------------------------------------------------------------------ tabla de variables
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

    def list_variables(self, show_hidden: bool = False) -> dict:
        with self._lock:
            rows = []
            for name in sorted(list(self.ns), key=str.lower):
                if not self._visible(name):
                    continue
                try:
                    r = self.row(name, self.ns[name])
                except Exception as exc:  # un objeto raro no debe romper toda la tabla
                    r = {"name": name, "class": type(self.ns[name]).__name__, "kind": "object", "size": "?",
                         "bytes": 0, "value": f"<error: {exc}>", "hidden": False, "expandable": False, "stats": {}}
                if r["hidden"] and not show_hidden:
                    continue
                rows.append(r)
            return {"version": self._version, "variables": rows, "stat_names": list(STAT_NAMES)}

    # ------------------------------------------------------------------ detalle de un objeto
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

    # ------------------------------------------------------------------ edición
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
        """Reasigna una variable de nivel superior, o un hijo de un contenedor, desde un literal."""
        with self._lock:
            try:
                value = parse_literal(str(text))
            except ValueError as exc:
                raise WorkspaceError(str(exc)) from None
            if len(path) == 1:
                if path[0] not in self.ns:
                    raise WorkspaceError(f"la variable {path[0]!r} ya no existe")
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
                raise WorkspaceError(f"la variable {name!r} no existe")
            del self.ns[name]
            self.bump()
            return {"ok": True}
