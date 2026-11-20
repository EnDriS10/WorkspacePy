"""Small shared helpers: number formatting, safe repr, safe JSON, size in bytes."""

from __future__ import annotations

import math
import reprlib
import sys
from typing import Any

try:  # numpy is optional
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

_INT_TYPES: tuple = (int,) + ((np.integer,) if np is not None else ())
_FLOAT_TYPES: tuple = (float,) + ((np.floating,) if np is not None else ())
_COMPLEX_TYPES: tuple = (complex,) + ((np.complexfloating,) if np is not None else ())
_BOOL_TYPES: tuple = (bool,) + ((np.bool_,) if np is not None else ())


def get_module(name: str):
    """Return a module only if it is already imported (so scipy/sympy/pandas are never loaded needlessly)."""
    return sys.modules.get(name)


def format_scalar(x: Any, digits: int = 6) -> str:
    """Format a Python/NumPy scalar for display in a cell."""
    if isinstance(x, _BOOL_TYPES):
        return "True" if bool(x) else "False"
    if isinstance(x, _INT_TYPES):
        return str(int(x))
    if isinstance(x, _FLOAT_TYPES):
        xf = float(x)
        if math.isnan(xf):
            return "NaN"
        if math.isinf(xf):
            return "Inf" if xf > 0 else "-Inf"
        return f"{xf:.{digits}g}"
    if isinstance(x, _COMPLEX_TYPES):
        c = complex(x)
        re = format_scalar(c.real, digits)
        im = format_scalar(abs(c.imag) if not math.isnan(c.imag) else c.imag, digits)
        neg = c.imag < 0 or (c.imag == 0 and math.copysign(1.0, c.imag) < 0)
        return f"{re} {'-' if neg else '+'} {im}j"
    if isinstance(x, bytes):
        return repr(x)
    return str(x)


_repr = reprlib.Repr()
_repr.maxstring = 60
_repr.maxother = 60
_repr.maxlist = 6
_repr.maxtuple = 6
_repr.maxdict = 4
_repr.maxset = 6
_repr.maxlevel = 2


def short_repr(obj: Any, maxlen: int = 80) -> str:
    """Bounded repr that never raises."""
    try:
        text = _repr.repr(obj)
    except Exception:
        try:
            text = f"<{type(obj).__name__}>"
        except Exception:  # pragma: no cover
            text = "<?>"
    text = " ".join(text.split())  # single line
    if len(text) > maxlen:
        text = text[: maxlen - 1] + "…"
    return text


def deep_sizeof(obj: Any, limit: int = 20000) -> int:
    """Size in bytes. For containers it sums their elements (capped to stay fast)."""
    seen: set[int] = set()
    budget = [limit]

    def inner(o: Any) -> int:
        oid = id(o)
        if oid in seen or budget[0] <= 0:
            return 0
        seen.add(oid)
        budget[0] -= 1
        if np is not None and isinstance(o, np.ndarray):
            return int(o.nbytes)
        try:
            size = sys.getsizeof(o)
        except Exception:
            return 0
        if isinstance(o, dict):
            for k, v in list(o.items())[:5000]:
                size += inner(k) + inner(v)
        elif isinstance(o, (list, tuple, set, frozenset)):
            for v in list(o)[:5000]:
                size += inner(v)
        return size

    try:
        return inner(obj)
    except Exception:
        return 0


def jsonable(obj: Any) -> Any:
    """Convert to something serializable as strict JSON (NaN/Inf become text)."""
    if obj is None or isinstance(obj, (str, bool)):
        return obj
    if isinstance(obj, _BOOL_TYPES):
        return bool(obj)
    if isinstance(obj, _INT_TYPES):
        return int(obj)
    if isinstance(obj, _FLOAT_TYPES):
        f = float(obj)
        if math.isnan(f):
            return "NaN"
        if math.isinf(f):
            return "Inf" if f > 0 else "-Inf"
        return f
    if isinstance(obj, _COMPLEX_TYPES):
        return format_scalar(obj, 10)
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if np is not None and isinstance(obj, np.ndarray):
        return jsonable(obj.tolist())
    return str(obj)


def size_label(shape) -> str:
    """(3, 4) -> '3×4'; None -> '1×1'; () -> '()'."""
    if shape is None:
        return "1×1"
    if len(shape) == 0:
        return "()"
    return "×".join(str(int(s)) for s in shape)
