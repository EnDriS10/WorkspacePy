"""Clase base `Inspector`, registro de inspectores y utilidades comunes de ventanas de tabla.

Un *inspector* sabe describir un tipo de objeto: qué mostrar en la fila del workspace
(Name / Value / Size / Bytes / Class), qué mostrar al abrirlo (propiedades, tabla, hijos)
y qué gráficas ofrece. Para soportar un tipo nuevo basta con heredar de `Inspector`,
implementar `matches` y decorar la clase con `@register`.
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
    """Decorador: añade un inspector al registro (se ordena por `priority`, mayor primero)."""
    if cls not in _REGISTRY:
        _REGISTRY.append(cls)
        _REGISTRY.sort(key=lambda c: -c.priority)
    return cls


def inspector_for(obj: Any) -> "Inspector":
    """Devuelve el inspector adecuado para `obj` (siempre hay uno: GenericInspector)."""
    for cls in _REGISTRY:
        try:
            if cls.matches(obj):
                return cls(obj)
        except Exception:
            continue
    raise RuntimeError("no hay inspector genérico registrado")  # pragma: no cover


def registered_inspectors() -> list:
    return list(_REGISTRY)


# --------------------------------------------------------------------------- parseo de valores


def parse_value(text: str, dtype_kind: str) -> Any:
    """Convierte el texto de una celda editada al tipo de un array NumPy (por dtype.kind)."""
    t = text.strip()
    if dtype_kind == "b":
        low = t.lower()
        if low in ("true", "1", "t", "yes", "si", "sí"):
            return True
        if low in ("false", "0", "f", "no"):
            return False
        raise ValueError("valor booleano no válido (usa True/False)")
    if dtype_kind in "iu":
        try:
            return int(t)
        except ValueError:
            f = float(t)
            if f != int(f):
                raise ValueError("el array es de enteros; ese valor tiene decimales") from None
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
    """Interpreta texto como literal de Python (3, 2.5, 'hola', [1, 2], ...). Nunca ejecuta código."""
    try:
        return ast.literal_eval(text.strip())
    except (ValueError, SyntaxError):
        raise ValueError("no es un literal de Python válido (números, 'texto', listas, ...)") from None


# --------------------------------------------------------------------------- ventanas de tabla


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
    """Empaqueta una ventana de celdas (lista de listas) lista para enviar al navegador."""
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


# --------------------------------------------------------------------------- clase base


class Inspector:
    """Describe un objeto para el workspace. Subclases: ver `arrays.py`, `symbolic.py`, ..."""

    #: tipo de visor del front-end: "array" | "table" | "sympy" | "container" | "scalar" | "callable" | "object"
    kind: str = "object"
    #: orden de comprobación (mayor = antes)
    priority: int = 0
    #: si True, no aparece en la tabla salvo que se active "mostrar funciones/módulos"
    hidden: bool = False

    def __init__(self, obj: Any):
        self.obj = obj

    @classmethod
    def matches(cls, obj: Any) -> bool:
        return False

    # ------------------------------------------------------------- columnas de la tabla
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
        """Array NumPy numérico equivalente (para estadísticas y gráficas) o None."""
        return as_numeric_array(self.obj)

    # ------------------------------------------------------------- vista de detalle
    def properties(self) -> List[Tuple[str, str]]:
        t = type(self.obj)
        return [("tipo", f"{t.__module__}.{t.__qualname__}")]

    def detail(self) -> dict:
        """Campos extra específicos del visor (LaTeX, firma, valor completo, columnas, ...)."""
        return {}

    # ------------------------------------------------------------- navegación (doble clic en hijos)
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
        raise ValueError("este objeto es de solo lectura")

    # ------------------------------------------------------------- tablas editables
    def window(self, r0: int, r1: int, c0: int, c1: int, index: Sequence[int], digits: int) -> Optional[dict]:
        return None

    def set_item(self, index: Sequence[int], row: int, col: int, text: str) -> str:
        raise ValueError("este objeto es de solo lectura")

    # ------------------------------------------------------------- gráficas
    def plot_kinds(self) -> list:
        arr = self.numeric()
        return available_plots(arr) if arr is not None and arr.size else []

    def plot(self, kind: str, index: Sequence[int], params: dict) -> dict:
        arr = self.numeric()
        if arr is None or arr.size == 0:
            raise ValueError("este objeto no se puede representar numéricamente")
        return build_plot(arr, kind, index)
