"""Array inspectors: numpy.ndarray and scipy.sparse matrices."""

from __future__ import annotations

from typing import List, Sequence, Tuple

from ..plots import slice2d
from ..stats import compute_stats  # noqa: F401  (re-exportado por comodidad)
from ..util import deep_sizeof, format_scalar, get_module, np, short_repr, size_label
from .base import Inspector, clamp_window, make_window, parse_value, register

MAX_DENSE_ELEMENTS = 2_000_000


def full_key(arr, index: Sequence[int], row: int, col: int) -> tuple:
    """Full index into an ndarray from the viewer's (leading index, row, column)."""
    if arr.ndim == 0:
        return ()
    if arr.ndim == 1:
        return (int(col),)             # 1-d arrays are displayed as one row
    lead = []
    for k in range(arr.ndim - 2):
        i = int(index[k]) if k < len(index) else 0
        lead.append(max(0, min(arr.shape[k] - 1, i)))
    return tuple(lead) + (int(row), int(col))


def lead_index(arr, index: Sequence[int]) -> list:
    return [max(0, min(arr.shape[k] - 1, int(index[k]) if k < len(index) else 0)) for k in range(max(arr.ndim - 2, 0))]


@register
class NumpyInspector(Inspector):
    kind = "array"
    priority = 70

    @classmethod
    def matches(cls, obj) -> bool:
        return np is not None and isinstance(obj, np.ndarray)

    def class_name(self) -> str:
        return f"{type(self.obj).__name__}[{self.obj.dtype}]"

    def shape(self):
        return self.obj.shape

    def nbytes(self) -> int:
        return int(self.obj.nbytes)

    def preview(self) -> str:
        a = self.obj
        if a.size == 0:
            return "[]"
        if a.dtype.kind in "biufc":
            # Show the content (the shape is in Size and the dtype in Class): [0, 0.101, ..., 10]
            text = np.array2string(a, precision=4, threshold=6, edgeitems=2, separator=", ", max_line_width=10_000)
            text = " ".join(text.split()).replace("[ ", "[").replace(" ]", "]")
            return text if len(text) <= 80 else text[:79] + "…"
        return short_repr(a)

    def numeric(self):
        return self.obj if self.obj.dtype.kind in "biufc" else None

    def properties(self) -> List[Tuple[str, str]]:
        a = self.obj
        return [
            ("shape", str(a.shape)), ("dtype", str(a.dtype)), ("ndim", str(a.ndim)),
            ("size", str(a.size)), ("itemsize", f"{a.itemsize} B"), ("nbytes", f"{a.nbytes} B"),
            ("C-contiguous", str(bool(a.flags.c_contiguous))), ("F-contiguous", str(bool(a.flags.f_contiguous))),
            ("owndata", str(bool(a.flags.owndata))), ("writeable", str(bool(a.flags.writeable))),
        ]

    def detail(self) -> dict:
        a = self.obj
        return {"editable": bool(a.flags.writeable and a.dtype.kind in "biufcUS"), "lead_shape": list(a.shape[:-2]) if a.ndim > 2 else []}

    def window(self, r0, r1, c0, c1, index, digits):
        a = self.obj
        a2 = a.reshape(1, -1) if a.ndim == 1 else slice2d(a, index)     # vectors are shown as a row
        r0, r1, c0, c1 = clamp_window(a2.shape[0], a2.shape[1], r0, r1, c0, c1)
        values = a2[r0:r1, c0:c1].tolist()
        col_labels = None
        return make_window(
            values, a2.shape[0], a2.shape[1], r0, c0, digits, col_labels=col_labels,
            lead_shape=list(a.shape[:-2]) if a.ndim > 2 else [], index=lead_index(a, index),
            editable=bool(a.flags.writeable and a.dtype.kind in "biufcUS"),
        )

    def set_item(self, index, row, col, text) -> str:
        a = self.obj
        if not a.flags.writeable:
            raise ValueError("the array is read-only")
        try:
            key = full_key(a, index, row, col)
            value = parse_value(text, a.dtype.kind)
            a[key] = value
            return format_scalar(a[key], 10)
        except (IndexError, OverflowError, TypeError) as exc:
            raise ValueError(f"could not assign: {exc}") from None


@register
class SparseInspector(Inspector):
    """scipy.sparse matrices/arrays (csr, csc, coo, lil, dok, dia, bsr)."""

    kind = "array"
    priority = 80

    @classmethod
    def matches(cls, obj) -> bool:
        sp = get_module("scipy.sparse")
        return sp is not None and sp.issparse(obj)

    def class_name(self) -> str:
        return f"{type(self.obj).__name__}[{self.obj.dtype}]"

    def shape(self):
        return tuple(self.obj.shape)

    def nbytes(self) -> int:
        total = 0
        for attr in ("data", "indices", "indptr", "row", "col", "offsets"):
            part = getattr(self.obj, attr, None)
            if isinstance(part, np.ndarray):
                total += int(part.nbytes)
        return total or deep_sizeof(self.obj)

    def preview(self) -> str:
        return f"sparse {self.obj.format}, nnz={self.obj.nnz}"

    def _n_elements(self) -> int:
        r, c = self.obj.shape[:2]
        return int(r) * int(c)

    def numeric(self):
        if self._n_elements() > MAX_DENSE_ELEMENTS:
            return None
        return self.obj.toarray()

    def properties(self):
        m = self.obj
        n = self._n_elements()
        density = (m.nnz / n) if n else 0.0
        return [
            ("format", str(m.format)), ("shape", str(tuple(m.shape))), ("dtype", str(m.dtype)),
            ("nnz", str(m.nnz)), ("density", f"{density:.4g}"), ("nbytes (stored)", f"{self.nbytes()} B"),
        ]

    def window(self, r0, r1, c0, c1, index, digits):
        nrows, ncols = self.obj.shape[:2]
        r0, r1, c0, c1 = clamp_window(nrows, ncols, r0, r1, c0, c1)
        sub = self.obj.tocsr()[r0:r1, c0:c1].toarray()
        return make_window(sub.tolist(), nrows, ncols, r0, c0, digits, editable=False, lead_shape=[], index=[])

    def plot_kinds(self):
        return super().plot_kinds()
