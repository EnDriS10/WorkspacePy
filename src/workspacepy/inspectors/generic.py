"""Standard Python inspectors: scalars, text, containers, functions/modules and objects."""

from __future__ import annotations

import inspect
import types
from itertools import islice
from typing import List, Tuple

from ..stats import as_numeric_array
from ..util import format_scalar, np, short_repr
from .base import Inspector, clamp_window, make_window, parse_literal, register

MAX_ATTRS = 300
MAX_CHILDREN_PAGE = 500

_SCALARS: tuple = (bool, int, float, complex) + ((np.generic,) if np is not None else ())


@register
class ScalarInspector(Inspector):
    kind = "scalar"
    priority = 60

    @classmethod
    def matches(cls, obj) -> bool:
        return isinstance(obj, _SCALARS) or obj is None

    def class_name(self) -> str:
        return type(self.obj).__name__

    def shape(self):
        return None

    def preview(self) -> str:
        return "None" if self.obj is None else format_scalar(self.obj, 10)

    def numeric(self):
        return as_numeric_array(self.obj) if self.obj is not None else None

    def properties(self):
        t = type(self.obj)
        return [("type", f"{t.__module__}.{t.__qualname__}")]

    def detail(self) -> dict:
        return {"value": "None" if self.obj is None else format_scalar(self.obj, 17), "editable": self.obj is not None}

    def plot_kinds(self):
        return []


@register
class StringInspector(Inspector):
    kind = "scalar"
    priority = 55

    @classmethod
    def matches(cls, obj) -> bool:
        return isinstance(obj, (str, bytes, bytearray))

    def shape(self):
        return (len(self.obj),)

    def size_label(self) -> str:
        return f"1×{len(self.obj)}"

    def preview(self) -> str:
        return short_repr(self.obj)

    def properties(self):
        return [("length", str(len(self.obj)))]

    def detail(self) -> dict:
        text = self.obj if isinstance(self.obj, str) else repr(self.obj)
        return {"value": text[:20000], "truncated": len(text) > 20000, "editable": isinstance(self.obj, str)}

    def numeric(self):
        return None

    def plot_kinds(self):
        return []


@register
class SequenceInspector(Inspector):
    """list, tuple, range, set, frozenset, deque... Numeric lists are also shown as a table."""

    kind = "container"
    priority = 50

    @classmethod
    def matches(cls, obj) -> bool:
        import collections

        return isinstance(obj, (list, tuple, range, set, frozenset, collections.deque))

    def shape(self):
        return (len(self.obj),)

    def size_label(self) -> str:
        return f"1×{len(self.obj)}"

    def preview(self) -> str:
        return short_repr(self.obj)

    def n_children(self):
        return len(self.obj)

    def iter_children(self):
        for i, v in enumerate(self.obj if not isinstance(self.obj, (set, frozenset)) else list(self.obj)):
            yield f"[{i}]", v

    def child(self, label: str):
        i = int(label.strip("[]"))
        if isinstance(self.obj, (set, frozenset)):
            return list(self.obj)[i]
        return self.obj[i]

    def children_page(self, offset, limit):
        limit = min(limit, MAX_CHILDREN_PAGE)
        src = self.obj if not isinstance(self.obj, (set, frozenset)) else list(self.obj)
        items = [(f"[{offset + k}]", v) for k, v in enumerate(islice(src, offset, offset + limit))]
        return len(self.obj), items

    def set_child(self, label: str, text: str) -> None:
        if not isinstance(self.obj, list):
            raise ValueError("only lists can be edited (tuple/set are immutable)")
        self.obj[int(label.strip("[]"))] = parse_literal(text)

    def properties(self):
        return [("length", str(len(self.obj))), ("editable", str(isinstance(self.obj, list)))]

    def detail(self) -> dict:
        return {"editable": isinstance(self.obj, list)}

    def numeric(self):
        return as_numeric_array(self.obj)

    # numeric 1-d or 2-d list (list of lists) -> can also be shown as a table
    def window(self, r0, r1, c0, c1, index, digits):
        arr = self.numeric()
        if arr is None or arr.ndim not in (1, 2):
            return None
        a2 = arr.reshape(-1, 1) if arr.ndim == 1 else arr
        r0, r1, c0, c1 = clamp_window(a2.shape[0], a2.shape[1], r0, r1, c0, c1)
        return make_window(a2[r0:r1, c0:c1].tolist(), a2.shape[0], a2.shape[1], r0, c0, digits,
                           col_labels=["value"] if arr.ndim == 1 else None, editable=False, lead_shape=[], index=[])


