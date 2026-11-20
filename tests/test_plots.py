import json

import numpy as np
import pytest

from workspacepy import plots


def strict(d):
    return json.dumps(d, allow_nan=False)  # fails if any NaN/Inf is left


def test_line_decimation_keeps_extremes():
    y = np.zeros(100_000)
    y[54321] = 9.0
    d = plots.line_data(y)
    assert len(d["series"][0]["y"]) <= 4100
    assert 9.0 in d["series"][0]["y"]
    strict(d)


def test_non_finite_become_none():
    d = plots.line_data(np.array([1.0, np.nan, np.inf, 2.0]))
    assert d["series"][0]["y"] == [1.0, None, None, 2.0]
    strict(d)


def test_complex_gives_re_and_im_series():
    d = plots.line_data(np.array([1 + 1j, 2 - 1j]))
    assert [s["name"] for s in d["series"]] == ["value (Re)", "value (Im)"]


def test_hist_integers_one_bin_per_value():
    d = plots.hist_data(np.array([1, 1, 2, 3, 3, 3]))
    assert d["counts"] == [2, 1, 3]


def test_hist_all_nan():
    assert plots.hist_data(np.array([np.nan]))["counts"] == []


def test_image_downsamples_large_arrays():
    d = plots.image_data(np.random.rand(3000, 1500))
    assert d["rows"] <= 300 and d["cols"] <= 300 and d["step"][0] >= 10
    strict(d)


def test_slice2d_clamps_indices():
    a = np.arange(24).reshape(2, 3, 4)
    assert plots.slice2d(a, [99])[0, 0] == 12
    assert plots.slice2d(np.arange(3)).shape == (3, 1)
    assert plots.slice2d(np.array(1.0)).shape == (1, 1)


def test_plot_kinds_by_ndim():
    assert "image" not in plots.available_plots(np.arange(3))
    assert "image" in plots.available_plots(np.zeros((2, 2)))


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        plots.build_plot(np.arange(3), "pie")
