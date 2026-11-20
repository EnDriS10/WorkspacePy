"""SymPy inspector: expressions, symbols, equations and symbolic matrices."""

from __future__ import annotations

from typing import List, Tuple

from ..util import format_scalar, get_module, short_repr, size_label
from .base import Inspector, clamp_window, make_window, register


def _latex(obj) -> str:
    sp = get_module("sympy")
    try:
        return sp.latex(obj)
    except Exception:
        return str(obj)


@register
class SympyMatrixInspector(Inspector):
    kind = "sympy"
    priority = 95

    @classmethod
    def matches(cls, obj) -> bool:
        sp = get_module("sympy")
        if sp is None:
            return False
        try:
            return isinstance(obj, (sp.MatrixBase, sp.ImmutableMatrix)) or isinstance(obj, sp.NDimArray)
        except Exception:
            return False

    def shape(self):
        return tuple(self.obj.shape)

    def preview(self) -> str:
        return short_repr(str(self.obj.tolist() if hasattr(self.obj, "tolist") else self.obj))

    def numeric(self):
        return None

    def properties(self) -> List[Tuple[str, str]]:
        m = self.obj
        props = [("shape", str(tuple(m.shape))), ("free symbols", ", ".join(sorted(str(s) for s in m.free_symbols)) or "—")]
        if len(m.shape) == 2 and m.shape[0] == m.shape[1] and m.shape[0] <= 8 and hasattr(m, "is_symmetric"):
            try:
                props.append(("symmetric", str(m.is_symmetric())))
            except Exception:
                pass
        return props

    def detail(self) -> dict:
        out = {"latex": _latex(self.obj) if len(self.obj) <= 400 else "", "str": str(self.obj)[:2000]}
        if len(self.obj.shape) == 2:
            out["table"] = True
        return out

    def window(self, r0, r1, c0, c1, index, digits):
        m = self.obj
        if len(m.shape) != 2:
            return None
        nrows, ncols = m.shape
        r0, r1, c0, c1 = clamp_window(nrows, ncols, r0, r1, c0, c1)
        values = [[m[i, j] for j in range(c0, c1)] for i in range(r0, r1)]
        return make_window(values, nrows, ncols, r0, c0, digits, formatter=lambda v, d: str(v),
                           editable=False, lead_shape=[], index=[])

    def plot_kinds(self):
        return []


@register
class SympyExprInspector(Inspector):
    kind = "sympy"
    priority = 90

    @classmethod
    def matches(cls, obj) -> bool:
        sp = get_module("sympy")
        if sp is None:
            return False
        try:
            return isinstance(obj, sp.Basic) and not isinstance(obj, type)
        except Exception:
            return False

    def class_name(self) -> str:
        return type(self.obj).__name__

    def preview(self) -> str:
        return short_repr(str(self.obj))

    def numeric(self):
        return None

    def properties(self) -> List[Tuple[str, str]]:
        e = self.obj
        props = [("class", type(e).__name__), ("free symbols", ", ".join(sorted(str(s) for s in e.free_symbols)) or "—")]
        for name, label in (("is_number", "is number"), ("is_real", "real"), ("is_integer", "integer"),
                            ("is_positive", "positive"), ("is_polynomial", None)):
            if label is None:
                continue
            try:
                val = getattr(e, name)
                props.append((label, str(val)))
            except Exception:
                pass
        try:
            props.append(("operation count", str(e.count_ops())))
        except Exception:
            pass
        return props

    def detail(self) -> dict:
        sp = get_module("sympy")
        e = self.obj
        out = {"latex": _latex(e), "str": str(e)[:4000], "free_symbols": sorted(str(s) for s in e.free_symbols)}
        if getattr(e, "is_number", False):
            try:
                out["numeric"] = format_scalar(complex(sp.N(e, 15)) if getattr(e, "is_real", None) is False else float(sp.N(e, 15)), 15)
            except Exception:
                pass
        return out

    def plot_kinds(self):
        return []