@register
class MappingInspector(Inspector):
    kind = "container"
    priority = 50

    @classmethod
    def matches(cls, obj) -> bool:
        from collections.abc import Mapping

        return isinstance(obj, Mapping)

    def shape(self):
        return (len(self.obj),)

    def size_label(self) -> str:
        return f"{len(self.obj)} keys"

    def preview(self) -> str:
        return short_repr(self.obj)

    def n_children(self):
        return len(self.obj)

    def iter_children(self):
        for k, v in self.obj.items():
            yield repr(k), v

    def children_page(self, offset, limit):
        limit = min(limit, MAX_CHILDREN_PAGE)
        items = [(repr(k), v) for k, v in islice(self.obj.items(), offset, offset + limit)]
        return len(self.obj), items

    def set_child(self, label: str, text: str) -> None:
        if not isinstance(self.obj, dict):
            raise ValueError("this mapping is read-only")
        for k in self.obj:
            if repr(k) == label:
                self.obj[k] = parse_literal(text)
                return
        raise KeyError(label)

    def properties(self):
        return [("keys", str(len(self.obj)))]

    def detail(self) -> dict:
        return {"editable": isinstance(self.obj, dict)}

    def plot_kinds(self):
        return []


@register
class CallableInspector(Inspector):
    kind = "callable"
    priority = 40
    hidden = True

    @classmethod
    def matches(cls, obj) -> bool:
        return isinstance(obj, (types.FunctionType, types.BuiltinFunctionType, types.MethodType, type, types.ModuleType)) or (
            callable(obj) and not hasattr(obj, "__dict__")
        )

    def class_name(self) -> str:
        return type(self.obj).__name__

    def preview(self) -> str:
        o = self.obj
        if isinstance(o, types.ModuleType):
            return f"<module {o.__name__}>"
        try:
            return f"{getattr(o, '__name__', type(o).__name__)}{inspect.signature(o)}"
        except (TypeError, ValueError):
            return short_repr(o)

    def properties(self):
        o = self.obj
        props = [("type", type(o).__name__)]
        mod = getattr(o, "__module__", None)
        if mod:
            props.append(("module", str(mod)))
        return props

    def detail(self) -> dict:
        doc = inspect.getdoc(self.obj) or ""
        out = {"doc": doc[:4000]}
        try:
            out["signature"] = str(inspect.signature(self.obj))
        except (TypeError, ValueError):
            pass
        return out

    def numeric(self):
        return None

    def plot_kinds(self):
        return []


@register
class ObjectInspector(Inspector):
    """Last resort: any object. Shows its public attributes as browsable children."""

    kind = "object"
    priority = -100

    @classmethod
    def matches(cls, obj) -> bool:
        return True

    def preview(self) -> str:
        return short_repr(self.obj)

    def _attrs(self) -> List[Tuple[str, object]]:
        out = []
        for name in dir(self.obj):
            if name.startswith("_"):
                continue
            try:
                val = getattr(self.obj, name)
            except Exception:
                continue
            if callable(val) and not isinstance(val, type):
                continue
            out.append((name, val))
            if len(out) >= MAX_ATTRS:
                break
        return out

    def n_children(self):
        return len(self._attrs())

    def iter_children(self):
        return iter(self._attrs())

    def properties(self):
        t = type(self.obj)
        return [("type", f"{t.__module__}.{t.__qualname__}"), ("public attributes", str(len(self._attrs())))]

    def numeric(self):
        return None

    def plot_kinds(self):
        return []
