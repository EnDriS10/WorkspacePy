"""Data for the viewer plots (line, histogram, bars, image).

The server only returns already-reduced numbers; drawing is done by the browser on a <canvas>.
All non-finite values are returned as `null`.
"""

from __future__ import annotations

import math
from typing import Sequence

from .util import np

MAX_LINE_POINTS = 4000
MAX_SERIES = 12
MAX_BARS = 60
MAX_BAR_SERIES = 8
MAX_IMAGE_SIDE = 300


def slice2d(arr: "np.ndarray", index: Sequence[int] = ()) -> "np.ndarray":
    """Reduce an N-d array to 2D by fixing the leading dimensions with `index`.

    0-d -> (1, 1); 1-d -> column (n, 1); N-d -> arr[i0, i1, ..., :, :].
    """
    if arr.ndim == 0:
        return arr.reshape(1, 1)
    if arr.ndim == 1:
        return arr.reshape(-1, 1)
    if arr.ndim == 2:
        return arr
    idx = []
    for k in range(arr.ndim - 2):
        i = int(index[k]) if k < len(index) else 0
        idx.append(max(0, min(arr.shape[k] - 1, i)))
    return arr[tuple(idx)]


def clean_list(values) -> list:
    """1-d ndarray -> list of floats with None for NaN/Inf."""
    v = np.asarray(values, dtype=np.float64).ravel()
    out = v.tolist()
    bad = ~np.isfinite(v)
    if bad.any():
        for i in np.flatnonzero(bad):
            out[int(i)] = None
    return out


def _decimate(y: "np.ndarray"):
    """Return (x, y) with at most ~MAX_LINE_POINTS points, keeping the extremes."""
    n = y.shape[0]
    if n <= MAX_LINE_POINTS:
        return np.arange(n), y
    buckets = MAX_LINE_POINTS // 2
    size = n // buckets
    body = y[: buckets * size].reshape(buckets, size).astype(np.float64)
    nan = np.isnan(body)
    lo = np.where(nan, np.inf, body).argmin(axis=1)
    hi = np.where(nan, -np.inf, body).argmax(axis=1)
    first = np.minimum(lo, hi)
    second = np.maximum(lo, hi)
    base = np.arange(buckets) * size
    xs = np.empty(buckets * 2, dtype=np.int64)
    xs[0::2] = base + first
    xs[1::2] = base + second
    tail = np.arange(buckets * size, n)
    xs = np.concatenate([xs, tail])
    return xs, y[xs]


def _real(arr: "np.ndarray") -> "np.ndarray":
    if arr.dtype.kind == "c":
        return np.abs(arr)
    return arr.astype(np.float64) if arr.dtype.kind in "biu" else arr


def line_data(arr: "np.ndarray", index: Sequence[int] = ()) -> dict:
    a2 = slice2d(arr, index)
    ncols = a2.shape[1]
    single = arr.ndim <= 1
    series = []
    for j in range(min(ncols, MAX_SERIES)):
        col = a2[:, j]
        base = "value" if single else f"col {j}"
        parts = [(f"{base} (Re)", col.real), (f"{base} (Im)", col.imag)] if col.dtype.kind == "c" else [(base, col)]
        for name, y in parts:
            x, yy = _decimate(np.asarray(y))
            series.append({"name": name, "x": x.tolist(), "y": clean_list(yy)})
    return {
        "kind": "line",
        "series": series,
        "xlabel": "index",
        "n": int(a2.shape[0]),
        "truncated_series": bool(ncols > MAX_SERIES),
    }


def hist_data(arr: "np.ndarray", index: Sequence[int] = ()) -> dict:
    v = _real(arr).ravel().astype(np.float64)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return {"kind": "hist", "edges": [], "counts": [], "n": 0}
    lo, hi = float(v.min()), float(v.max())
    if arr.dtype.kind in "biu" and (hi - lo) < 100:
        edges = np.arange(lo, hi + 2) - 0.5  # one bin per integer
        counts, edges = np.histogram(v, bins=edges)
    else:
        bins = int(min(100, max(5, math.ceil(math.sqrt(v.size)))))
        counts, edges = np.histogram(v, bins=bins)
    return {"kind": "hist", "edges": clean_list(edges), "counts": counts.tolist(), "n": int(v.size), "min": lo, "max": hi}


def bar_data(arr: "np.ndarray", index: Sequence[int] = ()) -> dict:
    a2 = slice2d(_real(arr), index)
    rows = min(a2.shape[0], MAX_BARS)
    cols = min(a2.shape[1], MAX_BAR_SERIES)
    series = [{"name": "value" if arr.ndim <= 1 else f"col {j}", "y": clean_list(a2[:rows, j])} for j in range(cols)]
    return {
        "kind": "bar",
        "series": series,
        "labels": list(range(rows)),
        "truncated": bool(a2.shape[0] > rows or a2.shape[1] > cols),
    }


def image_data(arr: "np.ndarray", index: Sequence[int] = ()) -> dict:
    a2 = _real(arr)
    a2 = a2.reshape(1, -1) if a2.ndim == 1 else slice2d(a2, index)
    rows, cols = a2.shape
    sy = max(1, math.ceil(rows / MAX_IMAGE_SIDE))
    sx = max(1, math.ceil(cols / MAX_IMAGE_SIDE))
    sub = np.asarray(a2[::sy, ::sx], dtype=np.float64)
    finite = sub[np.isfinite(sub)]
    vmin = float(finite.min()) if finite.size else 0.0
    vmax = float(finite.max()) if finite.size else 1.0
    return {
        "kind": "image",
        "rows": int(sub.shape[0]),
        "cols": int(sub.shape[1]),
        "data": clean_list(sub.ravel()),
        "vmin": vmin,
        "vmax": vmax,
        "shape": [int(rows), int(cols)],
        "step": [sy, sx],
    }


BUILDERS = {"line": line_data, "hist": hist_data, "bar": bar_data, "image": image_data}


def available_plots(arr: "np.ndarray") -> list:
    kinds = ["line", "hist", "bar"]
    if arr.ndim >= 2:
        kinds.append("image")
    return kinds


def build_plot(arr: "np.ndarray", kind: str, index: Sequence[int] = ()) -> dict:
    try:
        builder = BUILDERS[kind]
    except KeyError:
        raise ValueError(f"unknown plot kind: {kind!r}") from None
    return builder(arr, index)
