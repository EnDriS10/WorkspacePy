import numpy as np
import pytest

from workspacepy.inspectors import inspector_for
from workspacepy.inspectors.base import parse_literal, parse_value

sp = pytest.importorskip("sympy")
pd = pytest.importorskip("pandas")
sparse = pytest.importorskip("scipy.sparse")


def test_numpy_row_info():
    i = inspector_for(np.zeros((3, 4), dtype=np.float32))
    assert i.kind == "array" and i.size_label() == "3×4" and i.nbytes() == 48
    assert i.class_name() == "ndarray[float32]"


def test_numpy_window_and_edit():
    a = np.arange(12.0).reshape(3, 4)
    i = inspector_for(a)
    w = i.window(0, 2, 1, 3, [], 6)
    assert w["cells"] == [["1", "2"], ["5", "6"]] and w["nrows"] == 3 and w["ncols"] == 4
    assert i.set_item([], 2, 3, "99") == "99" and a[2, 3] == 99


def test_numpy_edit_rejects_bad_values_without_changing_data():
    a = np.arange(4)
    i = inspector_for(a)
    with pytest.raises(ValueError):
        i.set_item([], 0, 0, "1.5")  # array de enteros
    with pytest.raises(ValueError):
        i.set_item([], 0, 0, "abc")
    assert a.tolist() == [0, 1, 2, 3]


def test_readonly_array_cannot_be_edited():
    a = np.arange(4.0)
    a.setflags(write=False)
    with pytest.raises(ValueError):
        inspector_for(a).set_item([], 0, 0, "1")


def test_nd_slice_window():
    a = np.arange(24).reshape(2, 3, 4)
    w = inspector_for(a).window(0, 3, 0, 4, [1], 6)
    assert w["cells"][0] == ["12", "13", "14", "15"] and w["lead_shape"] == [2]


def test_0d_and_1d_arrays():
    assert inspector_for(np.array(5.0)).window(0, 1, 0, 1, [], 6)["cells"] == [["5"]]
    w = inspector_for(np.array([1.0, 2.0])).window(0, 1, 0, 2, [], 6)   # a vector is displayed as a row
    assert w["cells"] == [["1", "2"]] and w["nrows"] == 1 and w["ncols"] == 2
    v = np.zeros(3); i = inspector_for(v)
    i.set_item([], 0, 2, "7"); assert v[2] == 7             # editing the displayed row writes to the right element
    assert i.size_label() == "1×3" and "<" not in i.preview()


def test_complex_formatting():
    w = inspector_for(np.array([1 + 2j, 3 - 1j])).window(0, 1, 0, 2, [], 6)
    assert w["cells"] == [["1 + 2j", "3 - 1j"]]


def test_scalar_string_list_dict():
    assert inspector_for(3.5).kind == "scalar" and inspector_for("hola").detail()["value"] == "hola"
    lst = inspector_for([1, 2, 3])
    assert lst.kind == "container" and lst.n_children() == 3 and lst.child("[1]") == 2
    d = inspector_for({"a": 1})
    assert d.child("'a'") == 1
    d.set_child("'a'", "5")
    assert d.obj["a"] == 5


def test_tuple_is_readonly():
    with pytest.raises(ValueError):
        inspector_for((1, 2)).set_child("[0]", "3")


def test_sympy_expr_and_matrix():
    x = sp.Symbol("x")
    e = inspector_for(sp.sin(x) ** 2)
    assert e.kind == "sympy" and "sin" in e.detail()["latex"] and e.detail()["free_symbols"] == ["x"]
    m = inspector_for(sp.Matrix([[1, x], [x, 2]]))
    assert m.shape() == (2, 2) and m.window(0, 2, 0, 2, [], 6)["cells"][0] == ["1", "x"]


def test_pandas_dataframe():
    df = pd.DataFrame({"a": [1, 2], "b": [0.5, np.nan]})
    i = inspector_for(df)
    assert i.kind == "table" and i.shape() == (2, 2)
    w = i.window(0, 2, 0, 2, [], 6)
    assert w["col_labels"] == ["a", "b"] and w["cells"][1][1] == "NaN"
    assert [lab for lab, _ in i.iter_children()] == ["a", "b"]
    i.set_item([], 0, 0, "7")
    assert df.iat[0, 0] == 7


def test_scipy_sparse():
    m = sparse.eye(4, format="csr")
    i = inspector_for(m)
    assert i.kind == "array" and "nnz=4" in i.preview()
    assert i.window(0, 2, 0, 2, [], 6)["cells"] == [["1", "0"], ["0", "1"]]
    assert dict(i.properties())["nnz"] == "4"


def test_object_fallback_never_crashes():
    class Weird:
        def __repr__(self):
            raise RuntimeError("boom")

        @property
        def bad(self):
            raise RuntimeError("no")

    i = inspector_for(Weird())
    assert i.preview().startswith("<")  # short_repr swallows the exception


@pytest.mark.parametrize("text,kind,expected", [("3", "i", 3), ("3.0", "i", 3), ("2,5", "f", 2.5),
                                               ("1+2i", "c", 1 + 2j), ("true", "b", True)])
def test_parse_value(text, kind, expected):
    assert parse_value(text, kind) == expected


def test_parse_literal_does_not_execute_code():
    assert parse_literal("[1, 2]") == [1, 2]
    with pytest.raises(ValueError):
        parse_literal("__import__('os').system('echo hacked')")
