"""Clase base `Inspector`, registro de inspectores y utilidades comunes de table windows.

An *inspector* knows how to describe one kind of object: what to show in the workspace row
(Name / Value / Size / Bytes / Class), what to show when it is opened (properties, table, children)
and which plots it offers. To support a new type just subclass `Inspector`,
implement `matches` and decorate the class with `@register`.
"""

from __future__ import annotations

import ast
from itertools import islice
from typing import Any, Iterator, List, Optional, Sequence, Tuple

from ..plots import available_plots, build_plot
from ..stats import as_numeric_array
from ..util import deep_sizeof, format_scalar, short_repr, size_label

MAX_WIN_ROWS = 200
MAX_WIN_COLS = 50
MAX_CELL_CHARS = 80

_REGISTRY: List[type] = []


def register(cls):
    """Decorator: add an inspector to the registry (sorted by `priority`, highest first)."""
    if cls not in _REGISTRY:
        _REGISTRY.append(cls)
        _REGISTRY.sort(key=lambda c: -c.priority)
    return cls


def inspector_for(obj: Any) -> "Inspector":
    """Return the right inspector for `obj` (there is always one: the generic fallback)."""
    for cls in _REGISTRY:
        try:
            if cls.matches(obj):
                return cls(obj)
        except Exception:
            continue
    raise RuntimeError("no generic inspector registered")  # pragma: no cover


def registered_inspectors() -> list:
    return list(_REGISTRY)


# --------------------------------------------------------------------------- value parsing


def parse_value(text: str, dtype_kind: str) -> Any:
    """Convert the text of an edited cell to the type of a NumPy array (by dtype.kind)."""
    t = text.strip()
    if dtype_kind == "b":
        low = t.lower()
        if low in ("true", "1", "t", "yes"):
            return True
        if low in ("false", "0", "f", "no"):
            return False
        raise ValueError("invalid boolean value (use True/False)")
    if dtype_kind in "iu":
        try:
            return int(t)
        except ValueError:
            f = float(t)
            if f != int(f):
                raise ValueError("the array holds integers; that value has decimals") from None
            return int(f)
    if dtype_kind == "f":
        if t.count(",") == 1 and "." not in t:
            t = t.replace(",", ".")
        return float(t)
    if dtype_kind == "c":
        t = t.replace(" ", "")
        if t.endswith("i"):
            t = t[:-1] + "j"
        return complex(t)
    return text


def parse_literal(text: str) -> Any:
    """Interpret text as a Python literal (3, 2.5, 'hello', [1, 2], ...). Never executes code."""
    try:
        return ast.literal_eval(text.strip())
    except (ValueError, SyntaxError):
        raise ValueError("not a valid Python literal (numbers, 'text', lists, ...)") from None


# --------------------------------------------------------------------------- table windows


def clamp_window(nrows: int, ncols: int, r0: int, r1: int, c0: int, c1: int) -> Tuple[int, int, int, int]:
    r0 = max(0, min(int(r0), nrows))
    c0 = max(0, min(int(c0), ncols))
    r1 = max(r0, min(int(r1), nrows, r0 + MAX_WIN_ROWS))
    c1 = max(c0, min(int(c1), ncols, c0 + MAX_WIN_COLS))
    return r0, r1, c0, c1


def _cut(text: str) -> str:
    return text if len(text) <= MAX_CELL_CHARS else text[: MAX_CELL_CHARS - 1] + "…"


def make_window(values, nrows: int, ncols: int, r0: int, c0: int, digits: int = 6, *,
                row_labels: Optional[Sequence[str]] = None,
                col_labels: Optional[Sequence[str]] = None,
                formatter=None, **extra) -> dict:
    """Pack a window of cells (list of lists) ready to send to the browser."""
    fmt = formatter or format_scalar
    cells = [[_cut(fmt(v, digits)) for v in row] for row in values]
    r1 = r0 + len(cells)
    c1 = c0 + (len(cells[0]) if cells else 0)
    out = {
        "nrows": int(nrows), "ncols": int(ncols),
        "r0": r0, "r1": r1, "c0": c0, "c1": c1,
        "cells": cells,
        "row_labels": list(row_labels) if row_labels is not None else [str(i) for i in range(r0, r1)],
        "col_labels": list(col_labels) if col_labels is not None else [str(j) for j in range(c0, c1)],
    }
    out.update(extra)
    return out


# --------------------------------------------------------------------------- base class


class Inspector:
    """Describe an object for the workspace. Subclasses: see `arrays.py`, `symbolic.py`, ..."""

    #: front-end viewer kind: "array" | "table" | "sympy" | "container" | "scalar" | "callable" | "object"
    kind: str = "object"
    #: check order (higher = earlier)
    priority: int = 0
    #: if True, it is not listed unless "functions/modules" is enabled
    hidden: bool = False

    def __init__(self, obj: Any):
        self.obj = obj

    @classmethod
    def matches(cls, obj: Any) -> bool:
        return False

    # ------------------------------------------------------------- table columns
    def class_name(self) -> str:
        return type(self.obj).__name__

    def shape(self) -> Optional[tuple]:
        return None

    def size_label(self) -> str:
        return size_label(self.shape())

    def nbytes(self) -> int:
        return deep_sizeof(self.obj)

    def preview(self) -> str:
        return short_repr(self.obj)

    def numeric(self):
        """Equivalent numeric NumPy array (for statistics and plots) or None."""
        return as_numeric_array(self.obj)

    # ------------------------------------------------------------- vista de detalle
    def properties(self) -> List[Tuple[str, str]]:
        t = type(self.obj)
        return [("type", f"{t.__module__}.{t.__qualname__}")]

    def detail(self) -> dict:
        """Extra viewer-specific fields (LaTeX, signature, full value, columns, ...)."""
        return {}

    # ------------------------------------------------------------- navigation (double click on children)
    def n_children(self) -> Optional[int]:
        return None

    def iter_children(self) -> Iterator[Tuple[str, Any]]:
        return iter(())

    def child(self, label: str) -> Any:
        for lab, val in self.iter_children():
            if lab == label:
                return val
        raise KeyError(label)

    def children_page(self, offset: int, limit: int) -> Tuple[Optional[int], list]:
        items = list(islice(self.iter_children(), offset, offset + limit))
        return self.n_children(), items

    def set_child(self, label: str, text: str) -> None:
        raise ValueError("this object is read-only")

    # ------------------------------------------------------------- editable tables
    def window(self, r0: int, r1: int, c0: int, c1: int, index: Sequence[int], digits: int) -> Optional[dict]:
        return None

    def set_item(self, index: Sequence[int], row: int, col: int, text: str) -> str:
        raise ValueError("this object is read-only")

    # ------------------------------------------------------------- plots
    def plot_kinds(self) -> list:
        arr = self.numeric()
        return available_plots(arr) if arr is not None and arr.size else []

    def plot(self, kind: str, index: Sequence[int], params: dict) -> dict:
        arr = self.numeric()
        if arr is None or arr.size == 0:
            raise ValueError("this object cannot be represented numerically")
        return build_plot(arr, kind, index)
