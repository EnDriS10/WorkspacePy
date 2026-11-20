"""MATLAB-style statistics (min, max, range, mean, median, mode, var, std, ...)."""

from __future__ import annotations

from contextlib import nullcontext as _nullcontext
from typing import Any, Optional

from .util import np

#: Statistics available as workspace columns (in this order).
STAT_NAMES = ("min", "max", "range", "mean", "median", "mode", "var", "std", "sum", "nnz", "nans")

#: Above this number of elements no statistics are computed.
MAX_STATS_ELEMENTS = 5_000_000
#: The mode requires sorting; above this size it is skipped.
MAX_MODE_ELEMENTS = 1_000_000
#: Maximum number of elements of a list/tuple that is converted to an array.
MAX_SEQUENCE_ELEMENTS = 1_000_000


def _py(x: Any) -> Any:
    return x.item() if hasattr(x, "item") else x


def as_numeric_array(obj: Any) -> Optional["np.ndarray"]:
    """Try to view `obj` as a numeric array (bool/int/uint/float/complex). Otherwise return None."""
    if np is None:
        return None
    arr = None
    if isinstance(obj, np.ndarray):
        arr = obj
    elif isinstance(obj, (bool, int, float, complex, np.generic)):
        arr = np.asarray(obj)
    elif isinstance(obj, (list, tuple, range)):
        if len(obj) == 0 or len(obj) > MAX_SEQUENCE_ELEMENTS:
            return None
        try:
            arr = np.asarray(obj)
        except Exception:
            return None
    elif type(obj).__module__.split(".")[0] == "pandas":
        try:
            arr = obj.to_numpy()
        except Exception:
            return None
    else:
        return None
    if arr is not None and arr.dtype.kind in "biufc":
        return arr
    return None


def compute_stats(arr: Optional["np.ndarray"]) -> dict:
    """Statistics of a numeric array. MATLAB convention: var/std with N-1.

    For complex arrays they are computed on the modulus |z|. NaNs are ignored
    (and counted in `nans`). Returns a dict with every key of STAT_NAMES
    (None when it cannot be computed).
    """
    with np.errstate(all="ignore") if np is not None else _nullcontext():
        return _compute(arr)


def _compute(arr: Optional["np.ndarray"]) -> dict:
    out: dict = {k: None for k in STAT_NAMES}
    if arr is None or np is None or arr.size == 0 or arr.size > MAX_STATS_ELEMENTS:
        return out
    a = np.abs(arr) if arr.dtype.kind == "c" else arr
    if a.dtype.kind == "b":
        a = a.astype(np.int8)
    flat = a.ravel()
    out["nnz"] = int(np.count_nonzero(flat))
    if flat.dtype.kind == "f":
        nan_mask = np.isnan(flat)
        out["nans"] = int(nan_mask.sum())
        valid = flat[~nan_mask] if out["nans"] else flat
    else:
        out["nans"] = 0
        valid = flat
    if valid.size == 0:
        return out
    mn, mx = _py(valid.min()), _py(valid.max())
    out["min"], out["max"] = mn, mx
    out["range"] = mx - mn  # with Python ints: no overflow
    out["mean"] = float(np.mean(valid, dtype=np.float64))
    out["median"] = float(np.median(valid))
    ddof = 1 if valid.size > 1 else 0
    out["var"] = float(np.var(valid, dtype=np.float64, ddof=ddof))
    out["std"] = float(np.std(valid, dtype=np.float64, ddof=ddof))
    out["sum"] = _py(valid.sum())
    if valid.size <= MAX_MODE_ELEMENTS:
        vals, counts = np.unique(valid, return_counts=True)
        out["mode"] = _py(vals[int(np.argmax(counts))])  # tie: the smallest, like MATLAB
    return out
