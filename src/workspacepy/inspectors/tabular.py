"""Inspector de pandas: DataFrame, Series e Index."""

from __future__ import annotations

from typing import List, Tuple

from ..stats import as_numeric_array
from ..util import format_scalar, get_module, jsonable, np, size_label
from .base import Inspector, clamp_window, make_window, parse_value, register

MAX_COLUMN_SUMMARIES = 100


@register
class PandasInspector(Inspector):
    kind = "table"
    priority = 100

    @classmethod
    def matches(cls, obj) -> bool:
        pd = get_module("pandas")
        return pd is not None and isinstance(obj, (pd.DataFrame, pd.Series, pd.Index))

    # ---- ayudas
    def _pd(self):
        return get_module("pandas")

    def _frame(self):
        pd = self._pd()
        o = self.obj
        if isinstance(o, pd.DataFrame):
            return o
        if isinstance(o, pd.Series):
            return o.to_frame()
        return o.to_frame(index=False)

    # ---- columnas de la tabla
    def class_name(self) -> str:
        pd = self._pd()
        name = type(self.obj).__name__
        if isinstance(self.obj, (pd.Series, pd.Index)):
            return f"{name}[{self.obj.dtype}]"
        return name

    def shape(self):
        return tuple(self.obj.shape)

    def nbytes(self) -> int:
        try:
            usage = self.obj.memory_usage(deep=False)
            return int(usage.sum() if hasattr(usage, "sum") else usage)
        except Exception:
            return 0

    def preview(self) -> str:
        return f"<{size_label(self.shape())} {type(self.obj).__name__}>"

    def numeric(self):
        arr = as_numeric_array(self.obj)
        if arr is not None:
            return arr
        pd = self._pd()
        try:
            o = self.obj
            if isinstance(o, pd.DataFrame):
                if o.shape[1] and all(pd.api.types.is_numeric_dtype(t) for t in o.dtypes):
                    return o.to_numpy(dtype="float64", na_value=np.nan)
            elif pd.api.types.is_numeric_dtype(o.dtype):
                return o.to_numpy(dtype="float64", na_value=np.nan)
        except Exception:
            pass
        return None

    # ---- detalle
    def properties(self) -> List[Tuple[str, str]]:
        pd = self._pd()
        o = self.obj
        props = [("tipo", type(o).__name__), ("shape", str(tuple(o.shape)))]
        if isinstance(o, pd.DataFrame):
            props.append(("columnas", str(len(o.columns))))
            props.append(("nulos totales", str(int(o.isna().sum().sum()))))
        else:
            props.append(("dtype", str(o.dtype)))
            props.append(("nulos", str(int(o.isna().sum()))))
        props.append(("índice", type(o.index).__name__ if not isinstance(o, pd.Index) else "—"))
        props.append(("memoria (sin deep)", f"{self.nbytes()} B"))
        return props

    def detail(self) -> dict:
        pd = self._pd()
        frame = self._frame()
        cols = []
        for j in range(min(frame.shape[1], MAX_COLUMN_SUMMARIES)):
            s = frame.iloc[:, j]
            item = {"name": str(frame.columns[j]), "dtype": str(s.dtype), "nulls": int(s.isna().sum())}
            try:
                item["nunique"] = int(s.nunique()) if len(s) <= 1_000_000 else None
            except Exception:
                item["nunique"] = None
            if pd.api.types.is_numeric_dtype(s.dtype) and len(s):
                for key, fn in (("min", s.min), ("max", s.max), ("mean", s.mean), ("std", s.std)):
                    try:
                        item[key] = jsonable(fn())
                    except Exception:
                        item[key] = None
            cols.append(item)
        return {"columns": cols, "columns_truncated": frame.shape[1] > MAX_COLUMN_SUMMARIES, "editable": not isinstance(self.obj, pd.Index)}

    # ---- hijos: cada columna se abre como Series
    def n_children(self):
        pd = self._pd()
        return len(self.obj.columns) if isinstance(self.obj, pd.DataFrame) else None

    def iter_children(self):
        pd = self._pd()
        if isinstance(self.obj, pd.DataFrame):
            for col in self.obj.columns:
                yield str(col), self.obj[col]

    # ---- tabla
    def window(self, r0, r1, c0, c1, index, digits):
        frame = self._frame()
        nrows, ncols = frame.shape
        r0, r1, c0, c1 = clamp_window(nrows, ncols, r0, r1, c0, c1)
        sub = frame.iloc[r0:r1, c0:c1]
        values = sub.to_numpy(dtype=object).tolist()
        return make_window(
            values, nrows, ncols, r0, c0, digits,
            row_labels=[str(i) for i in sub.index], col_labels=[str(c) for c in sub.columns],
            lead_shape=[], index=[], editable=self.detail_editable(),
        )

    def detail_editable(self) -> bool:
        return not isinstance(self.obj, self._pd().Index)

    def set_item(self, index, row, col, text) -> str:
        pd = self._pd()
        o = self.obj
        if isinstance(o, pd.Index):
            raise ValueError("un Index es inmutable")
        try:
            if isinstance(o, pd.DataFrame):
                kind = o.dtypes.iloc[col].kind
                o.iat[row, col] = parse_value(text, kind)
                return format_scalar(o.iat[row, col], 10)
            o.iat[row] = parse_value(text, o.dtype.kind)
            return format_scalar(o.iat[row], 10)
        except (IndexError, TypeError, OverflowError) as exc:
            raise ValueError(f"no se pudo asignar: {exc}") from None
