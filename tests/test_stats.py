import numpy as np
import pytest

from workspacepy.stats import as_numeric_array, compute_stats


def test_basic_stats_match_numpy():
    a = np.array([[1.0, 2.0], [3.0, 4.0]])
    s = compute_stats(a)
    assert s["min"] == 1 and s["max"] == 4 and s["range"] == 3
    assert s["mean"] == pytest.approx(2.5) and s["median"] == pytest.approx(2.5)
    # como MATLAB: std con N-1
    assert s["std"] == pytest.approx(np.std(a, ddof=1))
    assert s["var"] == pytest.approx(np.var(a, ddof=1))
    assert s["sum"] == 10 and s["nnz"] == 4 and s["nans"] == 0


def test_mode_ties_pick_smallest_like_matlab():
    assert compute_stats(np.array([3, 1, 1, 3, 2]))["mode"] == 1
    assert compute_stats(np.array([1, 2, 2, 3, 3, 3]))["mode"] == 3


def test_nans_are_ignored_and_counted():
    s = compute_stats(np.array([1.0, np.nan, 3.0]))
    assert s["nans"] == 1 and s["mean"] == pytest.approx(2.0) and s["max"] == 3.0


def test_all_nan_does_not_crash():
    s = compute_stats(np.array([np.nan, np.nan]))
    assert s["nans"] == 2 and s["mean"] is None


def test_complex_uses_modulus():
    s = compute_stats(np.array([3 + 4j, 0 + 0j]))
    assert s["max"] == pytest.approx(5.0) and s["min"] == 0


def test_bool_and_unsigned_range_do_not_overflow():
    assert compute_stats(np.array([True, False, True]))["sum"] == 2
    assert compute_stats(np.array([0, 255], dtype=np.uint8))["range"] == 255


def test_single_element_std_is_zero_not_nan():
    assert compute_stats(np.array([5.0]))["std"] == 0.0


def test_empty_and_none():
    assert compute_stats(np.array([]))["mean"] is None
    assert compute_stats(None)["mean"] is None


def test_as_numeric_array_variants():
    assert as_numeric_array([1, 2, 3]).shape == (3,)
    assert as_numeric_array([[1, 2], [3, 4]]).shape == (2, 2)
    assert as_numeric_array(3.5).ndim == 0
    assert as_numeric_array(["a", "b"]) is None
    assert as_numeric_array({"a": 1}) is None
    assert as_numeric_array([]) is None
